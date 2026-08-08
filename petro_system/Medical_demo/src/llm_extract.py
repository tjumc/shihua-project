from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from .config import AppConfig
from .department_infer import infer_departments, infer_urgency
from .pdf_loader import LoadedDocument, LoadedPage, build_text_blob, guess_mime, load_uploaded_files
from .schemas import ExamResult, PatientProfile


def extract_medical_profile(
    file_paths: list[str | Path],
    config: AppConfig,
    max_pages_per_file: int = 0,
    progress: Any | None = None,
) -> tuple[PatientProfile, list[dict[str, object]], str]:
    _update_progress(progress, 0.01, "准备读取文件")
    docs = load_uploaded_files(
        file_paths=file_paths,
        uploads_dir=config.uploads_dir,
        cache_dir=config.cache_dir,
        max_pages_per_file=max_pages_per_file,
    )
    logs: list[str] = []
    logs.append(f"已读取 {len(docs)} 个文件。")
    total_pages = sum(len(doc.pages) for doc in docs)
    parse_mode = (config.medical_record_parse_mode or "qwen_ocr").strip().lower()
    mode_label = "文字识别模型" if parse_mode in {"qwen_ocr", "ocr", "qwen-vl-ocr"} else "视觉结构化模型"
    if total_pages:
        _update_progress(progress, 0.08, f"已渲染 {total_pages} 页，准备调用 {mode_label}")
    for doc in docs:
        if doc.warnings:
            logs.append(f"{doc.file_name}：{'；'.join(doc.warnings)}")

    if config.dashscope_api_key:
        try:
            if parse_mode in {"qwen_ocr", "ocr", "qwen-vl-ocr"}:
                profile, qwen_logs = _extract_with_qwen_ocr(docs, config, progress=progress)
                logs.extend(qwen_logs)
                logs.append(
                    "已调用文字识别模型完成全文识别。"
                )
            else:
                profile, qwen_logs = _extract_with_qwen_vl(docs, config, progress=progress)
                logs.extend(qwen_logs)
                logs.append("已调用视觉结构化模型完成全页分批抽取。")
        except Exception as exc:
            logs.append(f"模型抽取失败，已切换本地演示解析：{exc}")
            profile = _fallback_extract(docs, config)
    else:
        logs.append("未配置文字识别模型密钥，使用本地演示解析。")
        profile = _fallback_extract(docs, config)

    profile.source_files = [doc.file_name for doc in docs]
    if not profile.department_candidates:
        profile.department_candidates = infer_departments(profile)
    urgency, flags = infer_urgency(profile)
    profile.urgency_level = urgency
    for flag in flags:
        if flag not in profile.risk_flags:
            profile.risk_flags.append(flag)

    table_rows = [doc.table_row() for doc in docs]
    _update_progress(progress, 1.0, "病历解析完成")
    return profile, table_rows, "\n".join(logs)


