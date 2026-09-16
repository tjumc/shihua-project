#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Strict four-field validator for petrochemical knowledge-rule extraction."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config'
STRICT_FIELDS = ['rule_id','description','sets','parameters']
SET_FIELDS = ['set_name','subset_name','element']
PARAM_FIELDS = ['value','unit']
FORBIDDEN = {'type','category','subject','predicate','source','provenance','confidence','extraction_status','notes','subcategory'}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def catalog_maps(catalog: dict):
    file_to_big={c['file']:c['name'] for c in catalog['categories']}
    enabled={c['name']:set(c.get('enabled_subcategories',[])) for c in catalog['categories']}
    return file_to_big, enabled


def spec_map(spec: dict):
    return {(x['big_category'],x['subcategory']):x for x in spec.get('subcategories',[]) if x.get('enabled')}


def validate_rule(rule: Any, big: str, idx: int) -> list[dict]:
    issues=[]; where=f'{big}[{idx}]'
    if not isinstance(rule,dict):
        return [{'level':'ERROR','where':where,'message':'rule must be an object'}]
    missing=[k for k in STRICT_FIELDS if k not in rule]
    extra=[k for k in rule if k not in STRICT_FIELDS]
    if missing: issues.append({'level':'ERROR','where':where,'message':f'missing top-level fields: {missing}'})
    if extra: issues.append({'level':'ERROR','where':where,'message':f'forbidden extra top-level fields: {extra}'})
    if any(k in rule for k in FORBIDDEN):
        leaked=[k for k in rule if k in FORBIDDEN]
        issues.append({'level':'ERROR','where':where,'message':f'old/non-template metadata leaked into rule: {leaked}'})
    if missing: return issues

    rid=rule['rule_id']
    if not isinstance(rid,str) or not rid.strip(): issues.append({'level':'ERROR','where':where,'message':'rule_id must be non-empty string'})
    desc=rule['description']
    if not isinstance(desc,str) or not desc.strip(): issues.append({'level':'ERROR','where':where,'message':'description must be non-empty string'})
    elif 'DEMO' in desc or '格式示例' in desc or '非现场已核实规则' in desc:
        issues.append({'level':'ERROR','where':where,'message':'reference/DEMO wording leaked into field rule'})

    sets=rule['sets']
    if not isinstance(sets,list):
        issues.append({'level':'ERROR','where':where,'message':'sets must be an array'})
    else:
        for si,s in enumerate(sets):
            sw=f'{where}.sets[{si}]'
            if not isinstance(s,dict):
                issues.append({'level':'ERROR','where':sw,'message':'set item must be object'}); continue
            sm=[k for k in SET_FIELDS if k not in s]; se=[k for k in s if k not in SET_FIELDS]
            if sm: issues.append({'level':'ERROR','where':sw,'message':f'missing set fields: {sm}'})
            if se: issues.append({'level':'ERROR','where':sw,'message':f'extra set fields: {se}'})
            if sm: continue
            if not isinstance(s['set_name'],str) or not s['set_name'].strip(): issues.append({'level':'ERROR','where':sw,'message':'set_name must be non-empty string'})
            if s['subset_name'] is not None and not isinstance(s['subset_name'],str): issues.append({'level':'ERROR','where':sw,'message':'subset_name must be string or null'})
            if not isinstance(s['element'],str) or not s['element'].strip(): issues.append({'level':'ERROR','where':sw,'message':'element must be non-empty string'})
            elif 'DEMO' in s['element']: issues.append({'level':'ERROR','where':sw,'message':'DEMO entity leaked into field rule'})

    params=rule['parameters']
    if not isinstance(params,dict):
        issues.append({'level':'ERROR','where':where,'message':'parameters must be an object'})
    else:
        for pname,p in params.items():
            pw=f'{where}.parameters.{pname}'
            if not isinstance(pname,str) or not pname.strip(): issues.append({'level':'ERROR','where':pw,'message':'parameter name must be non-empty string'})
            if not isinstance(p,dict): issues.append({'level':'ERROR','where':pw,'message':'parameter item must be object'}); continue
            pm=[k for k in PARAM_FIELDS if k not in p]; pe=[k for k in p if k not in PARAM_FIELDS]
            if pm: issues.append({'level':'ERROR','where':pw,'message':f'missing parameter fields: {pm}'})
            if pe: issues.append({'level':'ERROR','where':pw,'message':f'extra parameter fields: {pe}'})
            if pm: continue
            if isinstance(p['value'],(dict,list)): issues.append({'level':'ERROR','where':pw,'message':'parameter value must be scalar'})
            if p['unit'] is not None and not isinstance(p['unit'],str): issues.append({'level':'ERROR','where':pw,'message':'unit must be string or null'})
    return issues


