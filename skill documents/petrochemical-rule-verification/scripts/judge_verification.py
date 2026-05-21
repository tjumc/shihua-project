#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from common import NO, YES, header_map, is_rule_sheet, load_xlsx, needs_manual_check, save_xlsx, safe_str


def judge(input_path: str, output_path: str, report_path: str):
    wb = load_xlsx(input_path)
    stats = Counter()
    examples = []
    for ws in wb.worksheets:
        if not is_rule_sheet(ws):
            continue
        h = header_map(ws)
        for row in range(2, ws.max_row + 1):
            rid = safe_str(ws.cell(row, h.get("规则编号", 1)).value)
            if not rid:
                continue
            row_flags = []
            for suffix in ["1", "2"]:
                key_col = f"关键字段mask{suffix}"
                fill_col = f"填空内容mask{suffix}"
                ev_col = f"原文内容mask{suffix}"
                flag_col = f"人工核验mask{suffix}"
                if key_col not in h or flag_col not in h:
                    continue
                expected = ws.cell(row, h[key_col]).value
                actual = ws.cell(row, h[fill_col]).value if fill_col in h else None
                evidence = ws.cell(row, h[ev_col]).value if ev_col in h else None
                flag = needs_manual_check(expected, actual, evidence)
                ws.cell(row, h[flag_col]).value = flag
                if flag:
                    row_flags.append(flag)
                    stats[f"mask{suffix}_{flag}"] += 1
            final = YES if YES in row_flags else (NO if row_flags else "")
            if "人工核对" in h:
                ws.cell(row, h["人工核对"]).value = final
            stats[f"final_{final or 'blank'}"] += 1
            if final == YES and len(examples) < 20:
                examples.append((ws.title, rid, row))
    save_xlsx(wb, output_path)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 规则核验报告\n\n")
        f.write("## 汇总统计\n\n")
        for k, v in sorted(stats.items()):
            f.write(f"- {k}: {v}\n")
        if examples:
            f.write("\n## 需要人工核对的示例\n\n")
            for sheet, rid, row in examples:
                f.write(f"- {sheet} / {rid} / 第 {row} 行\n")


def main():
    parser = argparse.ArgumentParser(description="Judge mask-level and final manual verification flags.")
    parser.add_argument("--input", required=True, help="Filled workbook")
    parser.add_argument("--output", required=True, help="Verified workbook")
    parser.add_argument("--report", required=True, help="Markdown report path")
    args = parser.parse_args()
    judge(args.input, args.output, args.report)


if __name__ == "__main__":
    main()
