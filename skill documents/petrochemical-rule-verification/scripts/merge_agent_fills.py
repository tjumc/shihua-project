#!/usr/bin/env python3
from __future__ import annotations

import argparse
from common import header_map, is_rule_sheet, load_xlsx, save_xlsx, safe_str


def collect_fills(path: str, suffix: str):
    wb = load_xlsx(path)
    out = {}
    fill_col = f"填空内容mask{suffix}"
    evidence_col = f"原文内容mask{suffix}"
    for ws in wb.worksheets:
        h = header_map(ws)
        if "规则编号" not in h:
            continue
        for row in range(2, ws.max_row + 1):
            rid = safe_str(ws.cell(row, h["规则编号"]).value)
            if not rid:
                continue
            out[rid] = {
                fill_col: ws.cell(row, h[fill_col]).value if fill_col in h else None,
                evidence_col: ws.cell(row, h[evidence_col]).value if evidence_col in h else None,
            }
    return out


def merge(base_path: str, agent1_path: str, agent2_path: str, output_path: str):
    base = load_xlsx(base_path)
    fills1 = collect_fills(agent1_path, "1")
    fills2 = collect_fills(agent2_path, "2")
    for ws in base.worksheets:
        if not is_rule_sheet(ws):
            continue
        h = header_map(ws)
        for row in range(2, ws.max_row + 1):
            rid = safe_str(ws.cell(row, h["规则编号"]).value)
            if not rid:
                continue
            if rid in fills1:
                for col_name, value in fills1[rid].items():
                    if col_name in h and value not in (None, ""):
                        ws.cell(row, h[col_name]).value = value
            if rid in fills2:
                for col_name, value in fills2[rid].items():
                    if col_name in h and value not in (None, ""):
                        ws.cell(row, h[col_name]).value = value
    save_xlsx(base, output_path)


def main():
    parser = argparse.ArgumentParser(description="Merge two blind agent fill results into the base mask workbook.")
    parser.add_argument("--base", required=True, help="Base mask workbook")
    parser.add_argument("--agent1", required=True, help="Agent1 filled workbook")
    parser.add_argument("--agent2", required=True, help="Agent2 filled workbook")
    parser.add_argument("--output", required=True, help="Merged filled workbook")
    args = parser.parse_args()
    merge(args.base, args.agent1, args.agent2, args.output)


if __name__ == "__main__":
    main()