def validate_template_signature(rule: dict, big: str, subcategory: str, spec_lookup: dict, where: str) -> list[dict]:
    issues=[]
    sp=spec_lookup.get((big,subcategory))
    if not sp:
        return [{'level':'ERROR','where':where,'message':f'no enabled template spec for subcategory {subcategory!r}'}]
    expected=[x.get('set_name') for x in sp.get('set_signature',[])]
    actual=[x.get('set_name') for x in rule.get('sets',[]) if isinstance(x,dict)]
    if expected != actual:
        issues.append({'level':'ERROR','where':where,'message':f'sets set_name signature {actual} differs from 知识规则模版.md {expected}'})
    # subset_name is a semantic hint: some generic unit templates may validly switch Ucdu -> Up.
    for i,(exp,act) in enumerate(zip(sp.get('set_signature',[]),rule.get('sets',[]))):
        if not isinstance(act,dict): continue
        es=exp.get('subset_name'); a=act.get('subset_name')
        if es is not None and a != es:
            issues.append({'level':'WARNING','where':f'{where}.sets[{i}]','message':f'subset_name {a!r} differs from template example {es!r}; verify against symbol document and actual entity class'})
    return issues


def run_validation(rules_dir: Path, manifest_path: Path|None=None) -> dict:
    catalog=load_json(CONFIG/'eight_category_catalog.json')
    spec=load_json(CONFIG/'template_subcategory_spec.json')
    baseline=load_json(CONFIG/'rule_count_baseline_v3.json')
    valid_target_groups={x.get('target_group_id') for x in baseline.get('target_groups',[])}
    _,enabled=catalog_maps(catalog); spec_lookup=spec_map(spec)
    issues=[]; counts={}; all_ids={}; rules_by_id={}; big_by_id={}

    for c in catalog['categories']:
        path=rules_dir/c['file']; big=c['name']
        if not path.exists():
            issues.append({'level':'ERROR','where':big,'message':f'missing required JSON file: {path.name}'}); counts[big]=0; continue
        try: data=load_json(path)
        except Exception as e:
            issues.append({'level':'ERROR','where':big,'message':f'invalid JSON: {e}'}); counts[big]=0; continue
        if not isinstance(data,list):
            issues.append({'level':'ERROR','where':big,'message':'top-level JSON must be an array'}); counts[big]=0; continue
        counts[big]=len(data)
        for i,r in enumerate(data):
            issues.extend(validate_rule(r,big,i))
            if isinstance(r,dict) and isinstance(r.get('rule_id'),str):
                rid=r['rule_id']; rules_by_id[rid]=r; big_by_id[rid]=big
                if rid in all_ids: issues.append({'level':'ERROR','where':f'{big}[{i}]','message':f'duplicate rule_id {rid!r}; first seen at {all_ids[rid]}'})
                else: all_ids[rid]=f'{big}[{i}]'

    if manifest_path is not None:
        if not manifest_path.exists():
            issues.append({'level':'ERROR','where':'manifest','message':f'manifest not found: {manifest_path}'})
        else:
            try:
                manifest=load_json(manifest_path); audit=manifest.get('audit_records',[])
                audit_by_id={a.get('rule_id'):a for a in audit if isinstance(a,dict) and isinstance(a.get('rule_id'),str)}
                missing=sorted(set(rules_by_id)-set(audit_by_id)); orphan=sorted(set(audit_by_id)-set(rules_by_id))
                if missing: issues.append({'level':'ERROR','where':'manifest','message':f'rules missing audit records: {missing[:20]}'})
                if orphan: issues.append({'level':'WARNING','where':'manifest','message':f'audit records without emitted rules: {orphan[:20]}'})
                modes={'direct','calculated','summarized','missing','conflict','missing_template'}
                for i,a in enumerate(audit):
                    if not isinstance(a,dict): continue
                    rid=a.get('rule_id'); big=a.get('big_category'); sub=a.get('subcategory'); mode=a.get('extraction_mode')
                    aw=f'manifest.audit_records[{i}]'
                    if mode is not None and mode not in modes: issues.append({'level':'ERROR','where':aw,'message':f'invalid extraction_mode {mode!r}'})
                    if rid in rules_by_id:
                        for req in ['target_group_id','extraction_phase','source_priority','dedup_key']:
                            if not a.get(req): issues.append({'level':'ERROR','where':aw,'message':f'missing required audit field {req}'})
                        if a.get('target_group_id') and a.get('target_group_id') not in valid_target_groups:
                            issues.append({'level':'ERROR','where':aw,'message':f"unknown target_group_id {a.get('target_group_id')!r}"})
                        if a.get('extraction_phase') not in {'table_first','document_supplement'}:
                            issues.append({'level':'ERROR','where':aw,'message':f"invalid extraction_phase {a.get('extraction_phase')!r}"})
                        if a.get('source_priority') not in {'P1','P2','P3','P4','P5'}:
                            issues.append({'level':'ERROR','where':aw,'message':f"invalid or control-only source_priority {a.get('source_priority')!r}"})
                        expected_big=big_by_id[rid]
                        if big != expected_big: issues.append({'level':'ERROR','where':aw,'message':f'big_category {big!r} does not match rule file {expected_big!r}'})
                        if not isinstance(sub,str) or sub not in enabled.get(expected_big,set()):
                            issues.append({'level':'ERROR','where':aw,'message':f'subcategory {sub!r} is not enabled in {expected_big}'})
                        else:
                            issues.extend(validate_template_signature(rules_by_id[rid],expected_big,sub,spec_lookup,aw))
                dedup_seen={}
                for i,a in enumerate(audit):
                    if not isinstance(a,dict) or a.get('rule_id') not in rules_by_id: continue
                    dk=a.get('dedup_key')
                    if not dk: continue
                    if dk in dedup_seen and dedup_seen[dk] != a.get('rule_id'):
                        issues.append({'level':'ERROR','where':f'manifest.audit_records[{i}]','message':f'duplicate emitted dedup_key also used by {dedup_seen[dk]!r}'})
                    else:
                        dedup_seen[dk]=a.get('rule_id')
            except Exception as e:
                issues.append({'level':'ERROR','where':'manifest','message':f'invalid manifest JSON: {e}'})

    nerr=sum(x['level']=='ERROR' for x in issues); nwarn=sum(x['level']=='WARNING' for x in issues)
    return {'valid':nerr==0,'error_count':nerr,'warning_count':nwarn,'rule_counts':counts,'total_rules':sum(counts.values()),'issues':issues}


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--rules-dir',required=True,type=Path); ap.add_argument('--manifest',type=Path); ap.add_argument('--report',type=Path)
    args=ap.parse_args(); result=run_validation(args.rules_dir,args.manifest)
    report=args.report or args.rules_dir/'validation_report.json'; report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['valid','error_count','warning_count','total_rules','rule_counts']},ensure_ascii=False,indent=2))
    for issue in result['issues'][:60]: print(f"[{issue['level']}] {issue['where']}: {issue['message']}")
    if len(result['issues'])>60: print(f"... {len(result['issues'])-60} more issues; see {report}")
    return 0 if result['valid'] else 2

if __name__=='__main__': raise SystemExit(main())
