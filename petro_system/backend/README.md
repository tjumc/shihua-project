# 石化知识规则 SQLite 数据库

该模块把正式提交表中的五类、1050 条规则导入本地 SQLite 文件，无需 Docker、数据库服务或云端连接。

## 数据位置

默认数据库：`data/petro_rules.db`

数据库包含：

- `rule_categories`：五类规则字典；
- `rules`：规则主体；
- `source_documents`：规则来源文件；
- `import_batches`：每次导入的数量和状态；
- `rule_change_logs`：规则新增和更新记录；
- `schema_migrations`：数据库结构版本。

## 初始化环境

需要 Python 3.10 或更高版本。在本目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 初始化并导入

正式表路径已经配置为默认值，因此可以直接运行：

```bash
python -m petro_rules.cli validate
python -m petro_rules.cli init
python -m petro_rules.cli import
python -m petro_rules.cli stats
```

重复执行导入不会产生重复规则。规则编号相同但内容发生变化时，程序默认停止导入；人工确认后使用：

```bash
python -m petro_rules.cli import --update-existing
```

## 检索示例

```bash
python -m petro_rules.cli search "原油中断"
python -m petro_rules.cli search "升降温" --category EXP --limit 10
```

## 测试

```bash
python -m unittest discover -s tests -v
```

测试会使用临时 SQLite 文件，不会修改正式数据库。

## 启动可视化界面

在 `petro_system` 目录执行：

```bash
backend/.venv/bin/python app.py
```

默认访问地址为 `http://127.0.0.1:7860`。界面包含真实分类统计、规则筛选与分页、规则详情、新增编辑、归档恢复、导入记录和原有的 Qwen/DeepSeek AI 助手。
