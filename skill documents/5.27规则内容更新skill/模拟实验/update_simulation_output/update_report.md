# 石化规则增量更新报告

- 生成时间: 2026-05-27T20:24:07
- 旧总表: /Applications/Desktop/项目/5.27/v2.xlsx
- 新抽取表: /Applications/Desktop/项目/5.27/新批次两文件抽取结果.xlsx
- 匹配字段: 知识类型, 子类型, 适用范围, 规则名称
- 内容比较字段: 规则内容, 来源文件, 具体页码, 原文内容, JSON, 备注

## 汇总

### 工艺规范类
- 新增: 57
- 合并后总数: 120

### 调度经验类
- 新增: 3
- 合并后总数: 90

### 全部
- 新增: 60
- 更新: 0
- 不变: 0
- 合并后总数: 210

## 下游核验

将 `extracted_rules.xlsx` 传给 `petrochemical-rule-verification`：

```bash
python ~/.codex/skills/petrochemical-rule-verification/scripts/run_verification.py \
  --phase prep \
  --input extracted_rules.xlsx \
  --output-dir verification_output
```
