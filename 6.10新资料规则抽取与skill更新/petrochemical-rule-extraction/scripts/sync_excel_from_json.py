#!/usr/bin/env python3
"""Rebuild extracted_rules.xls from the five petrochemical rule JSON files."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import xlrd
from xlutils.copy import copy as xl_copy


EXCEL_HEADERS = [
    "规则编号",
    "规则名称",
    "知识类型",
    "子类型",
    "适用范围",
    "规则内容",
    "来源文件",
    "具体页码",
    "原文内容",
    "JSON",
    "备注",
]
FIELDS = [
    "rule_id",
    "rule_name",
    "knowledge_type",
    "sub_type",
    "applicable_scope",
    "rule_content",
    "source_file",
    "locator",
    "evidence_text",
    "parameters",
    "devices",
    "operations",
    "conditions",
    "constraint_type",
    "notes",
]
SHEET_JSON_MAPPING = {
    "1、质量标准规则": "质量标准规则.json",
    "2、工艺规范规则": "工艺规范规则.json",
    "3、流程特征规则": "流程特征规则.json",
    "4、操作规程规则": "操作规程规则.json",
    "5、调度经验规则": "调度经验规则.json",
}
ROW_KEYS = [
    "rule_id",
    "rule_name",
    "knowledge_type",
    "sub_type",
    "applicable_scope",
    "rule_content",
    "source_file",
    "locator",
    "evidence_text",
    "notes",
]


def load_rules(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("rules", "data", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a JSON array or a common rule-array wrapper")
    for idx, rule in enumerate(data, start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"{path.name} row {idx} is not a JSON object")
        missing = [field for field in FIELDS if field not in rule]
        if missing:
            raise ValueError(f"{path.name} row {idx} missing fields: {', '.join(missing)}")
    return data


def row_values(rule: dict[str, Any]) -> list[str]:
    return [
        str(rule.get("rule_id", "")),
        str(rule.get("rule_name", "")),
        str(rule.get("knowledge_type", "")),
        str(rule.get("sub_type", "")),
        str(rule.get("applicable_scope", "")),
        str(rule.get("rule_content", "")),
        str(rule.get("source_file", "")),
        str(rule.get("locator", "")),
        str(rule.get("evidence_text", "")),
        json.dumps(rule, ensure_ascii=False),
        str(rule.get("notes", "")),
    ]


def rebuild_excel(output_dir: Path, template_xls: Path, backup: bool) -> dict[str, int]:
    rules_by_sheet = {
        sheet: load_rules(output_dir / json_file)
        for sheet, json_file in SHEET_JSON_MAPPING.items()
    }
    target_xls = output_dir / "extracted_rules.xls"
    if backup and target_xls.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(target_xls, output_dir / f"extracted_rules_backup_{stamp}.xls")
    shutil.copy2(template_xls, target_xls)

    rb = xlrd.open_workbook(str(target_xls), formatting_info=True)
    wb = xl_copy(rb)
    sheet_names = rb.sheet_names()
    for sheet, rules in rules_by_sheet.items():
        if sheet not in sheet_names:
            raise ValueError(f"Template is missing sheet: {sheet}")
        ws = wb.get_sheet(sheet_names.index(sheet))
        for col, header in enumerate(EXCEL_HEADERS):
            ws.write(0, col, header)
        for row_idx, rule in enumerate(rules, start=1):
            for col, value in enumerate(row_values(rule)):
                ws.write(row_idx, col, value)
    wb.save(str(target_xls))
    return {sheet: len(rules) for sheet, rules in rules_by_sheet.items()}


def verify_excel(output_dir: Path) -> dict[str, int]:
    target_xls = output_dir / "extracted_rules.xls"
    book = xlrd.open_workbook(str(target_xls))
    counts: dict[str, int] = {}
    for sheet, json_file in SHEET_JSON_MAPPING.items():
        rules = load_rules(output_dir / json_file)
        sh = book.sheet_by_name(sheet)
        headers = [str(sh.cell_value(0, col)).strip() for col in range(len(EXCEL_HEADERS))]
        if headers != EXCEL_HEADERS:
            raise ValueError(f"{sheet} header mismatch")
        if sh.nrows - 1 != len(rules):
            raise ValueError(f"{sheet} row count mismatch: excel={sh.nrows - 1}, json={len(rules)}")
        for idx, rule in enumerate(rules, start=1):
            expected = row_values(rule)
            actual = [str(sh.cell_value(idx, col)) for col in range(len(EXCEL_HEADERS))]
            if actual != expected:
                raise ValueError(f"{sheet} row {idx + 1} differs from {json_file}")
        counts[sheet] = len(rules)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild extracted_rules.xls from five rule JSON files.")
    parser.add_argument("output_dir", type=Path, help="Directory containing extracted_rules.xls and five JSON files.")
    parser.add_argument(
        "--template-xls",
        type=Path,
        default=Path("/Users/xiluo/.codex/skills/petrochemical-rule-extraction/templates/rule_summary_template.xls"),
    )
    parser.add_argument("--backup", action="store_true", help="Keep a timestamped backup of the existing xls.")
    parser.add_argument("--verify-only", action="store_true", help="Only verify Excel/JSON consistency.")
    args = parser.parse_args()

    if args.verify_only:
        counts = verify_excel(args.output_dir)
        action = "verified"
    else:
        rebuild_excel(args.output_dir, args.template_xls, args.backup)
        counts = verify_excel(args.output_dir)
        action = "rebuilt_and_verified"
    print(json.dumps({"status": action, "counts": counts, "total": sum(counts.values())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
