---
name: petrochemical-rule-update
description: Use this skill when incrementally updating petrochemical rule workbooks after a new batch of PDF/Word/Excel source documents has been processed. It connects petrochemical-rule-extraction and petrochemical-rule-verification by merging an old rule master workbook with newly extracted rules: append rules that do not already exist, replace existing rules when the same rule has changed, keep unchanged rules, preserve evidence fields, produce change logs, and output a verification-ready extracted_rules.xlsx.
---

# 石化规则增量更新 Skill

## Purpose

Use this skill between `petrochemical-rule-extraction` and `petrochemical-rule-verification`.

The normal pipeline is:

```text
新 PDF/Word/XLSX 文档
  -> petrochemical-rule-extraction 生成 new_extracted_rules.xlsx
  -> petrochemical-rule-update 合并旧总表和新抽取表
  -> petrochemical-rule-verification 对更新后的规则表做 mask 核验
```

This skill does not extract from raw documents by itself. First use `petrochemical-rule-extraction` on the new document batch, then use this skill to merge the result with the previous master workbook.

## Required Inputs

1. Previous master workbook, for example:

```text
/Applications/Desktop/项目/5.27/工艺规范与调度经验规则提取v1.xlsx
```

2. Newly extracted workbook from `petrochemical-rule-extraction`, usually:

```text
<new_extraction_output>/extracted_rules.xlsx
```

3. Output directory for the updated rule library.

Both old and new workbooks should use the standard 11 columns:

```text
规则编号, 规则名称, 知识类型, 子类型, 适用范围, 规则内容, 来源文件, 具体页码, 原文内容, JSON, 备注
```

## Update Policy

Read `references/update-policy.md` when the user asks about matching logic, audit rules, or edge cases.

Default policy:

- If no existing rule matches the new rule's identity fingerprint, append it as `新增`.
- If an existing rule matches the identity fingerprint but the rule content/evidence/JSON differs, replace the old row with the new row as `更新`.
- If an existing rule matches and the comparable fields are unchanged, keep the old row as `不变`.
- Preserve old rules not mentioned by the new batch.
- Reassign rule IDs after merging so each sheet has stable sequential IDs.
- Write a change log so reviewers can see old versus new values.

## Quick Command

Run the bundled script:

```bash
python ~/.codex/skills/petrochemical-rule-update/scripts/merge_rule_updates.py \
  --old /Applications/Desktop/项目/5.27/工艺规范与调度经验规则提取v1.xlsx \
  --new <new_extraction_output>/extracted_rules.xlsx \
  --output-dir <update_output_dir>
```

Optional flags:

```bash
--match-fields 知识类型 子类型 适用范围 规则名称
--content-fields 规则内容 来源文件 具体页码 原文内容 JSON 备注
--keep-old-ids
```

Use `--keep-old-ids` only when the downstream system depends on existing IDs. Otherwise let the script renumber rows to avoid duplicate or stale IDs.

## Outputs

The script creates:

```text
<output-dir>/
  extracted_rules.xlsx          # update result; pass this to petrochemical-rule-verification
  updated_rules.xlsx            # same workbook, explicit name for humans
  change_log.csv                # row-level change log
  change_log.json               # structured change log
  update_report.md              # summary and next-step commands
```

The `extracted_rules.xlsx` output is intentionally named to match `petrochemical-rule-verification` expectations.

## Recommended Workflow

1. Extract rules from the new document batch:

```text
请使用 petrochemical-rule-extraction skill，扫描 <新文档目录>，输出到 <new_extraction_output>。
```

2. Merge the new extraction into the previous master:

```bash
python ~/.codex/skills/petrochemical-rule-update/scripts/merge_rule_updates.py \
  --old /Applications/Desktop/项目/5.27/工艺规范与调度经验规则提取v1.xlsx \
  --new <new_extraction_output>/extracted_rules.xlsx \
  --output-dir <update_output_dir>
```

3. Verify the merged workbook:

```text
请使用 petrochemical-rule-verification skill，
核验 <update_output_dir>/extracted_rules.xlsx，
原始资料目录是 <包含旧资料和新资料的总目录>，
输出到 <verification_output_dir>。
```

## Quality Checks

After running the merge:

- Confirm `update_report.md` has sensible counts for `新增`, `更新`, and `不变`.
- Check `change_log.csv` for high-risk updates where numeric limits, units, or operation directions changed.
- Confirm both rule sheets still contain the standard 11 columns.
- Pass only `extracted_rules.xlsx` to the verification skill, not the change log.
