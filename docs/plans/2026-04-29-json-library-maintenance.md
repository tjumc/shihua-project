# JSON 规则库维护结构 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 `json规则库` 建立可持续维护的工作结构，明确当前工作版、历史版本、变更记录和维护规则。

**Architecture:** 保持“模板文件”和“当前工作版”分离，当前工作版使用合法 JSON 空壳初始化并明确状态，历史版本目录只保存快照，变更记录和 README 负责说明维护流程。第一阶段不批量填充 215 条规则，只建立受控维护框架。

**Tech Stack:** PowerShell, JSON, Markdown

---

### Task 1: 建立规则库维护骨架

**Files:**
- Create: `json规则库/历史版本/`
- Create: `json规则库/README.md`
- Create: `json规则库/规则库_当前版.json`
- Create: `json规则库/规则库_变更记录.md`

**Step 1:** 创建 `历史版本` 目录。

**Step 2:** 写入 `README.md`，说明哪个文件是模板、哪个文件是当前工作版。

**Step 3:** 写入 `规则库_当前版.json`，明确当前仅为初始化工作版。

**Step 4:** 写入 `规则库_变更记录.md`，记录初始化动作和后续维护规则。

### Task 2: 创建初始快照

**Files:**
- Create: `json规则库/历史版本/2026-04-29_v1_初始化模板.json`

**Step 1:** 将当前工作版复制一份为初始快照。

**Step 2:** 在变更记录中登记版本号、日期、说明。

### Task 3: 更新交接文档与校验

**Files:**
- Modify: `AGENT_CONTEXT.md`
- Modify: `提取结果--mc/00_项目总览/当前状态一页纸.md`

**Step 1:** 在交接文档中补充规则库维护入口。

**Step 2:** 在当前状态页中补充“本周任务重点转向 JSON 整理”。

**Step 3:** 校验 `规则库_当前版.json` 和历史快照的 JSON 合法性。

**Step 4:** 向用户汇报当前可执行的维护流程。
