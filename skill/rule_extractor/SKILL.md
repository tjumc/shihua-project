---
name: petrochemical-knowledge-rule-extractor
description: Multi-file petrochemical scheduling knowledge-rule extraction with file preflight, spreadsheet-first extraction, V3 quantity-gap control, strict four-field JSON, eight-category sequential processing, deduplication, and final 8-sheet workbook/report.
---

# 石化调度知识规则提取 Skill（多文件表格优先补缺版）

## 0. 核心目标

把一个文件或一个包含大量 Excel / DOCX / PDF / MD / JSON 等资料的目录，转换为可用于调度算法的知识规则。

本 Skill 不是“把所有文件混在一起尽量多抽”，而是执行：

> **先梳理文件 → 表格优先建立规则底座 → 按数量/实体覆盖核对缺口 → 只对缺口读取文本补充 → 去重/冲突 → 八大类最终汇总。**

必须同时满足：

1. **范围正确**：只抽 V3 允许的大类、子类和实体粒度；
2. **模板正确**：每个子类严格遵循《知识规则模版.md》；
3. **符号正确**：sets/公式符合《调度专项符号统一说明-V1》；
4. **表格优先**：原生结构化数据表首先提取；
5. **不重复提取**：表格已覆盖/达标的子类，后续文本只复核，不再生成重复规则；
6. **数量受控但不凑数**：规则数量基线用于覆盖控制，不用于伪造规则；
7. **JSON严格**：每条最终规则只有 `rule_id / description / sets / parameters` 四个顶层字段；
8. **全程可追溯**：来源、优先级、阶段、去重、冲突、target_group 只进审计文件，不污染最终 JSON。

---

# 1. 四个权威参考文件及职责

执行前必须加载：

## 1.1 `references/规则数26-V3(1).docx` —— 范围/实体粒度权威

决定：
- 8 个大类；
- 允许的业务范围；
- 实体粒度；
- 例如罐区按约10类逻辑实体罐，而不是按底层174个物理罐逐条扩张。

它回答：**抽什么、按什么粒度抽。**

## 1.2 `references/知识规则模版.md` —— JSON结构与逐子类表达最高权威

这是唯一 JSON 模板。

每个 `### 子类` 均给出：
- 规则对象；
- 必须保留的 sets；
- 不应重复的集合；
- parameters 命名；
- description 表达；
- 完整四字段 JSON 示例。

进入任何子类前必须读取该子类段落，不能只按经验生成。

## 1.3 `references/调度专项符号统一说明-V1.docx` —— 集合与公式权威

决定：
- `T/U/S/Q/O/N`；
- `Ucdu/Up/Umix`；
- `IU/OU/IT/OT/UQ/OUSQ/CDUsk`；
- CDU流量/性质、二次装置、混流等公式语义。

## 1.4 `references/规则数26-V3_规则数量整理.xlsx` —— 数量覆盖基线

该表用于：
- 记录 8 大类目标量；
- 记录子类/子类组数量；
- 表格首轮后计算剩余规则数量；
- 决定哪些子类还允许进入文档补缺阶段。

**数量表不是造数配额。**

派生配置：`config/rule_count_baseline_v3.json`。

总目标：约 **1200** 条；大类目标：

| 大类 | 目标数量 |
|---|---:|
| 原油类 | 50 |
| 装置类 | 550 |
| 罐区类 | 50 |
| 调合类 | 150 |
| 产品类 | 100 |
| 停工调度规则 | 100 |
| 流程特征和协同规则 | 100 |
| 调度经验规则 | 100 |

重要：
- 停工正文按11子类×10类装置=110，与大类100不一致；
- 流程协同子项约数直接相加约120，与大类100不一致；
- 调度经验各子项约数直接相加也超过100；
- 调合正文约150–160，大类目标写150；
- 原油混合计算数量未明确。

因此：**明确数量可用于关闭补缺；约数/区间/歧义只作覆盖指导。**

---

# 2. 最终 JSON 严格四字段

每条规则必须且只能有：

```json
{
  "rule_id": "...",
  "description": "...",
  "sets": [],
  "parameters": {}
}
```

