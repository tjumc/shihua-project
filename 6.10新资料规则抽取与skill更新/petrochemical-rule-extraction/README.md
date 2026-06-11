# petrochemical-rule-extraction

用于从石化项目目录中的文本 PDF、扫描/图片型 PDF、DOC/DOCX、TXT、XLS/XLSX 文件中一次性抽取 5 类知识规则：

- 质量标准规则
- 工艺规范规则
- 流程特征规则
- 操作规程规则
- 调度经验规则

## 内置模板

```text
templates/rule_summary_template.xls
```

该模板包含 5 个空白子表，保留格式和列头：

- `1、质量标准规则`
- `2、工艺规范规则`
- `3、流程特征规则`
- `4、操作规程规则`
- `5、调度经验规则`

5 个子表字段顺序均为：

```text
规则编号, 规则名称, 知识类型, 子类型, 适用范围, 规则内容, 来源文件, 具体页码, 原文内容, JSON, 备注
```

最终输出中 `规则内容` / JSON `rule_content` 必须全局去重，不得出现完全重复的规则内容。规则内容必须写成梳理后的结论式规则，不使用“针对+原文片段”的拼接表达，也不得包含页码、文件名、表号、目录文字、省略号、OCR 乱码或机械解析词。

## 扫描 PDF

扫描件 PDF 通过 OCR 解析；英文 PDF 可先翻译成中文 DOCX。默认使用当前 Python 的文档解析依赖和 `claude` conda 环境中的 Tesseract：

```bash
conda activate claude
```

整本 PDF/书籍转换为中文 DOCX：

```bash
python scripts/pdf_to_chinese_docx.py <PDF_OR_DIR> <DOCX_OR_DIR> --batch --translate auto --ocr-lang chi_sim+eng --ocr-workers 2
```

单独 OCR 扫描 PDF 文本块：

```bash
conda run -n claude python scripts/ocr_scanned_pdf.py <INPUT_PDF> <OCR_WORK_DIR> --lang chi_sim+eng --dpi 300
```

抽查 OCR 或翻译质量时可先加 `--max-pages 1`。正式处理整本书时去掉 `--max-pages`。

OCR 中间文件只用于解析，不作为最终交付物。

## 调用示例

```text
请使用 petrochemical-rule-extraction skill，扫描 ./project_docs，输出规则到 ./rule_output。
要求使用内置 Excel 模板，最终只生成 extracted_rules.xls 和 5 类 JSON，一次性抽取质量标准、工艺规范、流程特征、操作规程和调度经验规则，不生成 mask、置信度、人工核验或人工核对字段。
```

最终输出文件只保留：

```text
extracted_rules.xls
质量标准规则.json
工艺规范规则.json
流程特征规则.json
操作规程规则.json
调度经验规则.json
```

5 类 JSON 均为数组，每条规则字段参考项目中的 `工艺规范规则.json`：

```text
rule_id, rule_name, knowledge_type, sub_type, applicable_scope, rule_content,
source_file, locator, evidence_text, parameters, devices, operations,
conditions, constraint_type, notes
```

基于 `parsed_docx` 或文本 PDF 生成规则：

```bash
python scripts/extract_rules_from_docs.py <PROJECT_DIR> <OUTPUT_DIR> --min-rules 500
```

如果 5 类 JSON 已经人工或程序更新，只需按 JSON 重新生成并校验 Excel：

```bash
python scripts/sync_excel_from_json.py <OUTPUT_DIR>
```
