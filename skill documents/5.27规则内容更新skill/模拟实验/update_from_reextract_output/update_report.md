# 石化规则增量更新报告

- 生成时间: 2026-05-27T20:50:28
- 旧总表: /Applications/Desktop/项目/5.27/v2.xlsx
- 新抽取表: /Applications/Desktop/项目/5.27/reextract_from_pdf_output/extracted_rules.xlsx
- 匹配字段: 知识类型, 子类型, 适用范围, 规则名称
- 内容比较字段: 规则内容, 来源文件, 具体页码, 原文内容, JSON, 备注

## 汇总

### 工艺规范类
- 新增: 21
- 合并后总数: 84

### 调度经验类
- 新增: 7
- 合并后总数: 94

### 全部
- 新增: 28
- 更新: 0
- 不变: 0
- 合并后总数: 178

## 下游核验

将 `extracted_rules.xlsx` 传给 `petrochemical-rule-verification`：

```bash
python ~/.codex/skills/petrochemical-rule-verification/scripts/run_verification.py \
  --phase prep \
  --input extracted_rules.xlsx \
  --output-dir verification_output
```