禁止加入任何额外顶层字段，包括：
`type/category/subject/predicate/source/provenance/confidence/extraction_status/notes/subcategory/dedup_key/target_group_id`。

## 2.1 sets

每个 item 只能：

```json
{
  "set_name": "U",
  "subset_name": "Ucdu",
  "element": "CDU_01"
}
```

## 2.2 parameters

每个参数只能：

```json
"feed_rate_min": {
  "value": 100,
  "unit": "t/h"
}
```

## 2.3 description

- 中文、事实化、简洁；
- 不写来源过程；
- 不写“根据附件/表格/计算得到”；
- 不带 DEMO；
- 不把审计信息塞进描述。

---

# 3. 多文件任务的总流程：必须按阶段执行

禁止“打开所有文件 → 混合抽取 → 最后分类”。

必须严格执行 7 个阶段：

## Phase 0 — 文件梳理 Preflight（任何规则生成之前）

### 3.0.1 递归扫描目录

支持：
- `.xlsx/.xls/.csv/.tsv`
- `.docx`
- `.pdf`
- `.md/.txt`
- `.json`

保留完整相对路径，不能只记文件名。

### 3.0.2 区分“控制参考”与“现场事实源”

以下属于 R0，只控制 Skill，禁止作为现场事实抽取源：
- 知识规则模版.md
- 调度专项符号统一说明-V1.docx
- 规则数26-V3(1).docx
- 规则数26-V3_规则数量整理.xlsx
- Skill 内 config/reference/template 文件

### 3.0.3 每个现场文件必须建立档案

写入 `source_inventory.json`：
- `source_id`
- `relative_path`
- `file_type`
- `priority`
- `evidence_role`
- `contains_structured_table`
- `likely_big_categories`
- `likely_subcategories`
- `expected_contribution`
- `read_order`
- `status`
- `notes`

### 3.0.4 必须先给出“这个文件大概能抽什么”

在正式抽取前生成 `文件梳理与提取计划.md`，示例：

| 优先级 | 文件 | 格式 | 主要内容 | 可能大类 | 可能子类 | 预计贡献 | 是否首轮 |
|---|---|---|---|---|---|---|---|
| P1 | 装置基础数据.xlsx | xlsx | 负荷/能力 | 装置类 | 装置进料上下限 | 高 | 是 |
| P1 | 储罐数据.xlsx | xlsx | 库存/罐主数据 | 原油/罐区 | 库存/实体映射 | 高 | 是 |
| P3 | 停工规程.docx | docx | 停复工时窗 | 停工调度 | 11个停工子类 | 中-高 | 表格后补缺 |
| P4 | 流程说明.pdf | pdf | 上下游连接 | 流程协同 | 物料流向等 | 中 | 表格后补缺 |

如果没有完成 Preflight，不得开始生成最终规则。

---

# 4. 文件优先级：表格优先，但冲突权威性独立

读取 `config/source_priority_policy.json`。

## P1 原生结构化数据表 —— 第一优先级

`.xlsx/.xls/.csv/.tsv`。

优先抽：
- 上下限
- 负荷
- 收率
- 物性
- 配方
- 库存
- 产量/需求（必须区分语义）
- 实体映射
- 拓扑表

## P2 文档内结构化表格

DOCX/PDF/MD 中明确表格。只在表格首轮缺口计划允许时新增。

## P3 正式规程/操作/规则文本

适合：停工、切换、检修、时间窗口、操作频次、经验阈值。

## P4 流程/拓扑说明

适合 IU/OU/IT/OT、装置链协同。

## P5 叙述性材料

最后补充；没有明确对象+约束+参数时不生成。

### 提取顺序 ≠ 冲突权威性

表格先抽取，但若后续正式文件明确：
- 更新版本；
- 生效日期；
- 修订后的新阈值；

则进入 revision/conflict 判定，不能因为“表格先读”而无条件覆盖正式最新规程。

---

# 5. Phase 1 — 表格首轮：先建立规则底座

只处理 P1 原生结构化数据表。

## 5.1 P1 内部仍按 8 大类顺序

1. 原油类
2. 装置类
3. 罐区类
4. 调合类
5. 产品类
6. 停工调度规则
7. 流程特征和协同规则
8. 调度经验规则