def _extract_with_qwen_ocr(
    docs: list[LoadedDocument],
    config: AppConfig,
    progress: Any | None = None,
) -> tuple[PatientProfile, list[str]]:
    pages = _collect_pages(docs)
    text_blob = build_text_blob(docs, max_chars=None)
    if not pages and not text_blob:
        raise ValueError("未从上传资料中得到可解析的文本或图片。")

    logs: list[str] = []
    pages_with_images = [page for page in pages if page.image_path and page.image_path.exists()]
    raw_pages: list[dict[str, Any]] = []

    if pages_with_images:
        total_pages = len(pages_with_images)
        for index, page in enumerate(pages_with_images, start=1):
            _update_progress(
                progress,
                0.08 + 0.84 * ((index - 1) / max(1, total_pages)),
                f"文字识别模型正在识别第 {index}/{total_pages} 页",
            )
            text = _extract_page_text_with_qwen_ocr(page, config)
            raw_pages.append(
                {
                    "source_file": page.source_file,
                    "page_number": page.page_number,
                    "text": text or page.text or "",
                }
            )
            logs.append(f"已识别 {page.source_file} 第 {page.page_number} 页。")
            _update_progress(
                progress,
                0.08 + 0.84 * (index / max(1, total_pages)),
                f"文字识别已完成 {index}/{total_pages} 页",
            )
    else:
        logs.append("未发现可渲染页面图片，使用 PDF 文本层。")

    if not any(_to_str(page.get("text")) for page in raw_pages):
        raw_pages = _raw_pages_from_pdf_text(pages)
    full_text = _raw_text_from_pages(raw_pages) or text_blob

    _update_progress(progress, 0.93, "Qwen 文本模型正在生成患者摘要和结构化病历")
    try:
        profile = _extract_profile_with_qwen_text(full_text, raw_pages, docs, config)
        logs.append(f"Qwen 文本模型 {config.text_model} 已生成患者摘要、结构化病历和科室候选。")
    except Exception as exc:
        logs.append(f"Qwen 文本模型生成患者摘要和结构化病历失败，保留本地规则结果：{exc}")
        profile = _fallback_extract(docs, config, override_text=full_text)

    source_files = [doc.file_name for doc in docs]
    profile.raw_page_texts = raw_pages
    profile.raw_document_text = full_text
    profile.source_files = source_files
    if not profile.present_illness:
        profile.present_illness = _summary_from_text(full_text)
    if not profile.exam_results:
        profile.exam_results = _extract_exam_lines(full_text, source_files)
    if not profile.suspected_diagnoses:
        profile.suspected_diagnoses = _guess_diagnoses(full_text, profile.exam_results)
    profile.missing_information = list(dict.fromkeys([*profile.missing_information, *_missing_information(profile)]))
    if not profile.department_candidates:
        profile.department_candidates = infer_departments(profile)
    _update_progress(progress, 0.95, "正在整理文字识别结果")
    return profile, logs


def _extract_profile_with_deepseek_text(
    full_text: str,
    raw_pages: list[dict[str, Any]],
    docs: list[LoadedDocument],
    config: AppConfig,
) -> PatientProfile:
    from .deepseek_agent import _call_deepseek_json

    prompt = config.read_prompt("deepseek_extract_medical_record.md") or (
        "你是严谨的医疗文档结构化抽取助手。请基于文字识别原文抽取客观医学事实，"
        "输出严格 JSON，字段贴合 PatientProfile schema。"
    )
    payload = {
        "source_files": [doc.file_name for doc in docs],
        "raw_page_texts": raw_pages,
        "raw_document_text": full_text,
        "patient_profile_schema": PatientProfile().model_dump(),
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是严谨的医疗病历结构化助手。只能依据用户提供的文字识别原文抽取事实；"
                "不要编造患者信息、诊断、检查结果、医院或医生；不要输出治疗建议。"
            ),
        },
        {
            "role": "user",
            "content": f"{prompt}\n\n输入数据：\n{json.dumps(payload, ensure_ascii=False)}",
        },
    ]
    data = _call_deepseek_json(config, messages)
    profile = _profile_from_model_data(data)
    if not profile.raw_document_text:
        profile.raw_document_text = full_text
    if not profile.raw_page_texts:
        profile.raw_page_texts = raw_pages
    return profile


