#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Finalize strict four-field JSON outputs into 8-sheet Excel + extraction report."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from validate_rules import run_validation

ROOT=Path(__file__).resolve().parents[1]
def load_json(p:Path): return json.loads(p.read_text(encoding='utf-8'))


def build_report(catalog, validation, manifest, rules_by_big, out_path:Path):
    baseline=load_json(ROOT/'config'/'rule_count_baseline_v3.json')
    lines=['# 知识规则提取报告','', '## 1. 权威参考与格式','',
           '- 范围与实体粒度：`规则数26-V3(1).docx`',
           '- 子类数量覆盖基线：`规则数26-V3_规则数量整理.xlsx`',
           '- JSON结构与逐子类表达：`知识规则模版.md`',
           '- 符号与公式：`调度专项符号统一说明-V1.docx`',
           '- 最终每条规则仅含 `rule_id / description / sets / parameters` 四个顶层字段。','',
           '## 2. 总体统计','', '| 大类 | direct | calculated | summarized | missing | conflict | 最终规则数 |','|---|---:|---:|---:|---:|---:|---:|']
    cats=manifest.get('categories',{})
    for c in catalog['categories']:
        s=cats.get(c['name'],{}).get('status_summary',{})
        lines.append(f"| {c['name']} | {s.get('direct',0)} | {s.get('calculated',0)} | {s.get('summarized',0)} | {s.get('missing',0)} | {s.get('conflict',0)} | {len(rules_by_big.get(c['name'],[]))} |")
    lines += ['', '## 3. 数量控制线与最终覆盖','', '| 大类 | 目标控制线 | 最终唯一规则 | 差值 | 说明 |','|---|---:|---:|---:|---|']
    for c in catalog['categories']:
        meta=baseline.get('category_targets',{}).get(c['name'],{})
        target=meta.get('target_count'); final=len(rules_by_big.get(c['name'],[])); diff=(target-final) if isinstance(target,(int,float)) else ''
        lines.append(f"| {c['name']} | {target} | {final} | {diff} | {meta.get('note','')} |")
    lines += ['', '说明：数量是覆盖控制线，不是凑数配额；约数/不一致必须在缺失与冲突章节说明。','', '## 4. 八大类逐类结果','']
    audit=manifest.get('audit_records',[])
    for c in catalog['categories']:
        big=c['name']; lines += [f"### {c['order']}. {big}",'',f"- V3实体范围：{c.get('entity_scope','')}",f"- 最终规则数：{len(rules_by_big.get(big,[]))}",'', '#### 子类覆盖','', '| 子类 | 状态/规则数 | 备注 |','|---|---:|---|']
        for sub in c.get('enabled_subcategories',[]):
            rs=[a for a in audit if isinstance(a,dict) and a.get('big_category')==big and a.get('subcategory')==sub and a.get('rule_id') in {r.get('rule_id') for r in rules_by_big.get(big,[])}]
            misses=[x for x in cats.get(big,{}).get('missing_subcategories',[]) if (x==sub or (isinstance(x,dict) and x.get('subcategory')==sub))]
            note='已输出' if rs else ('缺失' if misses else '无可输出规则/待核对')
            lines.append(f"| {sub} | {len(rs)} | {note} |")
        notes=cats.get(big,{}).get('calculation_notes',[])
        if notes:
            lines += ['', '#### 计算说明',''] + [f'- {n}' for n in notes]
        miss=cats.get(big,{}).get('missing_subcategories',[])
        if miss:
            lines += ['', '#### 缺失子类/字段',''] + [f'- {json.dumps(x,ensure_ascii=False) if isinstance(x,dict) else x}' for x in miss]
        conf=cats.get(big,{}).get('conflicts',[])
        if conf:
            lines += ['', '#### 冲突',''] + [f'- {json.dumps(x,ensure_ascii=False) if isinstance(x,dict) else x}' for x in conf]
        lines.append('')
    lines += ['## 5. 严格校验','',f"- valid: `{validation['valid']}`",f"- errors: {validation['error_count']}",f"- warnings: {validation['warning_count']}",'- 顶层规则字段：仅 `rule_id / description / sets / parameters`。','- 子类集合签名：根据 manifest 的 subcategory 回查 `知识规则模版.md`。','- DEMO/格式示例字样不得进入现场规则。','', '## 6. 多文件流程审计','',
              f"- Preflight完成：`{manifest.get('run',{}).get('preflight_completed',False)}`",
              f"- 表格首轮完成：`{manifest.get('run',{}).get('table_first_completed',False)}`",
              f"- 表格后gap plan完成：`{manifest.get('run',{}).get('gap_plan_generated',False)}`",
              f"- 文档补缺完成：`{manifest.get('run',{}).get('document_supplement_completed',False)}`",
              '', '## 7. 最终文件','', '- 8个大类JSON','- 知识规则汇总.xlsx（8 sheets）','- 知识规则提取报告.md','- extraction_manifest.json','- validation_report.json','- source_inventory.json','- 文件梳理与提取计划.md','- rule_gap_after_tables.json','- 剩余规则补缺计划.md','']
    out_path.write_text('\n'.join(lines),encoding='utf-8')