不得跨类混写。

## 5.2 Sheet 也要先梳理

一个工作簿包含很多 sheet 时，先建立 sheet inventory：
- sheet名
- 实体粒度
- 关键字段
- 是否数值型
- 可能子类
- 优先级

原始数据/参数 sheet 高于汇总说明 sheet。

## 5.3 每条候选规则先进入 staging，不立即无脑追加

manifest 审计字段至少记录：
- `rule_id`
- `big_category`
- `subcategory`
- `target_group_id`
- `extraction_phase = table_first`
- `extraction_mode`
- `source_id`
- `source_file`
- `source_priority = P1`
- `source_sheet_or_section`
- `source_location`
- `dedup_key`
- `validation_status`
- `secondary_sources`
- `audit_note`

这些字段绝不进入最终四字段 JSON。

---

# 6. 去重必须在“数量统计之前”完成

多文件混乱的核心通常是重复规则。因此：

> **先去重，再统计已提取数量。**

## 6.1 dedup_key

建议：

`big_category + subcategory + normalized sets signature + sorted parameter semantic keys`

sets signature 按：
`set_name | subset_name | normalized element` 排序。

**不要把 parameter value 放入身份键。**

原因：
- 同一个对象同一种约束，不同文件给不同数值，应识别为 conflict；
- 如果 value 放入 dedup_key，会被错误当成两条规则。

## 6.2 处理规则

### 同 dedup_key + 同参数值

= duplicate evidence。

只保留一条最终规则；其他来源写入 `secondary_sources`。

### 同 dedup_key + 不同参数值

= conflict/revision candidate。

- 不生成两条重复规则；
- 比较版本、生效时间、正式性；
- 能明确新版则保留新版并记录 superseded source；
- 不能明确则标 conflict，暂不输出确定规则。

---

# 7. Phase 2 — 表格首轮后的规则数量/覆盖缺口核对

表格 P1 完成后，**必须停止继续读低优先级文档**，先做缺口统计。

读取：`config/rule_count_baseline_v3.json`。

## 7.1 target_group_id

由于数量表中部分行是“多个模板子类共用一个数量”，不能简单按 subcategory 名字统计。

每条规则必须在 manifest 中绑定一个 `target_group_id`。

例如：
- 常减压“每种原油加工量+配方”共60条，是一个 target group；
- 上游10类装置共300条，是一个 target group；
- 罐区10类实体罐共50条，是一个 target group。

## 7.2 exact 数量

若目标是明确数量：

`remaining = max(target_count - extracted_unique, 0)`

如果 `remaining = 0`：
- `closed_for_generation = true`；
- 后续 DOCX/PDF/MD 只能复核；
- 不得再新增这个 target group 的规则。

## 7.3 approximate / interval

例如“约30”“约15–20”“约150–160”：
- 只做覆盖方向判断；
- 不强制填满；
- 不因为少几条就编造；
- 不因为多几条就立即删除。

## 7.4 unspecified

例如原油混合计算数量“未明确”：
- 不制造一个假 target；
- 只检查模板3个子类是否有证据；
- 有实体名册时看 coverage slot；
- 无证据保持 missing。

## 7.5 大类总量控制

大类目标是控制线：50/550/50/150/100/100/100/100。

若子类数字与大类不一致：
- 报告 discrepancy；
- 不强行让所有子类同时满足；
- 不把有效规则机械截断；
- 先查重复/粒度/映射问题。

## 7.6 必须生成

- `rule_gap_after_tables.json`
- `剩余规则补缺计划.md`

补缺计划必须列：

| 大类 | target_group | 子类 | 目标 | 表格已提取唯一规则 | 剩余 | 是否关闭 | 下一步允许文件 |
|---|---|---|---:|---:|---:|---|---|

---

# 8. 数量不是唯一标准：coverage slots 更重要

如果有明确实体名册，必须同时维护 coverage slot。

例如：
- 原油罐物料平衡：10个原油罐槽位；
- 原油库存上下限：10个原油罐槽位；
- 常减压30种原油：30个原油槽位；
- 罐区：10类逻辑实体罐；
- 产品类：50种产品（若现场名册存在）。