def _extract_profile_with_qwen_text(
    full_text: str,
    raw_pages: list[dict[str, Any]],
    docs: list[LoadedDocument],
    config: AppConfig,
) -> PatientProfile:
    from openai import OpenAI

    prompt = (
        config.read_prompt("extract_medical_record.md")
        or config.read_prompt("deepseek_extract_medical_record.md")
        or (
            "你是严谨的医疗文档结构化抽取助手。请基于文字识别原文抽取客观医学事实，"
            "输出严格 JSON，字段贴合 PatientProfile schema。"
        )
    )
    payload = {
        "source_files": [doc.file_name for doc in docs],
        "raw_page_texts": raw_pages,
        "raw_document_text": full_text,
        "patient_profile_schema": PatientProfile().model_dump(),
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是严谨的医疗病历结构化助手。只能依据用户提供的文字识别原文抽取事实；"
                "不要编造患者信息、诊断、检查结果、医院或医生；不要输出治疗建议。"
            ),
        },
        {
            "role": "user",
            "content": f"{prompt}\n\n输入数据：\n{json.dumps(payload, ensure_ascii=False)}",
        },
    ]
    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.qwen_base_url)
    try:
        response = client.chat.completions.create(
            model=config.text_model,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except Exception:
        response = client.chat.completions.create(
            model=config.text_model,
            messages=messages,
            temperature=0.1,
        )
    raw = response.choices[0].message.content or "{}"
    data = _loads_json_object(raw)
    profile = _profile_from_model_data(data)
    if not profile.raw_document_text:
        profile.raw_document_text = full_text
    if not profile.raw_page_texts:
        profile.raw_page_texts = raw_pages
    return profile


def _extract_page_text_with_qwen_ocr(page: LoadedPage, config: AppConfig) -> str:
    if not page.image_path:
        return page.text or ""
    import dashscope

    dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"
    image_path = page.image_path.resolve()
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {"text": "请仅输出图像中的文本内容，不要解释，不要总结，不要使用 Markdown。"},
            ],
        }
    ]
    response = dashscope.MultiModalConversation.call(
        api_key=config.dashscope_api_key,
        model=config.ocr_model,
        messages=messages,
    )
    return _extract_dashscope_text(response)


def _extract_with_qwen_vl(
    docs: list[LoadedDocument],
    config: AppConfig,
    progress: Any | None = None,
) -> tuple[PatientProfile, list[str]]:
    pages = _collect_pages(docs)
    text_blob = build_text_blob(docs, max_chars=None)
    if not pages and not text_blob:
        raise ValueError("未从上传资料中得到可解析的文本或图片。")

    from openai import OpenAI

    logs: list[str] = []
    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)
    batch_size = max(1, config.qwen_vl_pages_per_call)
    page_payloads: list[dict[str, Any]] = []
    pages_with_images = [page for page in pages if page.image_path and page.image_path.exists()]

    if pages_with_images:
        total_batches = (len(pages_with_images) + batch_size - 1) // batch_size
        total_pages = len(pages_with_images)
        completed_pages = 0
        for batch_index in range(total_batches):
            batch = pages_with_images[batch_index * batch_size : (batch_index + 1) * batch_size]
            first_page = batch[0].page_number
            last_page = batch[-1].page_number
            _update_progress(
                progress,
                0.08 + 0.84 * (completed_pages / max(1, total_pages)),
                f"视觉结构化模型正在解析第 {first_page}-{last_page} 页 / 共 {total_pages} 页",
            )
            data = _extract_page_batch_with_qwen_vl(batch, client, config)
            page_payloads.append(data)
            completed_pages += len(batch)
            _update_progress(
                progress,
                0.08 + 0.84 * (completed_pages / max(1, total_pages)),
                f"视觉结构化模型已完成 {completed_pages}/{total_pages} 页",
            )
            logs.append(
                f"视觉结构化模型已解析第 {batch_index + 1}/{total_batches} 批，"
                f"覆盖 {len(batch)} 页。"
            )
    else:
        logs.append("未发现可渲染页面图片，使用 PDF 文本层进行结构化。")

    merged = _merge_qwen_page_payloads(page_payloads)
    if not merged.get("raw_page_texts"):
        merged["raw_page_texts"] = _raw_pages_from_pdf_text(pages)
    qwen_text = _raw_text_from_pages(merged["raw_page_texts"])
    full_text = qwen_text or text_blob
    merged["raw_document_text"] = full_text
    if not merged.get("present_illness"):
        merged["present_illness"] = _summary_from_text(full_text)

    profile = _profile_from_model_data(merged)
    profile.raw_document_text = full_text
    profile.raw_page_texts = merged.get("raw_page_texts", [])
    if not profile.exam_results and full_text:
        profile.exam_results = _extract_exam_lines(full_text, [doc.file_name for doc in docs])
    _update_progress(progress, 0.95, "正在整理结构化结果")
    return profile, logs


