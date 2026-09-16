#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute rule-coverage gaps after table-first or final phase.

Counts unique emitted rules by target_group_id from extraction_manifest.json and
compares them with config/rule_count_baseline_v3.json. Exact targets can close a
rule group for generation. Approximate/ambiguous targets remain advisory.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"


def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def actual_rule_ids(rules_dir: Path) -> set[str]:
    catalog = load_json(CONFIG / "eight_category_catalog.json")
    ids: set[str] = set()
    for c in catalog["categories"]:
        p = rules_dir / c["file"]
        if not p.exists():
            continue
        data = load_json(p)
        if isinstance(data, list):
            for r in data:
                if isinstance(r, dict) and isinstance(r.get("rule_id"), str):
                    ids.add(r["rule_id"])
    return ids


def target_display(t: dict) -> str:
    kind = t.get("kind")
    if kind in {"exact", "advisory_exact", "approx"}:
        prefix = "约" if kind == "approx" else ""
        return f"{prefix}{t.get('value')}"
    if kind in {"interval", "approx_interval"}:
        prefix = "约" if kind == "approx_interval" else ""
        return f"{prefix}{t.get('min')}–{t.get('max')}"
    return "未明确"


def compute_gap(baseline: dict, manifest: dict, emitted_ids: set[str], phase: str | None) -> dict:
    audit = manifest.get("audit_records", []) if isinstance(manifest, dict) else []
    records=[]
    for a in audit:
        if not isinstance(a, dict):
            continue
        rid=a.get("rule_id")
        if rid not in emitted_ids:
            continue
        if phase and a.get("extraction_phase") != phase:
            continue
        if a.get("validation_status") not in {None, "PASS", "REVIEW"}:
            continue
        records.append(a)

    # Unique by rule_id. Upstream workflow should already deduplicate identities.
    by_group: dict[str, set[str]] = {}
    by_cat: dict[str, set[str]] = {}
    unassigned=[]
    for a in records:
        rid=a.get("rule_id"); big=a.get("big_category"); gid=a.get("target_group_id")
        if big:
            by_cat.setdefault(big,set()).add(rid)
        if gid:
            by_group.setdefault(gid,set()).add(rid)
        else:
            unassigned.append(rid)

    category_summary=[]
    for big,meta in baseline.get("category_targets",{}).items():
        target=meta.get("target_count")
        count=len(by_cat.get(big,set()))
        category_summary.append({
            "big_category":big,
            "target_count":target,
            "extracted_unique":count,
            "difference_to_target":None if not isinstance(target,(int,float)) else target-count,
            "control_reached":bool(isinstance(target,(int,float)) and count>=target),
            "note":meta.get("note","")
        })

    groups=[]
    for g in baseline.get("target_groups",[]):
        gid=g["target_group_id"]; t=g.get("target",{}); count=len(by_group.get(gid,set()))
        kind=t.get("kind")
        remaining=None; remaining_range=None; closed=False; supplement=True
        if kind=="exact":
            remaining=max(int(t.get("value",0))-count,0)
            closed=remaining==0
            supplement=remaining>0
        elif kind=="advisory_exact":
            remaining=max(int(t.get("value",0))-count,0)
            supplement=remaining>0
        elif kind=="approx":
            remaining=max(int(t.get("value",0))-count,0)
            supplement=count<int(t.get("value",0))
        elif kind in {"interval","approx_interval"}:
            lo=int(t.get("min",0)); hi=int(t.get("max",0))
            remaining_range=[max(lo-count,0),max(hi-count,0)]
            supplement=count<lo
        elif kind=="unspecified":
            supplement=count==0
        groups.append({
            "target_group_id":gid,
            "big_category":g.get("big_category"),
            "source_subcategory":g.get("source_subcategory"),
            "normalized_subcategories":g.get("normalized_subcategories",[]),
            "target_kind":kind,
            "target_display":target_display(t),
            "target_count":t.get("value"),
            "target_min":t.get("min"),
            "target_max":t.get("max"),
            "extracted_unique":count,
            "remaining_count":remaining,
            "remaining_range":remaining_range,
            "closed_for_generation":closed,
            "supplement_needed_by_count":supplement,
            "planning_rule":g.get("planning_rule",""),
            "notes":g.get("source_note","")
        })

    return {
        "phase": phase or "all_emitted",
        "total_emitted_counted":len({a.get('rule_id') for a in records if a.get('rule_id')}),
        "unassigned_rule_ids":sorted(set(unassigned)),
        "category_summary":category_summary,
        "target_groups":groups,
        "important_note":"remaining只用于补缺计划；approx/interval/unspecified不得作为凑数依据。coverage slots和实体粒度优先于纯数量。"
    }


def write_md(result: dict, out: Path) -> None:
    lines=["# 剩余规则补缺计划","",f"统计阶段：`{result['phase']}`","",
           "## 1. 大类覆盖","","| 大类 | 目标控制线 | 已提取唯一规则 | 与目标差 | 达到控制线 |","|---|---:|---:|---:|---|"]
    for x in result["category_summary"]:
        lines.append(f"| {x['big_category']} | {x['target_count']} | {x['extracted_unique']} | {x['difference_to_target']} | {'是' if x['control_reached'] else '否'} |")
    lines += ["","## 2. Target group 缺口","","| target_group | 大类 | 子类/组 | 目标 | 已提取 | 剩余 | 关闭新增 | 文档补缺 |","|---|---|---|---:|---:|---:|---|---|"]
    for g in result["target_groups"]:
        rem = g['remaining_count'] if g['remaining_count'] is not None else ("–".join(map(str,g['remaining_range'])) if g['remaining_range'] is not None else "未明确")
        subs="、".join(g['normalized_subcategories'])
        lines.append(f"| {g['target_group_id']} | {g['big_category']} | {subs} | {g['target_display']} | {g['extracted_unique']} | {rem} | {'是' if g['closed_for_generation'] else '否'} | {'需要' if g['supplement_needed_by_count'] else '数量上不需要'} |")
    if result["unassigned_rule_ids"]:
        lines += ["","## 3. 未绑定 target_group 的规则","",*[f"- {x}" for x in result['unassigned_rule_ids']]]
    lines += ["","## 4. 执行要求","",
              "- exact且已关闭的group：DOCX/PDF/MD只能复核，不再新增规则。",
              "- approx/interval/unspecified：结合coverage slots与证据判断，不凑数。",
              "- 文档补缺必须只针对本计划中的未覆盖子类/实体槽位。",
              "- 同identity重复证据合并；不同值进入conflict/revision。",""]
    out.write_text("\n".join(lines),encoding="utf-8")


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--rules-dir",required=True,type=Path)
    ap.add_argument("--manifest",required=True,type=Path)
    ap.add_argument("--phase",default="table_first")
    ap.add_argument("--output-json",required=True,type=Path)
    ap.add_argument("--output-md",required=True,type=Path)
    args=ap.parse_args()
    baseline=load_json(CONFIG/"rule_count_baseline_v3.json")
    manifest=load_json(args.manifest)
    result=compute_gap(baseline,manifest,actual_rule_ids(args.rules_dir),args.phase or None)
    args.output_json.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    write_md(result,args.output_md)
    print(json.dumps({"phase":result["phase"],"total_emitted_counted":result["total_emitted_counted"],"unassigned":len(result["unassigned_rule_ids"])},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
