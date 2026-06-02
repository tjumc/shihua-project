from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


# Export is driven from the curated delivery sheet.
FINAL_DELIVERY_SHEET = "最终交付表"
REQUIRED_HEADERS = [
    "规则编号",
    "知识类型",
    "子类型",
    "所属大类",
    "所属子项",
    "适用范围",
    "触发条件",
    "规则内容",
    "参数范围",
    "来源页码",
]


def normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    # Keep Excel numbers stable when they are serialized to JSON.
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()


def load_rules_from_workbook(workbook_path: Path) -> list[dict[str, Any]]:
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    if FINAL_DELIVERY_SHEET not in workbook.sheetnames:
        raise ValueError(f"Missing sheet: {FINAL_DELIVERY_SHEET}")

    worksheet = workbook[FINAL_DELIVERY_SHEET]
    row_iter = worksheet.iter_rows(values_only=True)
    try:
        headers = [normalize_cell(cell) for cell in next(row_iter)]
    except StopIteration as exc:
        raise ValueError("Workbook sheet is empty") from exc

    header_index = {header: index for index, header in enumerate(headers)}
    missing = [header for header in REQUIRED_HEADERS if header not in header_index]
    if missing:
        raise ValueError(f"Missing required headers: {missing}")

    rules: list[dict[str, Any]] = []
    for row in row_iter:
        # Normalize row values once so downstream fields stay string-based.
        values = {
            header: normalize_cell(row[index]) if index < len(row) else ""
            for header, index in header_index.items()
        }
        rule_id = values.get("规则编号", "")
        if not rule_id:
            continue

        source_page = values.get("来源页码", "")
        rules.append(
            {
                "rule_id": rule_id,
                "description": values.get("规则内容", ""),
                "major_category": values.get("所属大类", ""),
                "sub_category": values.get("所属子项", ""),
                "sets": [
                    {
                        "set_name": "KnowledgeType",
                        "subset_name": "知识类型",
                        "element": values.get("知识类型", ""),
                    },
                    {
                        "set_name": "SubType",
                        "subset_name": "子类型",
                        "element": values.get("子类型", ""),
                    },
                    {
                        "set_name": "Scope",
                        "subset_name": "适用范围",
                        "element": values.get("适用范围", ""),
                    },
                ],
                "parameters": {
                    "触发条件": {
                        "value": values.get("触发条件", ""),
                        "unit": "",
                    },
                    "规则内容": {
                        "value": values.get("规则内容", ""),
                        "unit": "",
                    },
                    "参数范围": {
                        "value": values.get("参数范围", ""),
                        "unit": "",
                    },
                    "来源页码": {
                        "value": source_page,
                        "unit": "页" if source_page else "",
                    },
                },
            }
        )

    workbook.close()
    return rules


def group_rules_by_major_category(
    rules: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        # Unclassified rules still need a predictable output bucket.
        major_category = rule.get("major_category", "") or "未分类"
        grouped.setdefault(major_category, []).append(rule)
    return grouped


def build_library_payload(
    rules: list[dict[str, Any]], workbook_path: Path
) -> dict[str, Any]:
    total_rules = len(rules)
    grouped = group_rules_by_major_category(rules)
    return {
        "meta": {
            "library_name": "refinery_extracted_rule_library_current",
            "version": "v3",
            "status": "populated" if total_rules else "initialized_not_populated",
            "encoding": "UTF-8",
            "source_of_truth": str(workbook_path),
            "preferred_mapping_sheet": FINAL_DELIVERY_SHEET,
            "expected_total_rules": total_rules,
            "loaded_rule_count": total_rules,
            "grouping_mode": "major_category_split_with_aggregate",
            "major_category_counts": {
                category: len(category_rules)
                for category, category_rules in grouped.items()
            },
            "last_updated": date.today().isoformat(),
            "notes": "当前文件为按大类拆分后的自动汇总文件，由主总表中的最终交付表批量导出生成。",
        },
        "rules": rules,
    }


def build_category_payload(
    major_category: str, rules: list[dict[str, Any]], workbook_path: Path
) -> dict[str, Any]:
    total_rules = len(rules)
    return {
        "meta": {
            "library_name": "refinery_extracted_rule_library_by_major_category",
            "version": "v3",
            "status": "populated" if total_rules else "initialized_not_populated",
            "encoding": "UTF-8",
            "source_of_truth": str(workbook_path),
            "preferred_mapping_sheet": FINAL_DELIVERY_SHEET,
            "grouping_mode": "major_category",
            "major_category": major_category,
            "loaded_rule_count": total_rules,
            "last_updated": date.today().isoformat(),
            "notes": "当前文件为按所属大类拆分后的规则库文件。",
        },
        "rules": rules,
    }


def build_index_payload(
    grouped_rules: dict[str, list[dict[str, Any]]], workbook_path: Path
) -> dict[str, Any]:
    categories = []
    for major_category, rules in grouped_rules.items():
        categories.append(
            {
                "major_category": major_category,
                "rule_count": len(rules),
                "file_name": f"{major_category}.json",
            }
        )
    return {
        "meta": {
            "library_name": "refinery_extracted_rule_library_index",
            "version": "v3",
            "status": "populated",
            "encoding": "UTF-8",
            "source_of_truth": str(workbook_path),
            "preferred_mapping_sheet": FINAL_DELIVERY_SHEET,
            "grouping_mode": "major_category",
            "last_updated": date.today().isoformat(),
        },
        "categories": categories,
    }


def write_payload(payload: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def export_grouped_libraries(
    workbook_path: Path, output_root: Path
) -> dict[str, list[dict[str, Any]]]:
    rules = load_rules_from_workbook(workbook_path)
    grouped = group_rules_by_major_category(rules)

    # Keep split files together with aggregate and index exports.
    current_dir = output_root / "current"
    current_dir.mkdir(parents=True, exist_ok=True)

    for major_category, category_rules in grouped.items():
        payload = build_category_payload(major_category, category_rules, workbook_path)
        write_payload(payload, current_dir / f"{major_category}.json")

    aggregate_payload = build_library_payload(rules, workbook_path)
    write_payload(aggregate_payload, output_root / "规则库_当前版.json")

    index_payload = build_index_payload(grouped, workbook_path)
    write_payload(index_payload, output_root / "index.json")

    return grouped


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    workbook_path = root / "提取结果" / "01_当前结果" / "主总表.xlsx"
    output_root = root / "json规则库"
    export_grouped_libraries(workbook_path, output_root)


if __name__ == "__main__":
    main()
