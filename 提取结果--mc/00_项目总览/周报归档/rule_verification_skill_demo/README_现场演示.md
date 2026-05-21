# 规则核验 Skill 现场演示说明

## 推荐演示方式

现场使用方案 A：给定一份已提取规则表，并使用预置的 `agent1_filled_demo.xlsx`、`agent2_filled_demo.xlsx` 作为盲审回填结果，演示完整核验链路。

默认演示命令：

```powershell
cd "C:\Users\643\Desktop\石化项目\提取结果--mc\00_项目总览\汇报附件\rule_verification_skill_demo"
.\run_demo.ps1
```

运行后输出目录：

```text
live_output/
```

## 现场展示顺序

1. `01_rule_content_mask.xlsx`：规则内容自动 mask。
2. `02_agent1_blind_input.xlsx`：参数类字段盲审输入。
3. `03_agent2_blind_input.xlsx`：语义类字段盲审输入。
4. `06_rule_content_filled.xlsx`：两个智能体回填结果合并。
5. `07_rule_content_verified.xlsx`：最终核验判定。
6. `08_verification_report.md`：核验统计报告。

## 使用老师现场给定的规则表

如果老师给的是已提取规则表 Excel，可以这样运行：

```powershell
.\run_demo.ps1 -InputRules "C:\demo\input_rules.xlsx"
```

注意：如果输入表不是本 demo 对应的 3 条样例规则，预置回填表的规则编号可能对不上，最终结果可能全部进入人工核对。要完整演示最终判定，需要准备与该输入表匹配的 `agent1_filled.xlsx` 和 `agent2_filled.xlsx`：

```powershell
.\run_demo.ps1 `
  -InputRules "C:\demo\input_rules.xlsx" `
  -Agent1Filled "C:\demo\agent1_filled.xlsx" `
  -Agent2Filled "C:\demo\agent2_filled.xlsx"
```

## 现场说明口径

当前可演示的是：

```text
已提取规则表 -> mask 核验表 -> 双智能体盲审输入 -> 回填合并 -> 自动核验判定
```

当前不演示的是：

```text
原始 PDF/DOCX/XLSX -> 自动抽取规则 -> 自动回源填空
```

这部分属于后续“新数据文件接入”和“抽取-更新-核验闭环”阶段。
