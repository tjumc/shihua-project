from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional, Sequence

from .db import DEFAULT_DATABASE, connect, database_stats, migrate
from .importer import ImportConflictError, import_workbook
from .workbook import WorkbookValidationError, read_official_workbook


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORKBOOK = (
    REPO_ROOT
    / "提取结果"
    / "01_当前结果"
    / "五类规则汇总"
    / "01_规则表"
    / "五类规则正式提交表_1050条.xlsx"
)


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="石化五类知识规则 SQLite 管理工具")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"SQLite 文件路径，默认：{DEFAULT_DATABASE}",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="初始化或升级数据库结构")

    validate = commands.add_parser("validate", help="校验正式规则 Excel")
    validate.add_argument("excel", type=Path, nargs="?", default=DEFAULT_WORKBOOK)

    import_command = commands.add_parser("import", help="导入正式规则 Excel")
    import_command.add_argument("excel", type=Path, nargs="?", default=DEFAULT_WORKBOOK)
    import_command.add_argument(
        "--update-existing",
        action="store_true",
        help="明确更新编号相同但内容变化的规则，并写入变更日志",
    )

    commands.add_parser("stats", help="核验规则总数、分类数量和最近导入批次")

    search = commands.add_parser("search", help="按编号、名称、内容或来源检索规则")
    search.add_argument("keyword")
    search.add_argument("--category", choices=["SOP", "QS", "FLOW", "PROC", "EXP"])
    search.add_argument("--limit", type=int, default=20)
    return parser


def _search(connection: Any, keyword: str, category: Optional[str], limit: int) -> list[dict[str, Any]]:
    pattern = f"%{keyword.strip()}%"
    where = """
        deleted_at IS NULL AND (
            rule_no LIKE ? OR rule_name LIKE ? OR rule_content LIKE ?
            OR subtype LIKE ? OR applicable_scope LIKE ? OR source_basis LIKE ?
        )
    """
    parameters: list[Any] = [pattern] * 6
    if category:
        where += " AND category_code = ?"
        parameters.append(category)
    parameters.append(max(1, min(limit, 200)))
    rows = connection.execute(
        f"""
        SELECT rule_no, rule_name, category_code, subtype, applicable_scope,
               trigger_condition, rule_content, parameter_text,
               source_page, source_basis
        FROM rules
        WHERE {where}
        ORDER BY rule_no
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return [dict(row) for row in rows]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            workbook = read_official_workbook(args.excel)
            _print(
                {
                    "status": "valid",
                    "file": str(workbook.path),
                    "sha256": workbook.file_sha256,
                    "total": len(workbook.records),
                    "categories": workbook.category_counts,
                }
            )
            return 0

        connection = connect(args.db)
        try:
            applied = migrate(connection)
            if args.command == "init":
                _print(
                    {
                        "status": "ready",
                        "database": str(Path(args.db).expanduser().resolve()),
                        "applied_migrations": applied,
                    }
                )
            elif args.command == "import":
                result = import_workbook(
                    connection, args.excel, update_existing=args.update_existing
                )
                _print({"status": "success", **asdict(result)})
            elif args.command == "stats":
                _print(database_stats(connection))
            elif args.command == "search":
                results = _search(connection, args.keyword, args.category, args.limit)
                _print({"count": len(results), "results": results})
            return 0
        finally:
            connection.close()
    except (WorkbookValidationError, ImportConflictError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"执行失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