def build_workbook(catalog,rules_by_big,manifest,out_path:Path):
    from artifact_tool import Workbook, SpreadsheetFile
    wb=Workbook.create(); audit=manifest.get('audit_records',[]) if isinstance(manifest,dict) else []
    audit_by_id={a.get('rule_id'):a for a in audit if isinstance(a,dict) and a.get('rule_id')}
    headers=['rule_id','description','sets_json','parameters_json','subcategory','target_group_id','extraction_phase','extraction_mode','source_file','source_priority','source_sheet_or_section','source_location','validation_status','audit_note']
    for c in catalog['categories']:
        sh=wb.worksheets.add(c['sheet']); sh.merge_cells('A1:N1'); sh.get_range('A1').values=[[f"{c['name']}知识规则汇总"]]
        sh.get_range('A1').format={'fill':'#1F4E78','font':{'bold':True,'color':'#FFFFFF','size':14},'horizontal_alignment':'center','vertical_alignment':'center'}
        sh.get_range('A2:N2').values=[['JSON字段','JSON字段','JSON字段','JSON字段','审计字段','审计字段','审计字段','审计字段','审计字段','审计字段','审计字段','审计字段','审计字段','审计字段']]
        sh.get_range('A2:N2').format={'fill':'#EAF2F8','font':{'italic':True},'horizontal_alignment':'center'}
        sh.get_range('A3:N3').values=[headers]; sh.get_range('A3:N3').format={'fill':'#D9EAF7','font':{'bold':True},'horizontal_alignment':'center','vertical_alignment':'center','wrap_text':True}
        rows=[]
        for r in rules_by_big.get(c['name'],[]):
            a=audit_by_id.get(r['rule_id'],{})
            rows.append([r['rule_id'],r['description'],json.dumps(r['sets'],ensure_ascii=False,separators=(',',':')),json.dumps(r['parameters'],ensure_ascii=False,separators=(',',':')),a.get('subcategory',''),a.get('target_group_id',''),a.get('extraction_phase',''),a.get('extraction_mode',''),a.get('source_file',''),a.get('source_priority',''),a.get('source_sheet_or_section',''),a.get('source_location',''),a.get('validation_status',''),a.get('audit_note','')])
        if rows:
            end=3+len(rows); sh.get_range(f'A4:N{end}').values=rows; sh.get_range(f'A3:N{end}').format.wrap_text=True; sh.tables.add(f'A3:N{end}',True,f"Rules_{c['order']}")
        sh.freeze_panes.freeze_rows(3)
        widths=[26,48,42,42,28,18,18,18,28,14,28,22,18,36]
        for i,w in enumerate(widths): sh.get_range(f"{'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[i]}:{'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[i]}").format.column_width=w
        sh.get_range('A:N').format.vertical_alignment='top'
    SpreadsheetFile.export_xlsx(wb).save(str(out_path))


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--rules-dir',required=True,type=Path); ap.add_argument('--manifest',required=True,type=Path); ap.add_argument('--output-dir',required=True,type=Path); args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    catalog=load_json(ROOT/'config'/'eight_category_catalog.json'); validation=run_validation(args.rules_dir,args.manifest)
    (args.output_dir/'validation_report.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
    if not validation['valid']:
        print('Validation failed; refusing to finalize workbook/report.'); return 2
    manifest=load_json(args.manifest); rules_by_big={c['name']:load_json(args.rules_dir/c['file']) for c in catalog['categories']}
    build_workbook(catalog,rules_by_big,manifest,args.output_dir/'知识规则汇总.xlsx'); build_report(catalog,validation,manifest,rules_by_big,args.output_dir/'知识规则提取报告.md')
    print(f'Finalized outputs in {args.output_dir}'); return 0
if __name__=='__main__': raise SystemExit(main())
