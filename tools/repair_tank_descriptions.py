import json
from pathlib import Path

ROOT = Path('/Users/machong/shihua-project')
OUT = ROOT / 'extract_result_v2'


def fmt(v):
    if isinstance(v, float):
        return f'{v:.6g}'
    return str(v)


def description(r):
    o = r.get('object') or {}
    material = o.get('material', '')
    tank = r.get('subject', '')
    parts = [f'{material}罐{tank}']
    if 'volume' in o:
        parts.append(f"罐容{fmt(o['volume'])}{o.get('unit', 'm3')}")
    if 'safe_lower_level' in o and 'safe_upper_level' in o:
        parts.append(f"安全液位{fmt(o['safe_lower_level'])}–{fmt(o['safe_upper_level'])}m")
    if 'initial_level' in o:
        parts.append(f"初始液位{fmt(o['initial_level'])}m")
    if 'meter_coefficient' in o:
        parts.append(f"液位计系数{fmt(o['meter_coefficient'])}")
    if 'density' in o and o['density'] is not None:
        parts.append(f"密度{fmt(o['density'])}")
    return '；'.join(parts) + '。'


all_path = OUT / 'all_rule_samples.json'
data = json.loads(all_path.read_text())
changed = 0
for r in data['rules']:
    if r.get('subcategory', '').endswith('罐') and r.get('predicate') == 'tank_capacity_and_level':
        r['description'] = description(r)
        changed += 1
all_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

for p in OUT.rglob('*.json'):
    if p.name in {'all_rule_samples.json', 'extraction_report.json'}:
        continue
    d = json.loads(p.read_text())
    if 'rules' not in d:
        continue
    for r in d['rules']:
        if r.get('subcategory', '').endswith('罐') and r.get('predicate') == 'tank_capacity_and_level':
            r['description'] = description(r)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2))

print(f'repaired {changed} tank descriptions')