def _extract_page_batch_with_qwen_vl(
    batch: list[LoadedPage],
    client: Any,
    config: AppConfig,
) -> dict[str, Any]:
    prompt = config.read_prompt("extract_medical_record.md") or "请抽取病历结构化信息，输出严格 JSON。"
    page_descriptions = "\n".join(
        f"{index + 1}. image_index={index + 1}, source_file={page.source_file}, "
        f"page_number={page.page_number}"
        for index, page in enumerate(batch)
    )
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"{prompt}\n\n"
                "请逐页完整识别图片中的所有可见文字，不要摘要、不要截断、不要省略表格行。"
                "同时抽取页面中明确出现的患者基本信息、生命体征、检查结果、诊断/问题。"
                "输出必须是严格 JSON，不要输出 Markdown。\n\n"
                "本批图片顺序如下：\n"
                f"{page_descriptions}\n\n"
                "JSON 格式：\n"
                "{\n"
                '  "pages": [\n'
                '    {"image_index": 1, "source_file": "...", "page_number": 1, "text": "完整OCR文字"}\n'
                "  ],\n"
                '  "patient_basic": {"name": "", "gender": "", "age": null, "city": "上海"},\n'
                '  "chief_complaint": "",\n'
                '  "present_illness": "",\n'
                '  "past_history": [],\n'
                '  "current_symptoms": [],\n'
                '  "vital_signs": {"temperature": null, "blood_pressure": "", "heart_rate": null},\n'
                '  "exam_results": [\n'
                '    {"date": "", "test_name": "", "result": "", "unit": "", '
                '"reference_range": "", "abnormal": false, "page": 1}\n'
                "  ],\n"
                '  "suspected_diagnoses": [],\n'
                '  "missing_information": []\n'
                "}"
            ),
        }
    ]
    for page in batch:
        path = page.image_path
        if not path:
            continue
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _image_to_data_url(path)},
            }
        )

    messages = [
        {"role": "system", "content": "你是严谨的医疗文档结构化抽取助手。"},
        {"role": "user", "content": content},
    ]
    try:
        response = client.chat.completions.create(
            model=config.vision_model,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except Exception:
        response = client.chat.completions.create(
            model=config.vision_model,
            messages=messages,
            temperature=0.1,
        )
    raw = response.choices[0].message.content or "{}"
    data = _loads_json_object(raw)
    return _normalize_page_batch_payload(data, batch, raw)


def _fallback_extract(docs: list[Any], config: AppConfig, override_text: str | None = None) -> PatientProfile:
    text = override_text if override_text is not None else build_text_blob(docs, max_chars=None)
    source_names = [doc.file_name for doc in docs]
    profile = PatientProfile()
    profile.patient_basic.name = _guess_name(source_names, text)
    profile.patient_basic.gender = _search_first(text, [r"性别[:： ]*([男女])", r"\b([男女])\b"])
    age = _search_first(text, [r"年龄[:： ]*(\d{1,3})", r"(\d{1,3})\s*岁"])
    profile.patient_basic.age = int(age) if age and age.isdigit() else None
    profile.patient_basic.city = config.default_city

    symptoms = _match_keywords(
        text,
        [
            "胸痛",
            "胸闷",
            "心悸",
            "咳嗽",
            "咳痰",
            "发热",
            "气促",
            "呼吸困难",
            "腹痛",
            "头晕",
            "头痛",
            "腰痛",
            "关节痛",
            "乏力",
            "水肿",
        ],
    )
    profile.current_symptoms = symptoms
    profile.chief_complaint = "、".join(symptoms[:4]) if symptoms else "上传资料待进一步结构化解析"
    profile.present_illness = _summary_from_text(text)
    profile.past_history = _match_keywords(
        text,
        ["高血压", "糖尿病", "冠心病", "脑梗", "肿瘤", "哮喘", "慢阻肺", "肾病", "手术史"],
    )
    profile.allergy_history = _extract_allergy(text)
    profile.surgery_history = _extract_surgery(text)
    profile.exam_results = _extract_exam_lines(text, source_names)
    profile.suspected_diagnoses = _guess_diagnoses(text, profile.exam_results)
    profile.missing_information = _missing_information(profile)
    profile.department_candidates = infer_departments(profile)
    profile.raw_document_text = text
    profile.raw_page_texts = _raw_pages_from_pdf_text(_collect_pages(docs))
    return profile


def _collect_pages(docs: list[LoadedDocument]) -> list[LoadedPage]:
    pages: list[LoadedPage] = []
    for doc in docs:
        pages.extend(doc.pages)
    return pages


def _normalize_page_batch_payload(
    data: dict[str, Any],
    batch: list[LoadedPage],
    raw: str,
) -> dict[str, Any]:
    normalized = _normalize_profile_data(data)
    page_rows = data.get("pages") if isinstance(data, dict) else []
    if not isinstance(page_rows, list):
        page_rows = []

    mapped_pages: list[dict[str, Any]] = []
    for index, source_page in enumerate(batch, start=1):
        matched = _find_page_row(page_rows, index, source_page)
        text = ""
        if isinstance(matched, dict):
            text = _to_str(matched.get("text") or matched.get("ocr_text") or matched.get("content"))
        if not text:
            text = source_page.text or ""
        mapped_pages.append(
            {
                "source_file": source_page.source_file,
                "page_number": source_page.page_number,
                "text": text,
            }
        )

    normalized["raw_page_texts"] = mapped_pages
    if not any(page["text"] for page in mapped_pages) and raw:
        normalized["raw_page_texts"] = [
            {
                "source_file": batch[0].source_file if batch else "",
                "page_number": batch[0].page_number if batch else 1,
                "text": raw,
            }
        ]
    return normalized


def _find_page_row(
    rows: list[Any],
    image_index: int,
    source_page: LoadedPage,
) -> dict[str, Any] | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_index = _to_int(row.get("image_index") or row.get("index"))
        row_page = _to_int(row.get("page_number") or row.get("page") or row.get("页码"))
        row_file = _to_str(row.get("source_file") or row.get("file"))
        if row_index == image_index:
            return row
        if row_page == source_page.page_number and (not row_file or row_file == source_page.source_file):
            return row
    if image_index - 1 < len(rows) and isinstance(rows[image_index - 1], dict):
        return rows[image_index - 1]
    return None


def _merge_qwen_page_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "patient_basic": {},
        "chief_complaint": "",
        "present_illness": "",
        "past_history": [],
        "allergy_history": [],
        "surgery_history": [],
        "current_symptoms": [],
        "vital_signs": {},
        "exam_results": [],
        "suspected_diagnoses": [],
        "department_candidates": [],
        "missing_information": [],
        "risk_flags": [],
        "raw_page_texts": [],
    }
    for payload in payloads:
        basic = payload.get("patient_basic") or {}
        if isinstance(basic, dict):
            for key, value in basic.items():
                if value not in {None, ""} and not merged["patient_basic"].get(key):
                    merged["patient_basic"][key] = value

        vitals = payload.get("vital_signs") or {}
        if isinstance(vitals, dict):
            for key, value in vitals.items():
                if value not in {None, ""} and not merged["vital_signs"].get(key):
                    merged["vital_signs"][key] = value

        for text_key in ["chief_complaint", "present_illness"]:
            value = _to_str(payload.get(text_key))
            if value and value not in merged[text_key]:
                merged[text_key] = "；".join([part for part in [merged[text_key], value] if part])

        for list_key in [
            "past_history",
            "allergy_history",
            "surgery_history",
            "current_symptoms",
            "suspected_diagnoses",
            "department_candidates",
            "missing_information",
            "risk_flags",
            "exam_results",
            "raw_page_texts",
        ]:
            value = payload.get(list_key)
            if isinstance(value, list):
                merged[list_key].extend(value)
            elif value:
                merged[list_key].append(value)

    for list_key in [
        "past_history",
        "allergy_history",
        "surgery_history",
        "current_symptoms",
        "suspected_diagnoses",
        "missing_information",
        "risk_flags",
    ]:
        merged[list_key] = list(dict.fromkeys(_to_str(item) for item in merged[list_key] if _to_str(item)))
    merged["exam_results"] = _dedupe_exam_results(merged["exam_results"])
    return _normalize_profile_data(merged)


