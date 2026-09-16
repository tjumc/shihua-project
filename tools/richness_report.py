import json
from collections import defaultdict
from pathlib import Path

root = Path('/Users/machong/shihua-project')
out = root / 'extract_result_v2'
rules = json.loads((out / 'all_rule_samples.json').read_text())['rules']
groups = defaultdict(list)
for r in rules:
    groups[(r['category'], r['subcategory'])].append(r)

rows = []
for (cat, sub), rs in groups.items():
    sources = {r.get('source', {}).get('document') for r in rs if r.get('source', {}).get('document')}
    subjects = {str(r.get('subject')) for r in rs if r.get('subject') is not None}
    fields = set()
    for r in rs:
        obj = r.get('object')
        if isinstance(obj, dict):
            fields.update(obj.keys())
        fields.update((r.get('parameters') or {}).keys())
    rows.append({'category': cat, 'subcategory': sub, 'sample_count': len(rs),
                 'source_file_count': len(sources), 'subject_count': len(subjects),
                 'numeric_field_count': len(fields),
                 'status': 'ready' if rs else 'pending'})
rows.sort(key=lambda r: (-r['sample_count'], -r['numeric_field_count'], r['category'], r['subcategory']))
report = {
    'generated_at': '2026-09-08',
    'source_policy': '仅统计 source-materials 原始调研资料，不使用旧规则库或1050条规则表',
    'metric_definition': {
        'sample_count': '已生成 JSON 样例条数',
        'source_file_count': '样例引用的原始文件去重数',
        'subject_count': '规则 subject 去重数',
        'numeric_field_count': 'object/parameters 中出现的字段名去重数'
    },
    'subcategory_count': len(rows), 'total_sample_count': len(rules), 'ranking': rows,
    'top_rich_subcategories': rows[:20]
}
(out / 'data_richness_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report['top_rich_subcategories'][:15], ensure_ascii=False, indent=2))
