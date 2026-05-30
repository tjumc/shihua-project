# Rule Update Policy

## Identity Fingerprint

By default, two rules are considered the same rule when these normalized fields match:

```text
知识类型 + 子类型 + 适用范围 + 规则名称
```

Normalization removes whitespace, common punctuation differences, and trivial full-width/half-width differences. It does not remove numbers or units.

If the new extraction uses unstable rule names, use a stricter or broader field set with `--match-fields`, for example:

```bash
--match-fields 知识类型 子类型 适用范围 规则内容
```

or:

```bash
--match-fields 知识类型 子类型 适用范围 来源文件 具体页码
```

## Content Difference

For matched rules, these fields decide whether the rule changed:

```text
规则内容, 来源文件, 具体页码, 原文内容, JSON, 备注
```

If any comparable field differs after normalization, classify the row as `更新` and use the new row.

## Append

If no old identity fingerprint matches a new row, classify it as `新增` and append it to the relevant sheet.

## Preserve

Old rows with no matching new row stay in the output as `不变`. This avoids accidentally deleting valid historical rules just because the new document batch did not mention them.

## Conflicts

If the new workbook contains duplicate identity fingerprints within the same sheet, keep the last occurrence in the merged workbook and write earlier duplicates to the change log as `新表重复覆盖`. Review these manually before verification.

## Rule IDs

Default behavior is to reassign IDs after merge:

- 工艺规范类: `R1-001`, `R1-002`, ...
- 调度经验类: preserve known `EXP-xxx` prefixes by subtype when possible, otherwise use `EXP-OTH-001`, ...

Use `--keep-old-ids` only when external systems already reference old IDs and cannot tolerate renumbering.

## Verification Handoff

The merged `extracted_rules.xlsx` must keep only the 11 extraction columns. Do not add mask columns or manual verification columns here. Those belong to `petrochemical-rule-verification`.