即使计数达到目标，如果重复覆盖同一个实体，也不能判完成。

状态判断优先级：
1. 实体 coverage slots；
2. dedup 后唯一规则数；
3. 数量基线。

---

# 9. Phase 3 — 文档补缺：只处理剩余子类/槽位

此阶段才处理 P2/P3/P4/P5。

## 9.1 允许新增规则的条件

至少满足一个：
1. `remaining_count > 0`；
2. 子类完全未覆盖；
3. 已知实体 slot 未覆盖；
4. 表格只给数值，但缺规则语义/时窗/事件；
5. 表格无法提供流程拓扑，而流程类仍未覆盖。

## 9.2 已完成子类的文本文件如何处理

已关闭 target group：
- 可以读；
- 只用于 validation / conflict detection；
- 不得再生成第二条同 identity 规则。

## 9.3 搜索范围必须缩小

不能再次遍历所有文件、所有子类。

`剩余规则补缺计划.md` 应明确：
- 要补哪个大类；
- 哪个子类；
- 缺哪些实体；
- 推荐读哪些文件；
- 文件优先级；
- 预计可补多少。

只有这些文件进入深读。

---

# 10. 每个子类仍必须先回读模板

即使进入补缺，也不能因为文本写得像规则就直接生成。

每个子类：
1. 找 `知识规则模版.md` 对应 `###`；
2. 读说明句；
3. 读示例 JSON；
4. 记录 sets 签名、subset、parameter 名、单位、description 语义；
5. 再从源文件替换现场实体和值。

典型：
- 装置进料性质：`UQ`；
- 侧线性质：`OUSQ`；
- 原油混合侧线收率：`O + CDUsk`；
- 调合配方：`IU + OU`。

---

# 11. 八大类范围与数量控制要点

## 11.1 原油类 — 大类目标50

模板子类：13个。

数量表明确部分包括：
- 原油罐物料平衡：10
- 收付互斥：1
- 库存上下限：10
- 单罐同时供装置数量：10
- 静置：1
- 付油罐切换：1
- 原油罐收油速率：10
- 进厂原油期限内收完：1
- 收油罐选择：1

原油混合计算数量未明确；供油罐数量/混油比例原文断句有歧义。不得强拆凑数。

## 11.2 装置类 — 550

数量 target groups：
- 常减压30种原油：加工量+配方 = 60（可明确分为30+30）；
- 常减压进料上下限+性质上下限 = 20（内部拆分未明确）；
- 常减压侧线收率 = 10；
- 10个侧线×6性质 = 60；
- 上游10类装置 = 300；
- 下游10类装置 = 100。

实际装置必须先映射到 V3 装置类别，不能把 Excel 所有设备无条件纳入。

## 11.3 罐区类 — 50

按约10类逻辑实体罐。

原文写“每类5条”，但又列举约6种操作规则。因此：
- 50作为总体控制；
- 不机械做10×6；
- 物理罐号只作证据；
- 储罐容积上下限禁用；
- 安全液位默认不计入当前V3。

## 11.4 调合类 — 150

正文约150–160。

只对数据存在的产品生成；不补造98#、-20#、航煤、船燃等。

数量是产品×组分/性质的总体估算，不能把同一事实拆成多个近义规则凑数。

## 11.5 产品类 — 100

- 每日产量上下限：50
- 调度周期总产量上下限：50

需求/配额不自动等于产量硬上下限。

## 11.6 停工调度规则 — 100

11个子类各“按10类装置类推”得到10条是分布指导；11×10=110 与大类100冲突。

因此：
- 子类10是 advisory；
- 大类100是控制线；
- 有真实停复工证据才抽。

## 11.7 流程特征和协同规则 — 100

子类约数相加约120。

所有子类数量均为 advisory；必须有明确流程/拓扑证据。

## 11.8 调度经验规则 — 100

各子类为约数/区间，合计明显超过100。

仅做覆盖方向；经验规则必须有明确经验、阈值、偏好、惩罚或事件依据。

---

# 12. 计算规则

只有模板允许且输入完整时才能计算。

## 12.1 原油罐库存
`inventory_min = h_min × meter_factor`

