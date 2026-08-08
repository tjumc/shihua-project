# 就医资源推荐系统

这是一个基于 Gradio 的医疗资源推荐 demo，面向保险公司客服或健康管理场景。

核心流程：

1. 上传患者病历、检查报告、体检报告等 PDF/图片资料。
2. 使用 Qwen3-VL 全页分批解析病历，保留完整 `raw_document_text`，再汇总为结构化信息。
3. 根据主诉、既往史、检查异常和患者诉求推断就诊科室。
4. 使用高德地图召回目标城市医院候选，默认城市为上海。
5. 推荐栏默认使用 Qwen 联网搜索直接生成医院-科室-医生推荐，并优先采用医院官网/官方渠道来源。
6. DeepSeek 保留为可切换/兜底链路。
7. 导出 JSON、CSV、Markdown 报告。

没有配置 API key 时，系统会进入演示模式：使用本地 PDF 文本抽取、内置医院候选和启发式排序，便于先检查界面与端到端流程。

## 环境

```bash
conda env create -f environment.yml
conda activate medical_demo
cp .env.example .env
```

编辑 `.env`：

```bash
DASHSCOPE_API_KEY=你的百炼APIKey
AMAP_API_KEY=你的高德Key
DEEPSEEK_API_KEY=你的DeepSeekKey

DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
ASSISTANT_PROVIDER=qwen
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_ASSISTANT_MODEL=qwen3.7-max
QWEN_ASSISTANT_FALLBACK_MODEL=qwen-plus-latest
RECOMMENDATION_PROVIDER=qwen
SEARCH_PROVIDER=deepseek_agent
WEB_SEARCH_PROVIDER=bocha
SEARCH_API_KEY=你的博查或Tavily搜索Key
QWEN_VL_PAGES_PER_CALL=2
```

## 启动

```bash
python app.py
```

默认访问：

```text
http://127.0.0.1:7860
```

## 说明

- 医生推荐优先使用医院官网、医院官方公众号、官方挂号/互联网医院等确切来源；第三方医生平台只作为补充。
- 推荐栏默认使用 Qwen 自带联网搜索直接生成“医院-科室-医生”推荐；如果 Qwen 不可用或结果不足，会尝试 DeepSeek 兜底链路。
- DeepSeek 会生成全网医生/科室核验搜索规划，系统再调用 `WEB_SEARCH_PROVIDER` 指定的网页搜索 API 抓取结果，最后由 DeepSeek 从搜索结果中抽取医生证据并重排推荐。
- 支持 `WEB_SEARCH_PROVIDER=bocha` 或 `WEB_SEARCH_PROVIDER=tavily`。没有网页医生来源时，会继续尝试 DeepSeek 直出医生候选。
- 右侧 AI 医疗助手选择 `Qwen联网` 时，使用 Qwen 自带联网搜索能力回答医院、科室和医生问题，不依赖 Bocha/Tavily；在助手中触发“重新推荐/推荐医院”也会同步更新推荐栏。
- PDF 会按全部页解析；`QWEN_VL_PAGES_PER_CALL` 控制每次送入 Qwen3-VL 的页数，建议 1-3。
- 推荐生成中会显示检索与执行状态；推荐完成后页面仅保留推荐卡片和完成提示，不展示表格或完整日志。
- 该 demo 只做就医资源推荐辅助，不做诊断、不做治疗建议、不做保险核保结论。
