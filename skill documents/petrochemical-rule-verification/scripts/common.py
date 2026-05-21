from __future__ import annotations

import re
from copy import copy
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

MASK_COLUMNS = [
    "规则内容mask1",
    "关键字段mask1",
    "填空内容mask1",
    "原文内容mask1",
    "人工核验mask1",
    "规则内容mask2",
    "关键字段mask2",
    "填空内容mask2",
    "原文内容mask2",
    "人工核验mask2",
]

HIDDEN_FROM_AGENTS = {"规则内容", "原文内容", "JSON", "备注"}

NUMERIC_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:[≤≥<>]=?|不超过|不低于|低于|高于|大于|小于|超过|控制在|提前|滞后)?\s*"
    r"(?:\d+(?:\.\d+)?\s*(?:%|℃|°C|MPa|kPa|Pa|bar|mbar|t/h|吨/小时|Nm\s*³/m\s*³|Nm3/m3|mol/mol|dL/g|h|小时|天|分钟|min|m3/h|m³/h)?"
    r"(?:\s*[-~至—]\s*\d+(?:\.\d+)?\s*(?:%|℃|°C|MPa|kPa|Pa|bar|mbar|t/h|吨/小时|Nm\s*³/m\s*³|Nm3/m3|mol/mol|dL/g|h|小时|天|分钟|min|m3/h|m³/h)?)?)"
)

ACTION_TERMS = [
    "告知/请示程序", "告知义务", "请示程序", "报批", "审批", "停工", "开工", "切换", "降量", "升量",
    "降低处理量", "提高负荷", "降低负荷", "调整", "开启", "投用", "关闭", "置换", "预热", "升温", "降温",
    "补充原油", "开侧线", "放净存水", "大循环", "小循环", "闭路循环", "冲洗", "腾挪", "卡边",
]

YES = "是"
NO = "否"


def load_xlsx(path: str):
    return load_workbook(path)