`inventory_max = h_max × meter_factor`

## 12.2 装置进料
`feed_min = rated_load × minimum_load_factor`

`feed_max = max_processing_load`

若明确使用最大负荷系数：
`feed_max = rated_load × maximum_load_factor`

## 12.3 固定收率产品产出
`product_rate_min = feed_min × yield`

`product_rate_max = feed_max × yield`

空/0不能默认当有效收率。

## 12.4 混合性质
- 质量型按质量流量加权；
- SPG/密度按符号文档体积加权；
- 不得所有性质统一线性质量加权。

---

# 13. extraction_manifest.json 审计要求

最终 JSON 只有4字段；所有过程信息进入 manifest。

每条已输出规则至少记录：

```json
{
  "rule_id": "UNIT_FEED_BOUND_XXX",
  "big_category": "装置类",
  "subcategory": "装置进料上下限",
  "target_group_id": "UNIT_G05",
  "extraction_phase": "table_first",
  "extraction_mode": "calculated",
  "source_id": "SRC003",
  "source_file": "数据/装置基础数据.xlsx",
  "source_priority": "P1",
  "source_sheet_or_section": "二次加工装置基础数据",
  "source_location": "A12:H12",
  "dedup_key": "...",
  "secondary_sources": [],
  "validation_status": "PASS",
  "audit_note": ""
}
```

---

# 14. 最终 Excel

`知识规则汇总.xlsx` 必须有且只有 8 个大类 sheet：
- 原油类
- 装置类
- 罐区类
- 调合类
- 产品类
- 停工调度
- 流程协同
- 调度经验

前4列固定：
1. rule_id
2. description
3. sets_json
4. parameters_json

后续审计列可含：
- subcategory
- target_group_id
- extraction_phase
- extraction_mode
- source_file
- source_priority
- source_sheet_or_section
- source_location
- validation_status
- audit_note

审计列不得回写 JSON。

---

# 15. 最终提取报告必须包含

1. 输入根目录与文件总数；
2. **文件梳理/优先级表**；
3. 表格首轮提取统计；
4. 数量基线说明；
5. **表格首轮后：目标 / 已提取 / 剩余矩阵**；
6. 文档补缺计划；
7. 文档补缺实际新增数；
8. duplicate evidence 数量；
9. conflict/revision 情况；
10. 八大类逐子类覆盖；
11. 实体 coverage slot；
12. 计算规则；
13. missing；
14. 四字段 JSON 校验；
15. 8-sheet Excel 一致性。

---

# 16. 最终严格校验

## JSON
- 8个JSON存在；
- 顶层数组；
- 每条恰好4字段；
- set item 恰好3字段；
- parameter item 恰好2字段；
- 无 DEMO；
- rule_id 全局唯一。

## 多文件去重
- dedup_key 唯一 identity 不能输出两条同义规则；
- duplicate evidence 已合并；
- conflict 不得双写。

## 表格优先与补缺
- 必须存在 source inventory；
- 必须存在 table-first 阶段；
- 必须存在 table-first 后 gap plan；
- document_supplement 新增规则必须来自未关闭 target_group/slot；
- 已关闭 group 若有文本证据，只能记 secondary/conflict。

## 数量
- 明确 exact target：报告 remaining；
- 达标 group 后不得继续重复生成；
- approximate/ambiguous 不强制凑数；
- 大类超目标先查重复/粒度/映射；
- 证据不足允许少于目标，报告 missing。

---

# 17. 最终输出结构

```text
outputs/
├── 原油类.json
├── 装置类.json
├── 罐区类.json
├── 调合类.json
├── 产品类.json
├── 停工调度规则.json
├── 流程特征和协同规则.json
├── 调度经验规则.json
├── 知识规则汇总.xlsx
├── 知识规则提取报告.md
├── extraction_manifest.json
├── validation_report.json
├── source_inventory.json
├── 文件梳理与提取计划.md
├── rule_gap_after_tables.json
└── 剩余规则补缺计划.md
```

只有在：
- 四字段校验通过；
- 去重完成；
- 数量缺口已核对；
- 文档补缺只针对剩余项；
- `validation_report.json.valid=true`

后才能声明完成。
