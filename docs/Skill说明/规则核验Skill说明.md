# petrochemical-rule-verification

用于石化知识规则抽取结果的 mask 核验与人工核对判定。

## 安装

```bash
mkdir -p ~/.claude/skills
cp -r petrochemical-rule-verification ~/.claude/skills/
```

## 核心流程

```bash
mkdir -p verification_output

python scripts/build_mask_workbook.py --input extracted_rules.xlsx --output verification_output/rule_content_mask.xlsx
python scripts/export_blind_inputs.py --input verification_output/rule_content_mask.xlsx --outdir verification_output

# 使用两个独立智能体分别填充 agent1_filled.xlsx 和 agent2_filled.xlsx

python scripts/merge_agent_fills.py \
  --base verification_output/rule_content_mask.xlsx \
  --agent1 verification_output/agent1_filled.xlsx \
  --agent2 verification_output/agent2_filled.xlsx \
  --output verification_output/rule_content_filled.xlsx

python scripts/judge_verification.py \
  --input verification_output/rule_content_filled.xlsx \
  --output verification_output/rule_content_verified.xlsx \
  --report verification_output/verification_report.md
```

## 示例文件

- `examples/rule_content_mask_example.xlsx`
- `examples/rule_content_filled_example.xlsx`
