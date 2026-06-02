# JSON 模板清理与固化 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 基于当前 `结构样例-含JSON.xlsx` 和现有 `规则库.json` 草稿，产出一份可直接复用的正式 JSON 模板和字段说明。

**Architecture:** 以 `最终交付表` 中展示的“自然语言 + JSON”格式为正式口径，保留通用结构 `rule_id + description + sets + parameters`，生成 UTF-8、语法合法、便于后续批量整理的模板文件。

**Tech Stack:** PowerShell, Markdown, JSON

---

### Task 1: 确认正式字段口径

**Files:**
- Read: `提取结果/02_过程追溯/03_结构样例/结构样例-含JSON.xlsx`
- Read: `提取结果/02_过程追溯/03_结构样例/结构样例-含JSON-说明.txt`
- Read: `规则库.json`

**Step 1:** 提取 `规则总表` 和 `最终交付表` 中 JSON 示例。

**Step 2:** 对比现有 `规则库.json` 草稿与样例表 JSON 结构。

**Step 3:** 确认本阶段只固化模板，不处理批量规则内容。

### Task 2: 生成正式 JSON 模板

**Files:**
- Create: `json规则库/规则库_JSON模板_正式版.json`
- Create: `json规则库/规则库_JSON模板说明.md`

**Step 1:** 建立 `json规则库` 目录。

**Step 2:** 以 `最终交付表` 口径生成正式 JSON 模板。

**Step 3:** 在说明文档中写清字段含义、推荐映射来源和使用规则。

### Task 3: 校验与交接

**Files:**
- Modify: `AGENT_CONTEXT.md`

**Step 1:** 运行 JSON 合法性校验。

**Step 2:** 在交接文档中补充模板位置和本周新任务方向。

**Step 3:** 向用户汇报模板位置、选择该模板的原因，以及下一步批量整理建议。
