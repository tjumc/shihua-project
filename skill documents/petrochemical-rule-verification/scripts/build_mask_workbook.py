#!/usr/bin/env python3
from __future__ import annotations

import argparse
from common import (
    choose_numeric_key,
    choose_semantic_key,
    header_map,
    is_rule_sheet,
    load_xlsx,
    mask_text,
    normalize_header_order,
    save_xlsx,
    safe_str,
)


def build_masks(input_path: str, output_path: str):
    wb = load_xlsx(input_path)
    for ws in wb.worksheets:
        if not is_rule_sheet(ws):
            continue
        normalize_header_order(ws)
        h = header_map(ws)
        rule_col = h["规则内容"]
        for row in range(2, ws.max_row + 1):
            rule = safe_str(ws.cell(row, rule_col).value)
            if not rule:
                continue
            key1 = choose_numeric_key(rule)
            masked1 = mask_text(rule, key1)
            key2 = choose_semantic_key(rule, key1)
            masked2 = mask_text(rule, key2)
            if key1:
                ws.cell(row, h["规则内容mask1"]).value = masked1
                ws.cell(row, h["关键字段mask1"]).value = key1
            if key2:
                ws.cell(row, h["规则内容mask2"]).value = masked2
                ws.cell(row, h["关键字段mask2"]).value = key2
    save_xlsx(wb, output_path)


def main():
    parser = argparse.ArgumentParser(description="Build rule-content mask columns for petrochemical rule verification.")
    parser.add_argument("--input", required=True, help="Input extracted rules workbook")
    parser.add_argument("--output", required=True, help="Output mask workbook")
    args = parser.parse_args()
    build_masks(args.input, args.output)


if __name__ == "__main__":
    main()
