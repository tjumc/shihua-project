---
name: petrochemical-rule-verification
description: Use this skill when validating petrochemical knowledge-rule extraction workbooks. It creates mask columns from the rule content column, prepares blind-review workbooks for two independent agents that can only use source files and page references, merges their filled answers, and decides mask-level and final manual verification flags.
---

# 石化知识规则核验 Skill

本 skill 用于对上一阶段抽取出的 `xlsx` 规则汇总表进行自动化核验。它适用于工艺规范规则、调度经验规则等石化项目规则表，核心目标是：

1. 对 `规则内容` 列中的关键字段进行两轮 mask；
2. 让两个独立智能体分别只依据 `来源文件` 和 `具体页码` 回填 mask；
3. 严格隔离盲审智能体，使其不能看到 `规则内容`、`原文内容`、`JSON`；
4. 根据 `关键字段mask` 与 `填空内容mask` 的数值、文本、语义一致性，自动填写 `人工核验mask1`、`人工核验mask2` 和最终 `人工核对`。

## 输入文件

### 1. 抽取结果表

来自规则提取 skill 的 Excel 文件，例如：

```text
extracted_rules.xlsx
```

每个规则子表至少应包含以下列：

```text
规则编号
规则名称
知识类型
子类型
适用范围
规则内容
来源文件
具体页码
原文内容
JSON
备注
```

### 2. 项目原始资料目录

包含 `pdf`、`doc`、`docx`、`txt`、`xlsx` 等源文件。智能体只能基于表格中的：

```text
来源文件
具体页码
```

回到该目录中检索和核对原文。

## 输出文件

推荐输出目录：

```text
verification_output/
```

生成文件包括：

```text
rule_content_mask.xlsx                  # 新增 mask 列后的表
agent1_blind_input.xlsx                  # 智能体 1 盲审输入
agent2_blind_input.xlsx                  # 智能体 2 盲审输入
agent1_filled.xlsx                       # 智能体 1 填空结果
agent2_filled.xlsx                       # 智能体 2 填空结果
rule_content_filled.xlsx                 # 合并两个智能体后的 filled 表
rule_content_verified.xlsx               # 自动判断人工核验后的最终表
verification_report.md                   # 核验报告
```

## 字段插入规则

对每个包含 `规则内容` 列的规则子表，在 `规则内容` 后面新增以下列：

```text
规则内容mask1
关键字段mask1
填空内容mask1
原文内容mask1
人工核验mask1
规则内容mask2
关键字段mask2
填空内容mask2
原文内容mask2
人工核验mask2
```

在 `原文内容` 后、`JSON` 前新增：

```text
人工核对
```

最终推荐列顺序为：

```text
规则编号
规则名称
知识类型
子类型
适用范围
规则内容
规则内容mask1
关键字段mask1
填空内容mask1
原文内容mask1
人工核验mask1
规则内容mask2
关键字段mask2
填空内容mask2
原文内容mask2
人工核验mask2
来源文件
具体页码
原文内容
人工核对
JSON
备注
```

字段格式参考 `examples/rule_content_mask_example.xlsx` 和 `examples/rule_content_filled_example.xlsx`。

## 阶段一：生成 mask 表

调用：

```bash
python scripts/build_mask_workbook.py \
  --input extracted_rules.xlsx \
  --output verification_output/rule_content_mask.xlsx
```

### mask 选择原则

优先 mask 能够影响调度算法或工艺约束判断的关键词：

1. 具体数值：`10%`、`20 t/h`、`80%-105%`、`680-710℃`；
2. 上下限关系：`≤`、`≥`、`不超过`、`低于`、`高于`、`控制在`；
3. 关键操作：`停工`、`切换`、`降量`、`升温`、`补充原油`、`开启大循环`；
4. 运行模式：`大循环`、`小循环`、`闭路循环`、`开侧线`；
5. 时间约束：`提前2小时`、`18-24小时`、`≤45天`；
6. 物料/装置对象：`常压装置`、`催化装置`、`循环氢`、`电脱盐注水量`。

### mask1 / mask2 分工

- `mask1` 优先选择数值、阈值、范围、时间、比例、单位等参数字段；
- `mask2` 优先选择操作动作、运行模式、对象、约束条件等语义字段；
- 若规则只有一个有效关键字段，允许只生成 `mask1`，`mask2` 可为空；
- 不应 mask 无业务意义的虚词，例如“应”“时”“后”“进行”。

## 阶段二：生成两个盲审智能体输入

调用：

```bash
python scripts/export_blind_inputs.py \
  --input verification_output/rule_content_mask.xlsx \
  --outdir verification_output
```

生成：

```text
agent1_blind_input.xlsx
agent2_blind_input.xlsx
```

### 盲审隔离要求

两个智能体均不得看到以下列：

```text
规则内容
原文内容
JSON
备注
```

两个智能体只能看到：

```text
规则编号
规则名称
知识类型
子类型
适用范围
规则内容mask1 / mask2
关键字段mask1 / mask2
填空内容mask1 / mask2
原文内容mask1 / mask2
来源文件
具体页码
```

其中：

- 智能体 1 只处理 `mask1`；
- 智能体 2 只处理 `mask2`；
- 智能体不得根据 `关键字段mask` 直接抄答案，必须回到 `来源文件` 和 `具体页码` 查证；
- `关键字段mask` 仅用于后续自动比对，不作为填空证据来源。

## 阶段三：两个独立智能体填空

### 智能体 1 提示词

