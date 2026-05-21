# 石化规则抽取与核验项目

本仓库整理自本地石化项目当前工作区，用于团队协作维护。

## 目录结构

| 目录/文件 | 内容 |
|---|---|
| `AGENT_CONTEXT.md` | 项目背景、数据口径、当前工作状态 |
| `docs/` | 技术报告、方案文档、计划文档、参考资料 |
| `scripts/` | JSON 规则库导出、校验、修复等脚本 |
| `skill documents/` | 规则核验 skill 文档、脚本和示例 |
| `json规则库/` | 当前 JSON 规则库、分类规则、历史版本、模板和变更记录 |
| `延长数据/` | 项目源文件，包括操作规程、报表、截图、应急预案等 |
| `提取结果--mc/` | 当前规则提取结果、过程追溯、人工确认、交付快照和周报 |
| `petrochemical-rule-extraction.zip` | 规则提取 skill 压缩包 |
| `PROJECT_MANIFEST.csv` | 本次整理后的文件清单 |

## 当前核心产出

- 规则提取结果：`提取结果--mc/01_当前结果/`
- JSON 规则库：`json规则库/规则库_当前版.json`
- 分类 JSON：`json规则库/current/`
- 规则核验 skill：`skill documents/petrochemical-rule-verification/`
- 规则核验 Demo：`提取结果--mc/00_项目总览/汇报附件/rule_verification_skill_demo/`
- 周报归档：`提取结果--mc/00_项目总览/周报归档/`

## 常用脚本

```powershell
# 导出 JSON 规则库
python scripts/export_rules_to_json.py

# 校验 JSON 规则库
python scripts/validate_rule_library.py
```

规则核验 skill 脚本位于：

```text
skill documents/petrochemical-rule-verification/scripts/
```

## 本次整理规则

已保留：

- 当前文档、脚本、skill、规则库、源文件和当前产出；
- 规则核验 Demo 及周报展示所需图片；
- JSON 规则库历史版本。

已排除：

- 根目录 `90_项目级归档/`；
- `提取结果--mc/90_历史归档/`；
- `__pycache__/`、`.pyc`；
- `live_output/`；
- Office 临时锁文件 `~$*`。

## 提交建议

本项目包含业务源文件、报表、规程和截图。上传 GitHub 前建议确认仓库权限，优先使用私有仓库。
