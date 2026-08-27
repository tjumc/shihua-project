# 石化知识规则库项目

本仓库保留石化五类知识规则的最终成果、本地 SQLite 数据库、可视化管理系统和正式说明文档。

## 目录结构

```text
data/
├── tables/                         # 五类规则正式表
│   └── 五类规则正式提交表_1050条.xlsx
└── json/                           # 五类 JSON 规则

petro_system/
├── app.py                          # 可视化系统入口
├── images/                         # 系统页面资源
├── ai_assistant/                   # AI 助手调用配置
└── backend/
    ├── data/petro_rules.db         # SQLite 数据库
    ├── migrations/                 # 数据库结构迁移
    ├── petro_rules/                # 导入、查询和管理代码
    └── tests/                      # 自动化测试

docs/                               # 项目状态、周报、技术报告和演示材料
```

## 当前成果

- SQLite 数据库包含 1050 条规则；
- 五类规则分别为操作规程、质量标准、流程特征、工艺规范和调度经验；
- 数据库支持规则检索、分类统计、详情编辑、归档恢复和导入记录查询；
- AI 助手保留原有 Qwen/DeepSeek API 调用能力。

## 启动系统

需要 Python 3.10 或更高版本。在项目目录执行：

```bash
cd petro_system
backend/.venv/bin/python app.py
```

然后访问 `http://127.0.0.1:7860`。

## 数据库维护

```bash
cd petro_system/backend
.venv/bin/python -m petro_rules.cli validate
.venv/bin/python -m petro_rules.cli import
.venv/bin/python -m unittest discover -s tests -v
```

正式 Excel 默认位置为 `data/tables/五类规则正式提交表_1050条.xlsx`。原始资料、历史版本和过程文件不放入本仓库主目录。