```text
你是石化规则核验智能体1，只负责 mask1。你不能查看原始“规则内容”“原文内容”和“JSON”。

输入为一个盲审 Excel 表，包含规则编号、规则名称、适用范围、规则内容mask1、来源文件、具体页码等字段。

任务：
1. 对每条规则，根据“来源文件”和“具体页码”定位原始资料；
2. 查找能够填入“规则内容mask1”中空缺位置的原文证据；
3. 填写“填空内容mask1”；
4. 填写“原文内容mask1”，内容应为支持该填空的最小原文片段；
5. 如果来源文件或页码无法定位，填空内容mask1留空，并在原文内容mask1写明“未找到可核验证据”。

禁止：
- 不得查看或引用原始规则内容列；
- 不得查看或引用原文内容列；
- 不得查看或引用 JSON 列；
- 不得直接抄关键字段mask1作为答案，必须从来源文件和页码查证。
```

### 智能体 2 提示词

```text
你是石化规则核验智能体2，只负责 mask2。你不能查看原始“规则内容”“原文内容”和“JSON”。

输入为一个盲审 Excel 表，包含规则编号、规则名称、适用范围、规则内容mask2、来源文件、具体页码等字段。

任务：
1. 对每条规则，根据“来源文件”和“具体页码”定位原始资料；
2. 查找能够填入“规则内容mask2”中空缺位置的原文证据；
3. 填写“填空内容mask2”；
4. 填写“原文内容mask2”，内容应为支持该填空的最小原文片段；
5. 如果来源文件或页码无法定位，填空内容mask2留空，并在原文内容mask2写明“未找到可核验证据”。

禁止：
- 不得查看或引用原始规则内容列；
- 不得查看或引用原文内容列；
- 不得查看或引用 JSON 列；
- 不得直接抄关键字段mask2作为答案，必须从来源文件和页码查证。
```

## 阶段四：合并两个智能体结果

调用：

```bash
python scripts/merge_agent_fills.py \
  --base verification_output/rule_content_mask.xlsx \
  --agent1 verification_output/agent1_filled.xlsx \
  --agent2 verification_output/agent2_filled.xlsx \
  --output verification_output/rule_content_filled.xlsx
```

合并规则：

- 以 `规则编号` 为主键；
- 从 agent1 文件回填 `填空内容mask1`、`原文内容mask1`；
- 从 agent2 文件回填 `填空内容mask2`、`原文内容mask2`；
- 不覆盖 `规则内容`、`原文内容`、`JSON`；
- 保持原始表格格式、列顺序和 sheet 名称。

## 阶段五：自动判断人工核验

调用：

```bash
python scripts/judge_verification.py \
  --input verification_output/rule_content_filled.xlsx \
  --output verification_output/rule_content_verified.xlsx \
  --report verification_output/verification_report.md
```

### 判断规则

对每一条规则分别判断 `mask1` 和 `mask2`：

1. 若 `关键字段mask` 和 `填空内容mask` 都为空：
   - `人工核验mask` 留空或写 `是`，取决于是否存在待核验 mask；
2. 若数值相等：
   - `人工核验mask = 否`；
3. 若文本完全相同：
   - `人工核验mask = 否`；
4. 若文本不完全相同，但语义一致：
   - `人工核验mask = 否`；
5. 若数值不同、单位不一致、范围不一致、方向相反、语义不一致、缺少证据：
   - `人工核验mask = 是`。

最终：

```text
如果 人工核验mask1 == 是 或 人工核验mask2 == 是，则 人工核对 = 是；
否则 人工核对 = 否。
```

### 数值一致性

以下情况视为一致：

```text
10% == 10 %
20t/h == 20 t/h
400 Nm³/m³ == 400 Nm ³/m ³
0.45 == 45%
≤3%/h == 不超过3%/h
80%-105% == 80%~105%
680-710℃ == 680℃至710℃
```

以下情况视为不一致：

```text
25%、50%、75%、100% != 45%
≤3%/h != ≥3%/h
80%-105% != 70%-90%
提前2小时 != 提前1小时
```

### 语义一致性

以下情况视为一致：

```text
告知/请示程序 == 履行告知义务并按规定请示
停工 == 装置停工
切换 == 原油切换 / 物料切换
开启大循环 == 投用塔底大循环流程
```

以下情况视为不一致：

```text
停工 != 开工
升温 != 降温
提高负荷 != 降低负荷
大循环 != 小循环
告知 != 审批通过
```

## 推荐一键流程

```bash
mkdir -p verification_output

python scripts/build_mask_workbook.py \
  --input extracted_rules.xlsx \
  --output verification_output/rule_content_mask.xlsx

python scripts/export_blind_inputs.py \
  --input verification_output/rule_content_mask.xlsx \
  --outdir verification_output

# 然后分别调用两个独立智能体填写：
# verification_output/agent1_blind_input.xlsx -> verification_output/agent1_filled.xlsx
# verification_output/agent2_blind_input.xlsx -> verification_output/agent2_filled.xlsx

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

## 质量检查清单

完成后必须检查：

1. 所有规则子表都新增了 10 个 mask 相关列；
2. `人工核对` 位于 `原文内容` 后、`JSON` 前；
3. 两个盲审输入表不包含 `规则内容`、`原文内容`、`JSON`、`备注`；
4. 智能体 1 只填写 mask1；
5. 智能体 2 只填写 mask2；
6. `人工核验mask1/mask2` 只能填写 `是`、`否` 或空；
7. `人工核对` 只要任一 mask 为 `是`，就必须为 `是`；
8. 对于数值不一致、单位冲突、证据缺失的规则，必须进入人工核对。