def save_xlsx(wb, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def header_map(ws: Worksheet, header_row: int = 1) -> Dict[str, int]:
    mapping = {}
    for col in range(1, ws.max_column + 1):
        val = ws.cell(header_row, col).value
        if val is not None:
            mapping[str(val).strip()] = col
    return mapping


def is_rule_sheet(ws: Worksheet) -> bool:
    h = header_map(ws)
    return "规则内容" in h and "规则编号" in h


def copy_cell_style(src, dst):
    if src.has_style:
        dst._style = copy(src._style)
    if src.number_format:
        dst.number_format = src.number_format
    if src.alignment:
        dst.alignment = copy(src.alignment)
    if src.fill:
        dst.fill = copy(src.fill)
    if src.font:
        dst.font = copy(src.font)
    if src.border:
        dst.border = copy(src.border)


def clone_column_style(ws: Worksheet, source_col: int, target_col: int):
    source_letter = ws.cell(1, source_col).column_letter
    target_letter = ws.cell(1, target_col).column_letter
    ws.column_dimensions[target_letter].width = ws.column_dimensions[source_letter].width
    for row in range(1, ws.max_row + 1):
        copy_cell_style(ws.cell(row, source_col), ws.cell(row, target_col))


def normalize_header_order(ws: Worksheet):
    """Idempotently ensure mask columns after 规则内容 and 人工核对 after 原文内容."""
    h = header_map(ws)
    # Remove existing mask columns / 人工核对 to avoid duplicates.
    cols_to_delete = [idx for name, idx in h.items() if name in set(MASK_COLUMNS + ["人工核对"])]
    for idx in sorted(cols_to_delete, reverse=True):
        ws.delete_cols(idx, 1)

    h = header_map(ws)
    rule_col = h.get("规则内容")
    if not rule_col:
        return
    ws.insert_cols(rule_col + 1, len(MASK_COLUMNS))
    for offset, name in enumerate(MASK_COLUMNS, start=1):
        c = rule_col + offset
        ws.cell(1, c).value = name
        clone_column_style(ws, rule_col, c)

    h = header_map(ws)
    original_col = h.get("原文内容")
    json_col = h.get("JSON")
    if original_col and json_col:
        insert_col = original_col + 1
        ws.insert_cols(insert_col, 1)
        ws.cell(1, insert_col).value = "人工核对"
        clone_column_style(ws, original_col, insert_col)


def first_nonempty(iterable: Iterable[Optional[str]]) -> Optional[str]:
    for x in iterable:
        if x:
            return x
    return None


def choose_numeric_key(text: str) -> Optional[str]:
    if not text:
        return None
    candidates = [m.group(0).strip() for m in NUMERIC_PATTERN.finditer(text)]
    candidates = [c for c in candidates if re.search(r"\d", c)]
    if not candidates:
        return None
    # Prefer ranges / percentages / units over isolated integers.
    candidates.sort(key=lambda c: (bool(re.search(r"[-~至—]", c)), bool(re.search(r"%|℃|MPa|t/h|小时|天|Nm|mol|dL|mbar", c)), len(c)), reverse=True)
    return candidates[0]


def choose_semantic_key(text: str, numeric_key: Optional[str] = None) -> Optional[str]:
    if not text:
        return None
    for term in sorted(ACTION_TERMS, key=len, reverse=True):
        if term in text and term != numeric_key:
            return term
    # Fallback: choose a short noun/verb phrase around modal verbs.
    patterns = [
        r"应先([^，。；]+)", r"必须([^，。；]+)", r"需([^，。；]+)", r"不得([^，。；]+)",
        r"开启([^，。；]+)", r"投用([^，。；]+)", r"控制在([^，。；]+)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            val = m.group(1).strip()
            val = re.sub(r"^(进行|执行|按)", "", val)
            if val and val != numeric_key and len(val) <= 20:
                return val
    return None


def mask_text(text: str, key: Optional[str]) -> Optional[str]:
    if not text or not key:
        return None
    return text.replace(key, "____", 1)


def safe_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_text(value) -> str:
    s = safe_str(value)
    s = s.replace("％", "%").replace("℃", "℃").replace("°C", "℃")
    s = s.replace("～", "-").replace("~", "-").replace("—", "-").replace("至", "-")
    s = re.sub(r"\s+", "", s)
    s = s.replace("Nm³/m³", "Nm3/m3").replace("Nm³/m3", "Nm3/m3").replace("Nm3/m³", "Nm3/m3")
    return s.lower()


def extract_numbers(value) -> List[float]:
    s = normalize_text(value)
    nums = []
    for m in re.finditer(r"[-+]?\d+(?:\.\d+)?", s):
        try:
            nums.append(float(m.group(0)))
        except ValueError:
            pass
    # Convert simple percentage decimal equivalence: 0.45 can mean 45%.
    return nums


def has_percent(value) -> bool:
    return "%" in safe_str(value)


def numeric_equivalent(expected, actual) -> bool:
    e_nums = extract_numbers(expected)
    a_nums = extract_numbers(actual)
    if not e_nums or not a_nums:
        return False
    if len(e_nums) != len(a_nums):
        return False
    pairs = zip(e_nums, a_nums)
    for e, a in pairs:
        if abs(e - a) <= 1e-9:
            continue
        if has_percent(expected) and not has_percent(actual) and abs(e / 100.0 - a) <= 1e-9:
            continue
        if has_percent(actual) and not has_percent(expected) and abs(e - a / 100.0) <= 1e-9:
            continue
        return False
    # Direction/range operator check.
    e_norm, a_norm = normalize_text(expected), normalize_text(actual)
    for bad_pair in [("≤", "≥"), ("不超过", "不低于"), ("低于", "高于"), ("小于", "大于")]:
        if bad_pair[0] in e_norm and bad_pair[1] in a_norm:
            return False
        if bad_pair[1] in e_norm and bad_pair[0] in a_norm:
            return False
    return True

SYNONYMS = [
    ("告知/请示程序", "告知义务"),
    ("告知/请示程序", "请示程序"),
    ("停工", "装置停工"),
    ("切换", "原油切换"),
    ("切换", "物料切换"),
    ("开启大循环", "投用塔底大循环流程"),
    ("大循环", "塔底大循环"),
]

ANTONYMS = [
    ("停工", "开工"), ("升温", "降温"), ("提高负荷", "降低负荷"),
    ("升量", "降量"), ("大循环", "小循环"), ("告知", "审批通过"),
    ("开启", "关闭"), ("投用", "停用"),
]


def semantic_equivalent(expected, actual) -> bool:
    e = normalize_text(expected)
    a = normalize_text(actual)
    if not e or not a:
        return False
    if e == a or e in a or a in e:
        return True
    for x, y in SYNONYMS:
        nx, ny = normalize_text(x), normalize_text(y)
        if (nx in e and ny in a) or (ny in e and nx in a):
            return True
    for x, y in ANTONYMS:
        nx, ny = normalize_text(x), normalize_text(y)
        if (nx in e and ny in a) or (ny in e and nx in a):
            return False
    return False


def needs_manual_check(expected, actual, evidence=None) -> str:
    expected_s = safe_str(expected)
    actual_s = safe_str(actual)
    evidence_s = safe_str(evidence)
    if not expected_s:
        return ""
    if not actual_s:
        return YES
    if "未找到" in evidence_s or "无法定位" in evidence_s or "无证据" in evidence_s:
        return YES
    if normalize_text(expected_s) == normalize_text(actual_s):
        return NO
    if numeric_equivalent(expected_s, actual_s):
        return NO
    if semantic_equivalent(expected_s, actual_s):
        return NO
    return YES
