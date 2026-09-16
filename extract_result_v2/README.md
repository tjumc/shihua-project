# 第二版规则样例提取结果

所有 JSON 采用合并口径：以算法接入格式为主，包含 `rule_id`、`type`、`category`、`subcategory`、`subject`、`predicate`、`object`、`when`、`then`、`mapping`、`source` 等字段；同时保留项目组案例格式中的 `description`、`sets`、`parameters` 字段。事实/参数记录使用 `record_type=fact/parameter`，不强行填写约束映射；未找到可靠样例的小类保留 `status=pending`。
