from __future__ import annotations

import hashlib
import json
import math
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, Union

from .db import DEFAULT_DATABASE, connect, migrate


CATEGORY_LABELS = {
    "SOP": "操作规程规则",
    "QS": "质量标准规则",
    "FLOW": "流程特征规则",
    "PROC": "工艺规范规则",
    "EXP": "调度经验规则",
}
CATEGORY_PREFIXES = {code: f"{code}-" for code in CATEGORY_LABELS}
STATUS_LABELS = {
    "all": "全部状态",
    "published": "已发布",
    "draft": "草稿",
    "archived": "已归档",
}


class RuleValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RulePage:
    rows: tuple[dict[str, Any], ...]
    total: int
    page: int
    pages: int
    page_size: int


@contextmanager
def database(database: Optional[Union[str, Path]] = None) -> Iterator[Any]:
    connection = connect(database or DEFAULT_DATABASE)
    try:
        migrate(connection)
        yield connection
    finally:
        connection.close()


def dashboard_data(database_path: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    with database(database_path) as connection:
        summary = connection.execute(
            """
            SELECT
                SUM(CASE WHEN deleted_at IS NULL THEN 1 ELSE 0 END) AS active_count,
                SUM(CASE WHEN status = 'draft' AND deleted_at IS NULL THEN 1 ELSE 0 END) AS draft_count,
                SUM(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END) AS archived_count
            FROM rules
            """
        ).fetchone()
        source_count = connection.execute(
            """
            SELECT COUNT(DISTINCT source_document_id)
            FROM rules
            WHERE deleted_at IS NULL
            """
        ).fetchone()[0]
        categories = connection.execute(
            """
            SELECT c.code, c.name, COUNT(r.id) AS count
            FROM rule_categories AS c
            LEFT JOIN rules AS r
              ON r.category_code = c.code AND r.deleted_at IS NULL
            GROUP BY c.code, c.name, c.display_order
            ORDER BY c.display_order
            """
        ).fetchall()
        subtypes = connection.execute(
            """
            SELECT subtype, COUNT(*) AS count
            FROM rules
            WHERE deleted_at IS NULL
            GROUP BY subtype
            ORDER BY count DESC, subtype
            LIMIT 8
            """
        ).fetchall()
        recent = connection.execute(
            """
            SELECT rule_no, rule_name, updated_at
            FROM rules
            ORDER BY updated_at DESC, id DESC
            LIMIT 5
            """
        ).fetchall()
    active_count = int(summary["active_count"] or 0)
    return {
        "active_count": active_count,
        "draft_count": int(summary["draft_count"] or 0),
        "archived_count": int(summary["archived_count"] or 0),
        "source_count": int(source_count or 0),
        "categories": [
            {
                **dict(row),
                "percent": round((int(row["count"]) / active_count * 100), 1)
                if active_count
                else 0,
            }
            for row in categories
        ],
        "subtypes": [dict(row) for row in subtypes],
        "recent": [dict(row) for row in recent],
    }


def list_rules(
    keyword: str = "",
    category: str = "ALL",
    status: str = "all",
    page: int = 1,
    page_size: int = 20,
    database_path: Optional[Union[str, Path]] = None,
) -> RulePage:
    conditions: list[str] = []
    parameters: list[Any] = []
    keyword = (keyword or "").strip()
    if keyword:
        pattern = f"%{keyword}%"
        conditions.append(
            """
            (r.rule_no LIKE ? OR r.rule_name LIKE ? OR r.rule_content LIKE ?
             OR r.subtype LIKE ? OR r.applicable_scope LIKE ?
             OR r.source_basis LIKE ? OR d.file_name LIKE ?)
            """
        )
        parameters.extend([pattern] * 7)
    if category and category != "ALL":
        conditions.append("r.category_code = ?")
        parameters.append(category)
    if status == "archived":
        conditions.append("r.deleted_at IS NOT NULL")
    elif status in {"published", "draft"}:
        conditions.append("r.deleted_at IS NULL AND r.status = ?")
        parameters.append(status)
    else:
        conditions.append("r.deleted_at IS NULL")

    where = " AND ".join(f"({condition})" for condition in conditions) or "1 = 1"
    page_size = max(5, min(int(page_size or 20), 100))
    with database(database_path) as connection:
        total = int(
            connection.execute(
                f"""
                SELECT COUNT(*)
                FROM rules AS r
                JOIN source_documents AS d ON d.id = r.source_document_id
                WHERE {where}
                """,
                parameters,
            ).fetchone()[0]
        )
        pages = max(1, math.ceil(total / page_size))
        page = max(1, min(int(page or 1), pages))
        rows = connection.execute(
            f"""
            SELECT r.rule_no, r.rule_name, c.name AS category_name,
                   r.category_code, r.subtype, d.file_name AS source_file,
                   r.status, r.version, r.updated_at
            FROM rules AS r
            JOIN rule_categories AS c ON c.code = r.category_code
            JOIN source_documents AS d ON d.id = r.source_document_id
            WHERE {where}
            ORDER BY c.display_order, r.sequence_no, r.rule_no
            LIMIT ? OFFSET ?
            """,
            parameters + [page_size, (page - 1) * page_size],
        ).fetchall()
    return RulePage(
        rows=tuple(dict(row) for row in rows),
        total=total,
        page=page,
        pages=pages,
        page_size=page_size,
    )


def get_rule(
    rule_no: str, database_path: Optional[Union[str, Path]] = None
) -> Optional[dict[str, Any]]:
    if not rule_no:
        return None
    with database(database_path) as connection:
        row = connection.execute(
            """
            SELECT r.*, c.name AS category_name, d.file_name AS source_file
            FROM rules AS r
            JOIN rule_categories AS c ON c.code = r.category_code
            JOIN source_documents AS d ON d.id = r.source_document_id
            WHERE r.rule_no = ?
            """,
            (rule_no,),
        ).fetchone()
    return dict(row) if row else None


def next_rule_number(
    category_code: str, database_path: Optional[Union[str, Path]] = None
) -> str:
    if category_code not in CATEGORY_PREFIXES:
        raise RuleValidationError("请选择有效的规则类别")
    prefix = CATEGORY_PREFIXES[category_code]
    with database(database_path) as connection:
        numbers = [
            row[0]
            for row in connection.execute(
                "SELECT rule_no FROM rules WHERE category_code = ?", (category_code,)
            )
        ]
    suffixes = []
    for number in numbers:
        match = re.fullmatch(re.escape(prefix) + r"(\d+)", number)
        if match:
            suffixes.append(int(match.group(1)))
    return f"{prefix}{max(suffixes, default=0) + 1:03d}"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _optional(value: Any) -> Optional[str]:
    value = _clean(value)
    return value or None


def _rule_hash(values: dict[str, Any]) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def save_rule(
    values: dict[str, Any],
    original_rule_no: Optional[str] = None,
    database_path: Optional[Union[str, Path]] = None,
) -> str:
    category_code = _clean(values.get("category_code"))
    rule_no = _clean(values.get("rule_no"))
    status = _clean(values.get("status")) or "published"
    if category_code not in CATEGORY_LABELS:
        raise RuleValidationError("请选择有效的规则类别")
    if not rule_no.startswith(CATEGORY_PREFIXES[category_code]):
        raise RuleValidationError(
            f"规则编号必须以 {CATEGORY_PREFIXES[category_code]} 开头"
        )
    if status not in {"published", "draft"}:
        raise RuleValidationError("规则状态只能是已发布或草稿")

    required = {
        "rule_no": "规则编号",
        "rule_name": "规则名称",
        "subtype": "子类型",
        "applicable_scope": "适用范围",
        "rule_content": "规则内容",
        "source_file": "来源文件",
        "source_page": "来源页码",
        "source_basis": "来源依据",
    }
    cleaned = {key: _clean(values.get(key)) for key in required}
    missing = [label for key, label in required.items() if not cleaned[key]]
    if missing:
        raise RuleValidationError(f"请填写必填字段：{', '.join(missing)}")

    with database(database_path) as connection:
        category = connection.execute(
            "SELECT name, knowledge_type FROM rule_categories WHERE code = ?",
            (category_code,),
        ).fetchone()
        current = None
        if original_rule_no:
            current = connection.execute(
                "SELECT * FROM rules WHERE rule_no = ?", (original_rule_no,)
            ).fetchone()
            if current is None:
                raise RuleValidationError(f"未找到规则：{original_rule_no}")
        duplicate = connection.execute(
            "SELECT id FROM rules WHERE rule_no = ?", (rule_no,)
        ).fetchone()
        if duplicate and (current is None or duplicate["id"] != current["id"]):
            raise RuleValidationError(f"规则编号已存在：{rule_no}")

        connection.execute(
            "INSERT INTO source_documents (file_name) VALUES (?) "
            "ON CONFLICT(file_name) DO NOTHING",
            (cleaned["source_file"],),
        )
        document_id = connection.execute(
            "SELECT id FROM source_documents WHERE file_name = ?",
            (cleaned["source_file"],),
        ).fetchone()["id"]
        payload = {
            "rule_no": rule_no,
            "rule_name": cleaned["rule_name"],
            "category_code": category_code,
            "knowledge_type": category["knowledge_type"],
            "subtype": cleaned["subtype"],
            "applicable_scope": cleaned["applicable_scope"],
            "trigger_condition": _optional(values.get("trigger_condition")),
            "rule_content": cleaned["rule_content"],
            "parameter_text": _optional(values.get("parameter_text")),
            "source_page": cleaned["source_page"],
            "source_basis": cleaned["source_basis"],
            "notes": _optional(values.get("notes")),
            "status": status,
        }
        content_hash = _rule_hash(payload)

        with connection:
            if current is None:
                sequence_no = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM rules WHERE category_code = ?",
                        (category_code,),
                    ).fetchone()[0]
                )
                cursor = connection.execute(
                    """
                    INSERT INTO rules (
                        sequence_no, rule_no, rule_name, category_code, knowledge_type,
                        subtype, applicable_scope, trigger_condition, rule_content,
                        parameter_text, source_document_id, source_page, source_basis,
                        notes, source_sheet, source_row, content_hash, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '系统录入', 0, ?, ?)
                    """,
                    (
                        sequence_no,
                        rule_no,
                        payload["rule_name"],
                        category_code,
                        payload["knowledge_type"],
                        payload["subtype"],
                        payload["applicable_scope"],
                        payload["trigger_condition"],
                        payload["rule_content"],
                        payload["parameter_text"],
                        document_id,
                        payload["source_page"],
                        payload["source_basis"],
                        payload["notes"],
                        content_hash,
                        status,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO rule_change_logs (rule_id, action, new_values)
                    VALUES (?, 'insert', ?)
                    """,
                    (cursor.lastrowid, json.dumps(payload, ensure_ascii=False)),
                )
            else:
                old_values = dict(current)
                connection.execute(
                    """
                    UPDATE rules
                    SET rule_no = ?, rule_name = ?, category_code = ?, knowledge_type = ?,
                        subtype = ?, applicable_scope = ?, trigger_condition = ?,
                        rule_content = ?, parameter_text = ?, source_document_id = ?,
                        source_page = ?, source_basis = ?, notes = ?, content_hash = ?,
                        status = ?, version = version + 1,
                        updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                    """,
                    (
                        rule_no,
                        payload["rule_name"],
                        category_code,
                        payload["knowledge_type"],
                        payload["subtype"],
                        payload["applicable_scope"],
                        payload["trigger_condition"],
                        payload["rule_content"],
                        payload["parameter_text"],
                        document_id,
                        payload["source_page"],
                        payload["source_basis"],
                        payload["notes"],
                        content_hash,
                        status,
                        current["id"],
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO rule_change_logs (
                        rule_id, action, old_values, new_values
                    ) VALUES (?, 'update', ?, ?)
                    """,
                    (
                        current["id"],
                        json.dumps(old_values, ensure_ascii=False),
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
    return rule_no


def set_rule_archived(
    rule_no: str,
    archived: bool,
    database_path: Optional[Union[str, Path]] = None,
) -> None:
    with database(database_path) as connection:
        current = connection.execute(
            "SELECT * FROM rules WHERE rule_no = ?", (rule_no,)
        ).fetchone()
        if current is None:
            raise RuleValidationError(f"未找到规则：{rule_no}")
        if archived and current["deleted_at"] is not None:
            return
        if not archived and current["deleted_at"] is None:
            return
        action = "archive" if archived else "restore"
        with connection:
            if archived:
                connection.execute(
                    """
                    UPDATE rules
                    SET status = 'archived', deleted_at = datetime('now', 'localtime'),
                        version = version + 1,
                        updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                    """,
                    (current["id"],),
                )
            else:
                connection.execute(
                    """
                    UPDATE rules
                    SET status = 'published', deleted_at = NULL,
                        version = version + 1,
                        updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                    """,
                    (current["id"],),
                )
            updated = connection.execute(
                "SELECT * FROM rules WHERE id = ?", (current["id"],)
            ).fetchone()
            connection.execute(
                """
                INSERT INTO rule_change_logs (rule_id, action, old_values, new_values)
                VALUES (?, ?, ?, ?)
                """,
                (
                    current["id"],
                    action,
                    json.dumps(dict(current), ensure_ascii=False),
                    json.dumps(dict(updated), ensure_ascii=False),
                ),
            )


def list_import_batches(
    limit: int = 50, database_path: Optional[Union[str, Path]] = None
) -> list[dict[str, Any]]:
    with database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id, source_file_name, status, expected_count, inserted_count,
                   updated_count, unchanged_count, failed_count, created_at, completed_at
            FROM import_batches
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    return [dict(row) for row in rows]


def list_rule_changes(
    rule_no: str,
    limit: int = 20,
    database_path: Optional[Union[str, Path]] = None,
) -> list[dict[str, Any]]:
    with database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT l.action, l.created_at, l.import_batch_id
            FROM rule_change_logs AS l
            JOIN rules AS r ON r.id = l.rule_id
            WHERE r.rule_no = ?
            ORDER BY l.id DESC
            LIMIT ?
            """,
            (rule_no, max(1, min(int(limit), 100))),
        ).fetchall()
    return [dict(row) for row in rows]