def _dedupe_exam_results(items: list[Any]) -> list[Any]:
    seen: set[tuple[str, str, str, int | None]] = set()
    unique: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (
            _to_str(item.get("date")),
            _to_str(item.get("item") or item.get("test_name")),
            _to_str(item.get("result")),
            _to_int(item.get("source_page") or item.get("page")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _raw_pages_from_pdf_text(pages: list[LoadedPage]) -> list[dict[str, Any]]:
    return [
        {
            "source_file": page.source_file,
            "page_number": page.page_number,
            "text": page.text or "",
        }
        for page in pages
    ]


def _raw_text_from_pages(pages: list[dict[str, Any]]) -> str:
    chunks = []
    for page in pages:
        text = _to_str(page.get("text"))
        if not text:
            continue
        chunks.append(
            f"[{_to_str(page.get('source_file'))} 第{page.get('page_number') or ''}页]\n{text}"
        )
    return "\n\n".join(chunks)


def _profile_from_model_data(data: dict[str, Any]) -> PatientProfile:
    if "patient_profile" in data and isinstance(data["patient_profile"], dict):
        data = data["patient_profile"]
    data = _normalize_profile_data(data)
    try:
        return PatientProfile.model_validate(data)
    except Exception as exc:
        profile = _salvage_profile_from_data(data)
        profile.missing_information.append(f"模型输出未完全匹配 schema，已尽量修复关键字段：{exc}")
        return profile


def _normalize_profile_data(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data or {})
    patient_basic = normalized.get("patient_basic") or normalized.get("patient_info") or normalized.get("basic_info") or {}
    if not isinstance(patient_basic, dict):
        patient_basic = {}
    normalized["patient_basic"] = _normalize_patient_basic(patient_basic)

    vital_signs = normalized.get("vital_signs") or normalized.get("vitals") or {}
    if not isinstance(vital_signs, dict):
        vital_signs = {}
    normalized["vital_signs"] = _normalize_vital_signs(vital_signs)

    for key in [
        "past_history",
        "allergy_history",
        "surgery_history",
        "current_symptoms",
        "suspected_diagnoses",
        "missing_information",
        "risk_flags",
        "source_files",
    ]:
        value = normalized.get(key)
        if value is None:
            normalized[key] = []
        elif isinstance(value, str):
            normalized[key] = [value] if value.strip() else []
        elif isinstance(value, dict):
            normalized[key] = [json.dumps(value, ensure_ascii=False)]

    normalized["exam_results"] = _normalize_exam_results(
        normalized.get("exam_results") or normalized.get("exams") or normalized.get("检查结果") or []
    )
    normalized["department_candidates"] = _normalize_department_candidates(
        normalized.get("department_candidates") or normalized.get("departments") or []
    )
    normalized["chief_complaint"] = _to_str(normalized.get("chief_complaint"))
    normalized["present_illness"] = _to_str(normalized.get("present_illness"))
    normalized["raw_document_text"] = _to_str(normalized.get("raw_document_text"))
    raw_pages = normalized.get("raw_page_texts") or normalized.get("pages") or []
    normalized["raw_page_texts"] = raw_pages if isinstance(raw_pages, list) else []
    if normalized.get("urgency_level") not in {"routine", "soon", "urgent"}:
        normalized["urgency_level"] = "routine"
    return normalized


def _normalize_patient_basic(value: dict[str, Any]) -> dict[str, Any]:
    age = value.get("age") or value.get("年龄")
    return {
        "name": _to_str(value.get("name") or value.get("姓名")),
        "gender": _normalize_gender(value.get("gender") or value.get("性别")),
        "age": _to_int(age),
        "city": _to_str(value.get("city") or value.get("城市")) or "上海",
        "insurance_context": _to_str(value.get("insurance_context") or value.get("保险场景")),
    }


def _normalize_vital_signs(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature": _to_float(value.get("temperature") or value.get("体温")),
        "blood_pressure": _to_str(value.get("blood_pressure") or value.get("血压")),
        "heart_rate": _to_int(value.get("heart_rate") or value.get("心率")),
    }


def _normalize_exam_results(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            rows.append({"item": "检查结果", "result": item})
            continue
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "date": _to_str(item.get("date") or item.get("日期")),
                "type": _to_str(item.get("type") or item.get("类型")) or _guess_exam_type(_to_str(item)),
                "item": _to_str(
                    item.get("item")
                    or item.get("test_name")
                    or item.get("name")
                    or item.get("project")
                    or item.get("项目")
                ),
                "result": _to_str(item.get("result") or item.get("结果") or item.get("value")),
                "unit": _to_str(item.get("unit") or item.get("单位")),
                "reference_range": _to_str(item.get("reference_range") or item.get("参考范围")),
                "abnormal": _to_bool(item.get("abnormal") or item.get("是否异常")),
                "source_page": _to_int(item.get("source_page") or item.get("page") or item.get("页码")),
                "source_file": _to_str(item.get("source_file") or item.get("来源文件")),
            }
        )
    return rows


def _normalize_department_candidates(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            rows.append({"department": item, "reason": "", "confidence": 0.5})
        elif isinstance(item, dict):
            department = _to_str(item.get("department") or item.get("科室"))
            if department:
                rows.append(
                    {
                        "department": department,
                        "reason": _to_str(item.get("reason") or item.get("依据")),
                        "confidence": _to_float(item.get("confidence") or item.get("置信度")) or 0.5,
                    }
                )
    return rows


def _salvage_profile_from_data(data: dict[str, Any]) -> PatientProfile:
    dumped = json.dumps(data, ensure_ascii=False)
    profile = PatientProfile()
    profile.patient_basic.name = _search_first(dumped, [r'"name"\s*:\s*"([^"]+)"', r'"姓名"\s*:\s*"([^"]+)"'])
    profile.patient_basic.gender = _normalize_gender(
        _search_first(dumped, [r'"gender"\s*:\s*"([^"]+)"', r'"性别"\s*:\s*"([^"]+)"'])
    )
    age = _search_first(dumped, [r'"age"\s*:\s*(\d{1,3})', r'"年龄"\s*:\s*(\d{1,3})'])
    profile.patient_basic.age = _to_int(age)
    profile.present_illness = _summary_from_text(dumped)
    profile.raw_document_text = dumped
    return profile


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _to_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    match = re.search(r"\d{1,3}", str(value))
    return int(match.group(0)) if match else None


def _to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _to_str(value).lower()
    return text in {"true", "1", "yes", "y", "异常", "是", "阳性", "增高", "降低"}


def _normalize_gender(value: Any) -> str:
    text = _to_str(value)
    if text in {"男", "男性", "male", "M"}:
        return "男"
    if text in {"女", "女性", "female", "F"}:
        return "女"
    return text


def _loads_json_object(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _extract_dashscope_text(response: Any) -> str:
    try:
        content = response.output.choices[0].message.content
    except Exception as exc:
        message = getattr(response, "message", "") or getattr(response, "code", "") or str(response)
        raise RuntimeError(f"文字识别模型未返回有效文本：{message}") from exc

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(part.strip() for part in parts if part and part.strip())
    return _to_str(content)


def _update_progress(progress: Any | None, value: float, desc: str) -> None:
    if progress is None:
        return
    try:
        progress(min(max(value, 0.0), 1.0), desc=desc)
    except Exception:
        return


def _image_to_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{guess_mime(path)};base64,{encoded}"


def _profile_schema_hint() -> str:
    return json.dumps(PatientProfile().model_dump(), ensure_ascii=False, indent=2)


def _guess_name(source_names: list[str], text: str) -> str:
    name = _search_first(text, [r"姓名[:： ]*([\u4e00-\u9fa5]{2,4})"])
    if name:
        return name
    if not source_names:
        return ""
    stem = Path(source_names[0]).stem
    stem = re.sub(r"^[a-f0-9]{10}_", "", stem)
    stem = re.sub(r"^\d+", "", stem)
    stem = re.sub(r"[（(].*?[）)]", "", stem)
    return stem.strip()


def _search_first(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def _match_keywords(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def _summary_from_text(text: str) -> str:
    if not text.strip():
        return "资料未能抽取出文本，建议配置视觉结构化模型后使用图片解析。"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    useful = [
        line
        for line in lines
        if any(keyword in line for keyword in ["主诉", "现病史", "诊断", "检查", "报告", "印象", "提示"])
    ]
    return "；".join(useful[:8])[:1200] or "；".join(lines[:8])[:1200]


def _extract_allergy(text: str) -> list[str]:
    if "过敏" not in text:
        return []
    lines = [line.strip() for line in text.splitlines() if "过敏" in line]
    return lines[:5]


def _extract_surgery(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if "手术" in line]
    return lines[:5]


def _extract_exam_lines(text: str, source_names: list[str]) -> list[ExamResult]:
    if not text.strip():
        return []
    keywords = [
        "血常规",
        "尿常规",
        "CT",
        "MRI",
        "磁共振",
        "超声",
        "心电图",
        "肝功能",
        "肾功能",
        "肌酐",
        "血糖",
        "胆固醇",
        "甘油三酯",
        "尿酸",
        "肿瘤标志物",
        "病理",
        "阳性",
        "阴性",
        "异常",
        "增高",
        "降低",
    ]
    rows: list[ExamResult] = []
    source_file = source_names[0] if source_names else ""
    for line in text.splitlines():
        clean = line.strip()
        if len(clean) < 4 or len(clean) > 180:
            continue
        if any(keyword in clean for keyword in keywords):
            rows.append(
                ExamResult(
                    type=_guess_exam_type(clean),
                    item=_guess_exam_item(clean),
                    result=clean,
                    abnormal=any(flag in clean for flag in ["异常", "增高", "降低", "阳性", "占位", "结节"]),
                    source_file=source_file,
                )
            )
        if len(rows) >= 30:
            break
    return rows


def _guess_exam_type(line: str) -> str:
    if any(keyword in line for keyword in ["CT", "MRI", "磁共振", "影像", "超声"]):
        return "imaging"
    if "心电" in line:
        return "ecg"
    if "病理" in line:
        return "pathology"
    if any(keyword in line for keyword in ["血", "尿", "肌酐", "尿酸", "胆固醇"]):
        return "lab"
    return "other"


def _guess_exam_item(line: str) -> str:
    for keyword in ["血常规", "尿常规", "胸部CT", "CT", "MRI", "磁共振", "超声", "心电图", "肝功能", "肾功能", "病理"]:
        if keyword in line:
            return keyword
    return line[:24]


def _guess_diagnoses(text: str, exams: list[ExamResult]) -> list[str]:
    diagnoses = _match_keywords(
        text,
        ["高血压", "糖尿病", "冠心病", "肺炎", "慢阻肺", "脑梗死", "骨折", "肿瘤", "肾功能不全"],
    )
    if not diagnoses:
        for exam in exams:
            if "结节" in exam.result:
                diagnoses.append("结节性质待评估")
            if "占位" in exam.result:
                diagnoses.append("占位性病变待评估")
    return list(dict.fromkeys(diagnoses))[:8]


def _missing_information(profile: PatientProfile) -> list[str]:
    missing = []
    if not profile.patient_basic.age:
        missing.append("年龄")
    if not profile.patient_basic.gender:
        missing.append("性别")
    if not profile.current_symptoms:
        missing.append("当前主要症状")
    if not profile.exam_results:
        missing.append("关键检查结果")
    return missing
