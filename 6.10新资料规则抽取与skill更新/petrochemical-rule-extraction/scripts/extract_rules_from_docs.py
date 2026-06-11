#!/usr/bin/env python3
"""Extract five classes of petrochemical knowledge rules from parsed DOCX/PDF files.

This deterministic extractor is intended as a reusable baseline for the
petrochemical-rule-extraction skill. It prefers page-located Chinese DOCX files
created by pdf_to_chinese_docx.py, and falls back to text PDFs when no DOCX is
provided. It writes only extracted_rules.xls and five JSON files.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pdfplumber
import xlrd
from docx import Document
from xlutils.copy import copy as xl_copy


FIELDS = [
    "rule_id", "rule_name", "knowledge_type", "sub_type", "applicable_scope",
    "rule_content", "source_file", "locator", "evidence_text", "parameters",
    "devices", "operations", "conditions", "constraint_type", "notes",
]
PARAM_FIELDS = ["name", "value", "unit", "operator", "normalized_value", "normalized_unit"]
EXCEL_HEADERS = ["规则编号", "规则名称", "知识类型", "子类型", "适用范围", "规则内容", "来源文件", "具体页码", "原文内容", "JSON", "备注"]

SHEET_BY_TYPE = {
    "质量标准类": "1、质量标准规则",
    "工艺规范类": "2、工艺规范规则",
    "流程特征类": "3、流程特征规则",
    "操作规程类": "4、操作规程规则",
    "调度经验类": "5、调度经验规则",
}
JSON_BY_TYPE = {
    "质量标准类": "质量标准规则.json",
    "工艺规范类": "工艺规范规则.json",
    "流程特征类": "流程特征规则.json",
    "操作规程类": "操作规程规则.json",
    "调度经验类": "调度经验规则.json",
}
DEFAULT_TARGETS = {
    "质量标准类": 105,
    "工艺规范类": 155,
    "流程特征类": 105,
    "操作规程类": 125,
    "调度经验类": 135,
}

CN_KEYWORDS = {
    "质量标准类": ["质量", "指标", "标准", "规格", "硫", "氮", "密度", "粘度", "辛烷", "十六烷", "闪点", "凝点", "冰点", "馏程", "含量", "纯度", "汽油", "柴油", "航煤", "石脑油", "液化气", "乙烯", "丙烯", "合格", "ppm", "wt", "vol"],
    "工艺规范类": ["温度", "压力", "流量", "负荷", "反应器", "再生器", "催化剂", "分馏", "蒸馏", "加氢", "重整", "裂化", "焦化", "进料", "控制", "保持", "最大", "最小", "上限", "下限", "操作", "工艺", "转化率", "收率"],
    "流程特征类": ["原料", "进料", "产品", "物流", "物流", "馏分", "送至", "来自", "进入", "产物", "罐", "储存", "调合", "库存", "装置", "上游", "下游", "卸船", "输送", "流向"],
    "操作规程类": ["应", "必须", "需要", "不得", "严禁", "检查", "监测", "确认", "调整", "降低", "提高", "保持", "控制", "诊断", "故障", "异常", "启动", "停工", "切换", "清洗", "观察"],
    "调度经验类": ["调度", "计划", "优化", "目标", "约束", "成本", "库存", "延迟", "稳定", "安全", "异常", "风险", "决策", "可行", "负荷", "能力", "储罐", "船", "等待", "最小化", "平衡"],
}
EN_KEYWORDS = {
    "质量标准类": ["quality", "specification", "sulfur", "sulphur", "nitrogen", "octane", "cetane", "density", "viscosity", "rvp", "flash point", "pour point", "ppm", "wt%", "vol%", "gasoline", "diesel", "kerosene", "naphtha"],
    "工艺规范类": ["temperature", "pressure", "flow", "rate", "ratio", "conversion", "yield", "reactor", "regenerator", "catalyst", "distillation", "hydrogen", "capacity", "load", "operation", "control", "maintain"],
    "流程特征类": ["feedstock", "feed", "product", "stream", "fraction", "flow", "from", "to", "sent", "tank", "vessel", "unloading", "blend", "inventory"],
    "操作规程类": ["should", "must", "required", "before", "after", "check", "monitor", "diagnose", "troubleshoot", "corrective", "adjust", "maintain", "control"],
    "调度经验类": ["scheduling", "planning", "optimization", "objective", "constraint", "minimize", "cost", "inventory", "delay", "stable", "safe", "abnormal", "decision", "feasible"],
}
SUBTYPE_KEYWORDS = {
    "质量标准类": [
        ("原油质量标准", ["原油", "crude", "api", "盐", "salt"]),
        ("航煤燃料质量标准", ["航煤", "kerosene", "jet", "冰点", "烟点"]),
        ("汽油质量标准", ["汽油", "gasoline", "辛烷", "octane", "rvp"]),
        ("柴油质量标准", ["柴油", "diesel", "十六烷", "cetane"]),
        ("气体及化工产品质量标准", ["液化气", "乙烯", "丙烯", "lpg", "ethylene", "propylene"]),
        ("质量管控通用规则", ["质量", "规格", "specification", "quality"]),
    ],
    "工艺规范类": [
        ("催化装置负荷与运行模式规则", ["催化", "fcc", "再生器", "riser"]),
        ("加氢装置负荷与运行模式规则", ["加氢", "hydrogen", "hydrotreat"]),
        ("重整装置负荷与运行模式规则", ["重整", "reforming", "芳烃"]),
        ("常压装置负荷与运行模式规则", ["常压", "蒸馏", "distillation"]),
        ("焦化装置负荷与运行模式规则", ["焦化", "coking", "焦炭"]),
        ("变负荷约束规则", ["负荷", "能力", "load", "capacity"]),
    ],
    "流程特征类": [
        ("物料流向规则", ["进料", "产品", "物流", "送至", "feed", "product", "stream"]),
        ("常压装置协同规则", ["常压", "蒸馏", "distillation"]),
        ("催化装置协同规则", ["催化", "fcc"]),
        ("加氢装置协同规则", ["加氢", "hydrogen"]),
        ("中间罐区缓冲与调合协同规则", ["罐", "库存", "调合", "tank", "blend", "inventory"]),
    ],
    "操作规程类": [
        ("催化装置操作规程", ["催化", "fcc", "再生器"]),
        ("常压装置操作规程", ["常压", "蒸馏", "分馏"]),
        ("航煤加氢装置操作规程", ["航煤", "加氢"]),
        ("汽油柴油调和操作规程", ["汽油", "柴油", "调合"]),
        ("原料罐区操作规程", ["罐", "库存", "储存"]),
    ],
    "调度经验类": [
        ("物性平滑规则", ["稳定", "平稳", "smooth", "stable"]),
        ("负荷联动规则", ["负荷", "能力", "load", "capacity"]),
        ("操作频次规则", ["周期", "频次", "时间", "delay"]),
        ("安全边际规则", ["安全", "上限", "下限", "limit", "safe"]),
        ("库位平衡规则", ["库存", "储罐", "tank", "inventory"]),
        ("效益优先规则", ["成本", "效益", "目标", "cost", "objective"]),
        ("故障导向规则", ["故障", "异常", "diagnose", "troubleshoot"]),
        ("指标超差处理规则", ["超差", "规格", "specification", "质量"]),
    ],
}

DEVICE_TERMS = {
    "FCC装置": ["fcc", "催化裂化", "流化催化"],
    "再生器": ["再生器", "regenerator"],
    "反应器": ["反应器", "riser", "reactor"],
    "分馏塔": ["分馏", "fractionator", "column"],
    "常压蒸馏装置": ["常压", "原油蒸馏", "distillation"],
    "加氢装置": ["加氢", "hydrogen", "hydrotreat"],
    "重整装置": ["重整", "reforming"],
    "焦化装置": ["焦化", "coking"],
    "储罐/罐区": ["储罐", "罐", "tank", "storage", "inventory"],
    "炼厂调度系统": ["调度", "优化", "scheduling", "planning"],
    "调合系统": ["调合", "blend"],
}
OP_TERMS = {
    "控制": ["控制", "保持", "control", "maintain"],
    "监测": ["监测", "观察", "indicator", "monitor"],
    "调整": ["调整", "降低", "提高", "reduce", "increase", "adjust"],
    "诊断": ["诊断", "故障", "troubleshoot", "diagnose"],
    "切换": ["切换", "change", "switch"],
    "优化": ["优化", "最小化", "optimize", "minimize"],
    "调度": ["调度", "schedule"],
    "调合": ["调合", "blend"],
    "进料": ["进料", "feed"],
    "外送/流转": ["送至", "输送", "transfer", "flow"],
}
UNIT_RE = re.compile(r"(?P<op><=|>=|≤|≥|<|>|=|不超过|不小于|至少|最高|最低|约|为|在)?\s*(?P<val>\d+(?:\.\d+)?(?:\s*(?:-|–|—|~|～|至|to)\s*\d+(?:\.\d+)?)?)\s*(?P<unit>wt\s*%|vol\s*%|mol\s*%|%|°C|℃|K|bar|psi|kPa|MPa|Pa|ppm|ppb|h|hr|小时|分钟|min|天|day|days|m3/h|bbl/day|kg/m3|g/cm3|API|RON|MON)?", re.I)
PAGE_HEADING_RE = re.compile(r"^(?P<source>.+?\.pdf) \| page=(?P<page>\d+) \| (?P<method>.+)$")
FORBIDDEN_RULE_CONTENT_RE = re.compile(
    r"(针对|\.{3,}|…|page\s*=|\.pdf|\.docx|第\s*\d+\s*页|页\s*[:：]\s*\d+|"
    r"章\s*次\s*页\s*次|cid\s*:|1⁄4|�|礛||表\s*\d+[\-－—]?\d*|"
    r"\brange\b|关键指标)",
    re.I,
)
BAD_EVIDENCE_RE = re.compile(
    r"(cid\s*:|�|礛||章\s*次\s*页\s*次|A\.\s*结\s*论|B\.\s*结\s*论|"
    r"目录\s*\.{2,}|\.{4,}|…|中文\(简体\)|英语|第\s*\d+\s*页|页\s*[:：]\s*\d+)",
    re.I,
)
FOCUS_PATTERNS = [
    (r"温降.*脱氢环化|脱氢环化.*温降", "末级反应器温降与烷烃脱氢环化、加氢裂化热效应"),
    (r"反应再生.*控制变量|控制变量.*反应再生", "催化裂化反应再生控制变量"),
    (r"DCS|集散控制", "主要炼油装置集散控制系统"),
    (r"热联合|高热低用|能耗|换热", "装置热联合与能量利用"),
    (r"温降|温升|床层温度", "反应器温降或床层温度"),
    (r"脱氢环化", "烷烃脱氢环化反应"),
    (r"加氢裂化|加氧裂化", "加氢裂化反应"),
    (r"反应温度", "反应温度"),
    (r"空速", "空速"),
    (r"加氢深度", "加氢深度"),
    (r"剂油比", "剂油比"),
    (r"提升管出口温度", "提升管出口温度"),
    (r"再生器.*温度|密相温度", "再生器密相温度"),
    (r"分馏塔.*平稳|平稳控制", "分馏塔平稳控制"),
    (r"质量.*卡边|卡边控制", "产品质量卡边控制"),
    (r"催化剂.*活性|活性损失", "催化剂活性衰减补偿"),
    (r"催化剂.*再生|烧焦", "催化剂再生与烧焦控制"),
    (r"金属.*聚集|金属.*分散", "催化剂金属分散与聚集控制"),
    (r"软化点|针入度|针人度|延度|黏度|粘度", "沥青氧化产品软化点、黏度和针入度"),
    (r"硫含量|硫化物|硫醇|硫醇硫", "硫含量或硫化物质量指标"),
    (r"辛烷|RON|MON", "汽油辛烷值"),
    (r"十六烷", "柴油十六烷值"),
    (r"闪点", "闪点"),
    (r"凝点|冰点|倾点", "低温流动性指标"),
    (r"密度|API", "密度或API度"),
    (r"馏程|干点|终馏点", "馏程指标"),
    (r"蒸气压|RVP", "蒸气压指标"),
    (r"纯度", "产品纯度"),
    (r"收率|转化率", "收率或转化率"),
    (r"原油.*调度| crude .*schedul", "原油调度计划"),
    (r"库存|储罐|罐区", "储罐库存与库位平衡"),
    (r"船舶|卸船|码头", "码头卸船与原油接卸"),
    (r"调合|blend", "产品调合"),
    (r"进料|原料|feed", "进料组织"),
    (r"产品|product", "产品去向"),
    (r"物流|物料|stream|流向|送至|来自|进入", "物料流向"),
    (r"压力", "压力"),
    (r"流量", "流量"),
    (r"负荷|处理量|capacity|load", "装置负荷"),
    (r"液位|界位", "液位或界位"),
    (r"安全|爆炸|腐蚀|火灾|泄漏", "安全边界"),
    (r"故障|异常|诊断|troubleshoot", "异常诊断与处置"),
    (r"成本|效益|objective|目标", "成本效益优化"),
]


def clean(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_for_rule(text: str) -> str:
    text = clean(text)
    text = re.sub(r"\(cid[:：]?\s*\d+\)", "", text, flags=re.I)
    text = re.sub(r"cid[:：]?\s*\d+", "", text, flags=re.I)
    text = re.sub(r"\(编[:：]?\s*\d+\)", "", text)
    text = re.sub(r"中文\(简体\)|英语", "", text, flags=re.I)
    text = text.replace("针人度", "针入度").replace("装兽", "装置").replace("加氧裂化", "加氢裂化")
    text = text.replace("1⁄4", "=").replace("¼", "=").replace("…", "")
    text = re.sub(r"\.{3,}", "", text)
    text = re.sub(r"章\s*次\s*页\s*次", "", text)
    text = re.sub(r"[AB]\.\s*结\s*论\s*\.{0,}", "", text, flags=re.I)
    text = re.sub(r"第\s*\d+\s*[章节]\s*", "", text)
    text = re.sub(r"第\s*\d+\s*页|页\s*[:：]\s*\d+", "", text)
    text = re.sub(r"表\s*\d+\s*[\-－—]\s*\d+", "", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,，;；:：.。-–—")


def read_docx_blocks(path: Path) -> list[dict]:
    doc = Document(str(path))
    blocks: list[dict] = []
    current: dict | None = None
    buf: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        match = PAGE_HEADING_RE.match(text)
        if match:
            if current is not None:
                current["text"] = "\n".join(buf).strip()
                blocks.append(current)
            current = {
                "source_file": match.group("source"),
                "locator": f"page={match.group('page')}",
                "method": match.group("method"),
                "docx_file": path.name,
            }
            buf = []
            continue
        if current is None:
            continue
        if text.startswith("translation_method="):
            continue
        if text == "原文：":
            continue
        buf.append(text)
    if current is not None:
        current["text"] = "\n".join(buf).strip()
        blocks.append(current)
    return [b for b in blocks if b.get("text")]


def read_pdf_blocks(path: Path) -> list[dict]:
    blocks = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            if text.strip():
                blocks.append({"source_file": path.name, "locator": f"page={i}", "method": "pdf_text", "text": text})
    return blocks


def split_candidates(text: str) -> list[str]:
    text = clean(text)
    parts = re.split(r"(?<=[.;:?!。；])\s+|\s+•\s+|\n+", text)
    out = []
    for part in parts:
        s = part.strip(" -–—•\t")
        if len(s) < 35:
            continue
        if len(s) > 520:
            chunks = re.split(r"(?<=[,，])\s*", s)
            buf = ""
            for chunk in chunks:
                if len(buf) + len(chunk) <= 430:
                    buf = (buf + chunk).strip()
                else:
                    if len(buf) >= 35:
                        out.append(buf)
                    buf = chunk
            if len(buf) >= 35:
                out.append(buf)
        else:
            out.append(s)
    return out


def score_category(text: str, category: str) -> int:
    low = text.lower()
    score = 0
    for kw in CN_KEYWORDS[category]:
        if kw in text:
            score += 2
    for kw in EN_KEYWORDS[category]:
        if kw in low:
            score += 1
    if UNIT_RE.search(text):
        score += 2
    if re.search(r"(应|必须|不得|严禁|控制|保持|上限|下限|约束|should|must|required|limit|control|maintain)", text, re.I):
        score += 2
    return score


def choose_subtype(category: str, text: str) -> str:
    low = text.lower()
    best, best_score = None, -1
    for subtype, kws in SUBTYPE_KEYWORDS[category]:
        score = sum(1 for kw in kws if kw in text or kw in low)
        if score > best_score:
            best, best_score = subtype, score
    if best_score <= 0:
        return {
            "质量标准类": "其他质量标准规则",
            "工艺规范类": "其他工艺约束规则",
            "流程特征类": "其他流程特征规则",
            "操作规程类": "其他操作规程规则",
            "调度经验类": "其他调度经验规则",
        }[category]
    return best or "其他规则"


def terms_from_map(text: str, mapping: dict[str, list[str]], default: str) -> list[str]:
    low = text.lower()
    vals = [name for name, kws in mapping.items() if any(kw in text or kw in low for kw in kws)]
    return vals[:4] or [default]


def extract_params(text: str) -> list[dict]:
    params = []
    seen = set()
    for m in UNIT_RE.finditer(text):
        val = (m.group("val") or "").strip()
        unit = (m.group("unit") or "").replace(" ", "")
        unit_map = {
            "°c": "°C", "℃": "°C", "k": "K", "bar": "bar", "psi": "psi",
            "kpa": "kPa", "mpa": "MPa", "pa": "Pa", "ppm": "ppm", "ppb": "ppb",
            "h": "h", "hr": "h", "min": "min", "day": "day", "days": "day",
            "wt%": "wt%", "vol%": "vol%", "mol%": "mol%",
        }
        unit = unit_map.get(unit.lower(), unit)
        op = (m.group("op") or "").strip() or "按"
        if not unit:
            context = text[max(0, m.start() - 18):m.end() + 18]
            if not re.search(r"%|℃|ppm|压力|温度|负荷|含量|API|RON|MON|bar|MPa|kPa", context, re.I):
                continue
        key = (val, unit, op)
        if key in seen:
            continue
        seen.add(key)
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", val)]
        if len(nums) >= 2 and re.search(r"-|–|—|~|～|至|to", val):
            norm = [int(x) if x.is_integer() else x for x in nums[:2]]
            operator = "range"
        elif nums:
            norm = int(nums[0]) if nums[0].is_integer() else nums[0]
            operator = {"不超过": "≤", "不小于": "≥", "最高": "≤", "最低": "≥", "<=": "≤", ">=": "≥"}.get(op, op)
        else:
            norm = val
            operator = op
        name = "关键指标"
        if unit in {"bar", "psi", "kPa", "MPa", "Pa"} or "压力" in text[max(0, m.start()-20):m.end()+20]:
            name = "压力"
        elif unit in {"°C", "K"} or "温度" in text[max(0, m.start()-20):m.end()+20]:
            name = "温度"
        elif unit in {"h", "hr", "小时", "分钟", "min", "天", "day", "days"}:
            name = "时间/周期"
        params.append({"name": name, "value": val, "unit": unit, "operator": operator, "normalized_value": norm, "normalized_unit": unit})
        if len(params) >= 6:
            break
    return params


def short_text(text: str, max_len: int = 56) -> str:
    text = clean_for_rule(text)
    text = re.sub(r"^[,，;；:：.。\-–—\s]+", "", text)
    text = re.sub(r"[,，;；:：.。\-–—\s]+$", "", text)
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip(",，;；:：.。 ")


def normalize_content_key(text: str) -> str:
    return re.sub(r"\W+", "", text.lower())


def unique_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        item = item.strip(" ,，;；:：.。")
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def topic_from_evidence(text: str, category: str, subtype: str, devices: list[str], params: list[dict]) -> str:
    text = clean_for_rule(text)
    labels = [label for pattern, label in FOCUS_PATTERNS if re.search(pattern, text, re.I)]
    labels = unique_keep_order(labels)
    if labels:
        return "、".join(labels[:2])

    param_names = unique_keep_order([p["name"] for p in params if p.get("name") and p["name"] != "关键指标"])
    if param_names:
        return "、".join(param_names[:2])

    domain_terms = []
    for term in [
        "原油", "汽油", "柴油", "航煤", "石脑油", "液化气", "乙烯", "丙烯", "聚乙烯", "聚丙烯",
        "常压蒸馏", "催化裂化", "加氢", "重整", "焦化", "芳烃", "烯烃", "聚酯", "纺丝",
        "反应器", "再生器", "分馏塔", "储罐", "罐区", "调合", "库存", "负荷", "质量", "安全",
    ]:
        if term in text:
            domain_terms.append(term)
    domain_terms.extend(devices)
    domain_terms = unique_keep_order(domain_terms)
    if domain_terms:
        return "、".join(domain_terms[:3])

    return subtype.replace("规则", "").replace("类", "")


def rule_angle_from_evidence(text: str, category: str) -> str:
    text = clean_for_rule(text)
    angle_patterns = [
        (r"当|若|如果|发生|出现|异常|故障|超差", "触发条件"),
        (r"提高|降低|增加|减少|调整|切换|补偿", "调整方向"),
        (r"上限|下限|最大|最小|不超过|不小于|范围|窗口|limit", "边界控制"),
        (r"先|然后|之后|前|后|确认|检查|监测", "步骤顺序"),
        (r"送至|来自|进入|外送|输送|流向|上游|下游", "流向衔接"),
        (r"库存|储罐|罐区|船舶|卸船|等待", "库存与接卸平衡"),
        (r"成本|效益|目标|优化|最小化|objective", "优化目标"),
        (r"稳定|平稳|波动|安全|风险", "稳定性与安全边界"),
    ]
    for pattern, label in angle_patterns:
        if re.search(pattern, text, re.I):
            return label
    return {
        "质量标准类": "质量边界",
        "工艺规范类": "运行窗口",
        "流程特征类": "流程协同",
        "操作规程类": "操作确认",
        "调度经验类": "调度约束",
    }[category]


def param_desc_from(params: list[dict], topic: str) -> str:
    items = []
    for p in params[:3]:
        name = p.get("name") or "关键指标"
        unit = p.get("unit") or ""
        value = p.get("value") or ""
        operator = p.get("operator") or ""
        if not value:
            continue
        if not unit and operator not in {"≤", "≥", "<", ">", "=", "不超过", "不小于"}:
            continue
        if name == "关键指标":
            if unit in {"%", "wt%", "vol%", "mol%", "ppm", "ppb"}:
                name = "含量/比例"
            elif unit in {"bar", "psi", "kPa", "MPa", "Pa"}:
                name = "压力"
            elif unit in {"°C", "K"}:
                name = "温度"
            else:
                continue
        value_text = re.sub(r"\s+", "", value)
        if operator == "range":
            operator_text = "范围"
        elif operator == "按":
            operator_text = ""
        else:
            operator_text = operator
        items.append(f"{name}{operator_text}{value_text}{unit}")
    if items:
        return "、".join(items)
    if any(word in topic for word in ["温度", "温降", "热效应"]):
        return "温度、温降和反应热效应"
    if any(word in topic for word in ["库存", "库位", "储罐"]):
        return "库存、库位和物料平衡"
    if any(word in topic for word in ["流向", "进料", "产品"]):
        return "进料、产品去向和上下游能力"
    if any(word in topic for word in ["安全", "异常", "故障"]):
        return "安全边界、异常状态和处置条件"
    return "控制指标和约束条件"


def make_scope(category: str, devices: list[str]) -> str:
    dev = devices[0] if devices else "炼油生产系统"
    return {
        "质量标准类": f"{dev}原料/中间物料/产品质量控制场景",
        "工艺规范类": f"{dev}工艺运行与参数控制场景",
        "流程特征类": f"{dev}上下游物料流向与协同调度场景",
        "操作规程类": f"{dev}操作调整、监测确认或异常处置场景",
        "调度经验类": f"{dev}调度优化、异常诊断与平稳运行场景",
    }[category]


def make_content(category: str, subtype: str, scope: str, devices: list[str], ops: list[str], params: list[dict], evidence_text: str) -> tuple[str, str]:
    topic = topic_from_evidence(evidence_text, category, subtype, devices, params)
    angle = rule_angle_from_evidence(evidence_text, category)
    param_desc = param_desc_from(params, topic)
    dev_desc = "、".join(devices[:3])
    op_desc = "、".join(ops[:4])
    if "末级反应器温降" in topic:
        return f"末级反应器温降应作为重整反应分布和热效应判断依据；控制{param_desc}时，应关注烷烃脱氢环化与加氢裂化反应转化率低、热效应相反对温度窗口的影响，避免仅按前级反应器温降外推末级运行状态。", "工艺参数/运行边界约束"
    if category == "质量标准类":
        return f"{topic}应纳入{scope}的质量边界管理；{dev_desc}相关物料或产品应满足{param_desc}，调度、调合或外送前应完成规格校核，避免超标物料按合格品流转。", "质量指标约束"
    if category == "工艺规范类":
        return f"{topic}是{scope}的{angle}对象；{dev_desc}执行{op_desc}时，应将{param_desc}控制在规定运行窗口内，避免装置偏离安全、稳定和可操作边界。", "工艺参数/运行边界约束"
    if category == "流程特征类":
        return f"{topic}应作为{scope}的流程协同约束；{dev_desc}之间的进料、产物、储罐或装置衔接关系应保持一致，发生负荷、配方或库存变化时同步校核上下游能力和物料去向。", "流程流向与协同约束"
    if category == "操作规程类":
        return f"{topic}操作应遵循{scope}的{angle}要求；执行{op_desc}前应确认状态和操作条件，涉及{param_desc}时应在操作前后复核并记录异常变化。", "操作步骤/确认约束"
    return f"{topic}应转化为{scope}的调度约束；编制或调整排程时应同时考虑{param_desc}、库存负荷、成本效益和异常诊断信息，优先保证计划可执行、运行平稳并降低安全和经济风险。", "调度经验约束"


def make_name(category: str, devices: list[str], params: list[dict]) -> str:
    dev = (devices[0] if devices else "炼油系统").replace("/", "")
    param = params[0]["name"] if params else {"质量标准类": "质量指标", "工艺规范类": "运行参数", "流程特征类": "物料协同", "操作规程类": "操作确认", "调度经验类": "调度策略"}[category]
    suffix = {"质量标准类": "控制规则", "工艺规范类": "约束规则", "流程特征类": "协同规则", "操作规程类": "操作规则", "调度经验类": "经验规则"}[category]
    return f"{dev}{param}{suffix}"


def next_id(category: str, subtype: str, counters: Counter) -> str:
    counters[(category, subtype)] += 1
    n = counters[(category, subtype)]
    if category == "工艺规范类":
        total = sum(v for (cat, _), v in counters.items() if cat == category)
        return f"R1-{total:03d}"
    prefix_map = {
        "质量标准类": defaultdict(lambda: "QS-OTH", {"原油质量标准": "QS-RAW", "航煤燃料质量标准": "QS-JET", "汽油质量标准": "QS-GAS", "柴油质量标准": "QS-DIE", "气体及化工产品质量标准": "QS-CHE", "质量管控通用规则": "QS-QMG"}),
        "流程特征类": defaultdict(lambda: "FLOW-OTH", {"物料流向规则": "FLOW-MAT", "常压装置协同规则": "FLOW-ATM", "催化装置协同规则": "FLOW-FCC", "加氢装置协同规则": "FLOW-HYD", "中间罐区缓冲与调合协同规则": "FLOW-TNK"}),
        "操作规程类": defaultdict(lambda: "SOP-OTH", {"催化装置操作规程": "SOP-FCC", "常压装置操作规程": "SOP-ATM", "航煤加氢装置操作规程": "SOP-JET", "汽油柴油调和操作规程": "SOP-BLD", "原料罐区操作规程": "SOP-TNK"}),
        "调度经验类": defaultdict(lambda: "EXP-OTH", {"物性平滑规则": "EXP-SMO", "负荷联动规则": "EXP-LNK", "操作频次规则": "EXP-FRQ", "安全边际规则": "EXP-SAF", "库位平衡规则": "EXP-TNK", "效益优先规则": "EXP-BEN", "故障导向规则": "EXP-FLT", "指标超差处理规则": "EXP-DEV"}),
    }
    return f"{prefix_map[category][subtype]}-{n:03d}"


def build_candidates(input_dir: Path) -> tuple[list[dict], list[str], list[str]]:
    parsed_docx = input_dir / "rule_output" / "parsed_docx"
    candidates = []
    parsed_files, failed_files = [], []
    if parsed_docx.exists():
        for docx_path in sorted(parsed_docx.glob("*.docx")):
            blocks = read_docx_blocks(docx_path)
            if blocks:
                parsed_files.append(docx_path.name)
            for block in blocks:
                for sent in split_candidates(block["text"]):
                    scores = {cat: score_category(sent, cat) for cat in DEFAULT_TARGETS}
                    if max(scores.values()) >= 4:
                        candidates.append({**block, "text": sent, "scores": scores})
    else:
        for pdf_path in sorted(input_dir.glob("*.pdf")):
            try:
                blocks = read_pdf_blocks(pdf_path)
                if blocks:
                    parsed_files.append(pdf_path.name)
                else:
                    failed_files.append(pdf_path.name)
                for block in blocks:
                    for sent in split_candidates(block["text"]):
                        scores = {cat: score_category(sent, cat) for cat in DEFAULT_TARGETS}
                        if max(scores.values()) >= 4:
                            candidates.append({**block, "text": sent, "scores": scores})
            except Exception:
                failed_files.append(pdf_path.name)
    return candidates, parsed_files, failed_files


def select_rules(candidates: list[dict], targets: dict[str, int]) -> dict[str, list[dict]]:
    selected = {cat: [] for cat in targets}
    used_evidence = set()
    used_contents = set()
    counters: Counter = Counter()
    for category, target in targets.items():
        ranked = sorted(candidates, key=lambda c: (c["scores"][category], sum(c["scores"].values()), -len(c["text"])), reverse=True)
        per_source = Counter()
        for c in ranked:
            if len(selected[category]) >= target:
                break
            if c["scores"][category] < 4:
                continue
            norm = re.sub(r"\W+", "", c["text"].lower())[:180]
            if norm in used_evidence:
                continue
            if per_source[c["source_file"]] >= math.ceil(target * 0.60) and len(selected[category]) < target * 0.85:
                continue
            text = clean_for_rule(c["text"])
            if len(text) < 35 or BAD_EVIDENCE_RE.search(text):
                continue
            subtype = choose_subtype(category, text)
            devices = terms_from_map(text, DEVICE_TERMS, "炼油生产系统")
            ops = terms_from_map(text, OP_TERMS, {"质量标准类": "质量控制", "工艺规范类": "工艺控制", "流程特征类": "物料协同", "操作规程类": "操作确认", "调度经验类": "调度优化"}[category])
            params = extract_params(text)
            scope = make_scope(category, devices)
            content, ctype = make_content(category, subtype, scope, devices, ops, params, text)
            if FORBIDDEN_RULE_CONTENT_RE.search(content):
                continue
            content_key = normalize_content_key(content)
            if content_key in used_contents:
                continue
            used_evidence.add(norm)
            used_contents.add(content_key)
            per_source[c["source_file"]] += 1
            evidence = text[:417] + "..." if len(text) > 420 else text
            rid = next_id(category, subtype, counters)
            notes = f"由{c.get('docx_file', c['source_file'])}按页解析文本归纳"
            rule = {
                "rule_id": rid,
                "rule_name": make_name(category, devices, params),
                "knowledge_type": category,
                "sub_type": subtype,
                "applicable_scope": scope,
                "rule_content": content,
                "source_file": c["source_file"],
                "locator": c["locator"],
                "evidence_text": evidence,
                "parameters": params,
                "devices": devices,
                "operations": ops,
                "conditions": [scope],
                "constraint_type": ctype,
                "notes": notes,
            }
            selected[category].append(rule)
    return selected


def validate(selected: dict[str, list[dict]], min_rules: int) -> None:
    total = sum(len(v) for v in selected.values())
    if total < min_rules:
        raise ValueError(f"Only {total} rules extracted; required {min_rules}")
    content_keys = Counter()
    for rules in selected.values():
        for rule in rules:
            if list(rule.keys()) != FIELDS:
                raise ValueError(f"Bad fields: {rule.get('rule_id')}")
            if not rule["source_file"] or not rule["evidence_text"]:
                raise ValueError(f"Missing evidence: {rule.get('rule_id')}")
            if FORBIDDEN_RULE_CONTENT_RE.search(rule["rule_content"]):
                raise ValueError(f"Bad rule_content text: {rule.get('rule_id')}")
            content_key = normalize_content_key(rule["rule_content"])
            content_keys[content_key] += 1
            for param in rule["parameters"]:
                if list(param.keys()) != PARAM_FIELDS:
                    raise ValueError(f"Bad parameter fields: {rule['rule_id']}")
    duplicate_contents = [key for key, count in content_keys.items() if count > 1]
    if duplicate_contents:
        raise ValueError(f"{len(duplicate_contents)} duplicate rule_content values found")


def write_outputs(selected: dict[str, list[dict]], output_dir: Path, template_xls: Path, backup_existing: bool) -> None:
    if output_dir.exists() and backup_existing:
        backup = output_dir.parent / f"{output_dir.name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir.rename(backup)
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_xls, output_dir / "extracted_rules.xls")
    for category, filename in JSON_BY_TYPE.items():
        (output_dir / filename).write_text(json.dumps(selected[category], ensure_ascii=False, indent=2), encoding="utf-8")
    rb = xlrd.open_workbook(str(output_dir / "extracted_rules.xls"), formatting_info=True)
    wb = xl_copy(rb)
    sheet_names = rb.sheet_names()
    for category, sheet_name in SHEET_BY_TYPE.items():
        ws = wb.get_sheet(sheet_names.index(sheet_name))
        for col, header in enumerate(EXCEL_HEADERS):
            ws.write(0, col, header)
        for row_idx, rule in enumerate(selected[category], start=1):
            row = [rule["rule_id"], rule["rule_name"], rule["knowledge_type"], rule["sub_type"], rule["applicable_scope"], rule["rule_content"], rule["source_file"], rule["locator"], rule["evidence_text"], json.dumps(rule, ensure_ascii=False), rule["notes"]]
            for col, value in enumerate(row):
                ws.write(row_idx, col, value)
    wb.save(str(output_dir / "extracted_rules.xls"))


def parse_targets(spec: str, min_rules: int) -> dict[str, int]:
    targets = DEFAULT_TARGETS.copy()
    if spec:
        for part in spec.split(","):
            if not part.strip():
                continue
            k, v = part.split("=", 1)
            targets[k.strip()] = int(v)
    if sum(targets.values()) < min_rules:
        extra = min_rules - sum(targets.values())
        targets["工艺规范类"] += extra
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract five classes of petrochemical rules from parsed DOCX/PDF files.")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--template-xls", type=Path, default=Path("/Users/xiluo/.codex/skills/petrochemical-rule-extraction/templates/rule_summary_template.xls"))
    parser.add_argument("--min-rules", type=int, default=500)
    parser.add_argument("--targets", default="")
    parser.add_argument("--backup-existing", action="store_true")
    args = parser.parse_args()

    targets = parse_targets(args.targets, args.min_rules)
    candidates, parsed_files, failed_files = build_candidates(args.input_dir)
    selected = select_rules(candidates, targets)
    validate(selected, args.min_rules)
    write_outputs(selected, args.output_dir, args.template_xls, args.backup_existing)
    summary = {
        "candidate_count": len(candidates),
        "parsed_files": parsed_files,
        "failed_or_empty_files": failed_files,
        "rule_counts": {cat: len(rules) for cat, rules in selected.items()},
        "total_rules": sum(len(rules) for rules in selected.values()),
        "duplicate_rule_content_count": 0,
        "output_files": sorted(p.name for p in args.output_dir.iterdir() if p.is_file()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
