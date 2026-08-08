from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Callable

from .config import AppConfig
from .schemas import DoctorEvidence, HospitalCandidate, PatientProfile, Recommendation


def recommend_hospitals_with_assistant_logic(
    profile: PatientProfile,
    config: AppConfig,
    k: int = 6,
    city: str = "上海",
    area: str = "",
    hospital_level: str = "三级优先",
    require_doctor_evidence: bool = False,
) -> dict[str, Any]:
    if not config.deepseek_api_key:
        return {}

    prompt = config.read_prompt("deepseek_assistant_recommend_hospitals.md") or (
        "请根据患者资料推荐医院和科室，输出严格 JSON，不要输出医生或地址。"
    )
    payload = {
        "patient_profile": profile.model_dump(),
        "departments": [item.model_dump() for item in profile.department_candidates],
        "preference_context": {
            "city": city,
            "area": area,
            "hospital_level": hospital_level,
            "k": k,
            "require_doctor_evidence": require_doctor_evidence,
            "doctor_evidence_priority": require_doctor_evidence,
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是专业、谨慎的医疗资源推荐助手。你可以推荐医院和科室，"
                "但不能编造医生、地址、距离、号源或治疗方案。"
            ),
        },
        {"role": "user", "content": f"{prompt}\n\n输入数据：\n{json.dumps(payload, ensure_ascii=False)}"},
    ]
    return _call_deepseek_json(config, messages)


def build_search_plan(
    profile: PatientProfile,
    hospitals: list[HospitalCandidate],
    config: AppConfig,
    limit: int = 8,
) -> dict[str, Any]:
    if not config.deepseek_api_key:
        return {}

    prompt = config.read_prompt("deepseek_search_plan.md") or "请生成医疗资源搜索计划，输出 JSON。"
    payload = {
        "patient_profile": profile.model_dump(),
        "candidate_hospitals": [hospital.model_dump() for hospital in hospitals[:limit]],
        "departments": [item.model_dump() for item in profile.department_candidates],
    }
    messages = [
        {"role": "system", "content": "你是严谨的医疗资源搜索规划智能体。"},
        {"role": "user", "content": f"{prompt}\n\n输入数据：\n{json.dumps(payload, ensure_ascii=False)}"},
    ]
    return _call_deepseek_json(config, messages)


def rerank_with_deepseek(
    profile: PatientProfile,
    hospitals: list[HospitalCandidate],
    doctor_evidence: list[DoctorEvidence],
    heuristic: list[Recommendation],
    search_plan: dict[str, Any],
    config: AppConfig,
    k: int,
) -> list[Recommendation]:
    if not config.deepseek_api_key:
        return []

    prompt = config.read_prompt("rank_hospitals.md") or "请重排医疗资源推荐，输出严格 JSON。"
    payload = {
        "patient_profile": profile.model_dump(),
        "candidate_hospitals": [hospital.model_dump() for hospital in hospitals[:24]],
        "doctor_evidence": [doctor.model_dump() for doctor in doctor_evidence],
        "search_plan": search_plan,
        "heuristic_top": [rec.model_dump() for rec in heuristic],
        "k": k,
    }
    messages = [
        {"role": "system", "content": _ranking_system_prompt()},
        {"role": "user", "content": f"{prompt}\n\n输入数据：\n{json.dumps(payload, ensure_ascii=False)}"},
    ]
    data = _call_deepseek_json(config, messages)
    rows = data.get("recommendations", []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        return []

    hospital_map = {hospital.name: hospital for hospital in hospitals}
    base_map = {rec.hospital: rec for rec in heuristic}
    doctor_urls = {doctor.source_url for doctor in doctor_evidence if doctor.source_url}
    doctor_names = {(doctor.hospital, doctor.name) for doctor in doctor_evidence if doctor.name}

    recommendations: list[Recommendation] = []
    for index, row in enumerate(rows[:k], start=1):
        if not isinstance(row, dict):
            continue
        hospital_name = row.get("hospital") or row.get("hospital_name") or ""
        if hospital_name not in hospital_map:
            continue
        hospital = hospital_map[hospital_name]
        base = base_map.get(hospital_name)
        department = row.get("department") or (base.department if base else "")
        evidence_urls = _as_list(row.get("evidence_urls"))
        doctor = row.get("doctor") or "待人工确认"
        title = row.get("title", "")

        if (
            doctor != "待人工确认"
            and doctor_urls
            and not doctor_urls.intersection(evidence_urls)
            and (hospital_name, doctor) not in doctor_names
        ):
            doctor = "待人工确认"
            title = ""

        reasons = _as_list(row.get("reasons")) or (base.reasons if base else [])
        if search_plan and not doctor_evidence:
            reasons.append("推理模型已生成医生搜索规划；当前未获得医生候选。")

        rec = Recommendation(
            rank=index,
            hospital=hospital_name,
            department=department,
            doctor=doctor,
            title=title,
            score=float(row.get("score", base.score if base else 70)),
            address=hospital.address,
            reasons=list(dict.fromkeys(reasons)),
            evidence_urls=evidence_urls,
            map_url=hospital.map_url,
            caveats=_as_list(row.get("caveats")) or ["推荐仅供就医资源选择参考，不能替代医生诊断。"],
        )
        recommendations.append(rec)

    return recommendations


def extract_doctor_evidence_from_search(
    profile: PatientProfile,
    hospitals: list[HospitalCandidate],
    search_results: list[dict[str, Any]],
    config: AppConfig,
    log_callback: Callable[[str], None] | None = None,
) -> list[DoctorEvidence]:
    if not config.deepseek_api_key or not search_results:
        return []

    _emit(log_callback, f"推理模型正在从 {len(search_results)} 条搜索/网页证据中抽取医生信息。")
    prompt = config.read_prompt("extract_doctor_evidence.md") or "请从搜索结果中抽取医生证据，输出 JSON。"
    payload = {
        "patient_profile": profile.model_dump(),
        "candidate_hospitals": [hospital.model_dump() for hospital in hospitals],
        "search_results": search_results,
    }
    messages = [
        {"role": "system", "content": "你是严谨的医疗网页证据抽取助手。"},
        {"role": "user", "content": f"{prompt}\n\n输入数据：\n{json.dumps(payload, ensure_ascii=False)}"},
    ]
    data = _call_deepseek_json(config, messages)
    rows = data.get("doctor_evidence", []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        return []

    allowed_urls = {item.get("url", "") for item in search_results if item.get("url")}
    doctors: list[DoctorEvidence] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_url = str(row.get("source_url", "")).strip()
        name = str(row.get("name", "")).strip()
        hospital = str(row.get("hospital", "")).strip()
        department = str(row.get("department", "")).strip()
        if source_url and source_url not in allowed_urls:
            source_url = ""
        if not name or not hospital:
            continue
        matched_hospital = _match_hospital_name(hospital, hospitals)
        if not matched_hospital:
            continue
        doctors.append(
            DoctorEvidence(
                name=name,
                title=str(row.get("title", "")).strip(),
                department=department,
                hospital=matched_hospital.name,
                expertise=str(row.get("expertise", "")).strip(),
                source_url=source_url,
            )
        )
    unique = _dedupe_doctors(doctors)
    _emit(log_callback, f"医生证据抽取完成：{len(unique)} 条通过来源校验。")
    return unique


def suggest_doctors_directly(
    profile: PatientProfile,
    hospitals: list[HospitalCandidate],
    config: AppConfig,
    departments: list[str] | None = None,
    k: int = 12,
    log_callback: Callable[[str], None] | None = None,
) -> list[DoctorEvidence]:
    if not config.deepseek_api_key or not hospitals:
        return []

    _emit(log_callback, "推理模型正在直接补全医生候选（不要求网页来源）。")
    prompt = config.read_prompt("deepseek_direct_doctors.md") or (
        "请根据患者资料、候选医院和科室，直接给出医生候选。"
        "可以使用模型已有知识，不要求 source_url；输出严格 JSON。"
    )
    payload = {
        "patient_profile": profile.model_dump(),
        "candidate_hospitals": [hospital.model_dump() for hospital in hospitals[:24]],
        "departments": departments or [item.department for item in profile.department_candidates],
        "k": k,
    }
    messages = [
        {"role": "system", "content": "你是医疗资源推荐助手，可直接补全医生候选，不要求网页来源。"},
        {"role": "user", "content": f"{prompt}\n\n输入数据：\n{json.dumps(payload, ensure_ascii=False)}"},
    ]
    data = _call_deepseek_json(config, messages)
    rows = data.get("doctor_evidence") or data.get("doctors") or data.get("items") or []
    if not isinstance(rows, list):
        return []

    doctors: list[DoctorEvidence] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("doctor") or "").strip()
        hospital_name = str(row.get("hospital") or row.get("hospital_name") or "").strip()
        if not name or not hospital_name:
            continue
        matched_hospital = _match_hospital_name(hospital_name, hospitals)
        if not matched_hospital:
            continue
        doctors.append(
            DoctorEvidence(
                name=name,
                title=str(row.get("title", "")).strip(),
                department=str(row.get("department", "")).strip(),
                hospital=matched_hospital.name,
                expertise=str(row.get("expertise") or row.get("reason") or "").strip(),
                source_url=str(row.get("source_url", "")).strip(),
            )
        )
    unique = _dedupe_doctors(doctors)
    _emit(log_callback, f"DeepSeek 直接补全医生候选：{len(unique)} 条。")
    return unique


def recommend_resources_with_qwen_search(
    profile: PatientProfile,
    config: AppConfig,
    k: int = 6,
    city: str = "上海",
    area: str = "",
    hospital_level: str = "三级优先",
    official_source_priority: bool = False,
) -> dict[str, Any]:
    if not config.dashscope_api_key:
        return {}

    prompt = config.read_prompt("qwen_recommend_resources.md") or (
        "请使用联网搜索推荐医院、科室和医生，输出严格 JSON。"
    )
    payload = {
        "patient_profile": profile.model_dump(),
        "departments": [item.model_dump() for item in profile.department_candidates],
        "recommendation_context": {
            "city": city,
            "area": area,
            "hospital_level": hospital_level,
            "k": int(k),
            "official_source_priority": bool(official_source_priority),
            "today": date.today().isoformat(),
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是严谨的医疗资源联网检索智能体。你必须优先核验医院官网/官方渠道，"
                "不得编造医院、医生、科室、来源链接、号源或治疗方案。"
            ),
        },
        {"role": "user", "content": f"{prompt}\n\n输入数据：\n{json.dumps(payload, ensure_ascii=False)}"},
    ]
    return _call_qwen_json_with_search(config, messages)


def chat_with_medical_assistant(
    user_message: str,
    history: list[dict[str, str]],
    config: AppConfig,
    profile: PatientProfile | None = None,
    recommendations: list[Recommendation] | None = None,
    preference_context: dict[str, Any] | None = None,
    action_context: str = "",
    provider: str | None = None,
) -> str:
    provider_key = _normalize_assistant_provider(provider or config.assistant_provider)
    if provider_key == "qwen":
        return _chat_with_qwen_medical_assistant(
            user_message=user_message,
            history=history,
            config=config,
            profile=profile,
            recommendations=recommendations,
            preference_context=preference_context,
            action_context=action_context,
        )
    return _chat_with_deepseek_medical_assistant(
        user_message=user_message,
        history=history,
        config=config,
        profile=profile,
        recommendations=recommendations,
        preference_context=preference_context,
        action_context=action_context,
    )


def _chat_with_deepseek_medical_assistant(
    user_message: str,
    history: list[dict[str, str]],
    config: AppConfig,
    profile: PatientProfile | None = None,
    recommendations: list[Recommendation] | None = None,
    preference_context: dict[str, Any] | None = None,
    action_context: str = "",
) -> str:
    if not config.deepseek_api_key:
        return "DeepSeek API Key 未配置，暂时无法使用 AI 医疗助手。"

    prompt = config.read_prompt("deepseek_medical_assistant.md") or _assistant_system_prompt()
    messages = _build_assistant_messages(
        prompt=prompt,
        user_message=user_message,
        history=history,
        profile=profile,
        recommendations=recommendations,
        preference_context=preference_context,
        action_context=action_context,
        context_instruction="当前系统上下文如下，请据此回答，不要编造上下文外事实：",
    )

    from openai import OpenAI

    client = OpenAI(api_key=config.deepseek_api_key, base_url=config.deepseek_base_url)
    response = client.chat.completions.create(
        model=config.deepseek_model,
        messages=messages,
        temperature=0.3,
    )
    content = response.choices[0].message.content or ""
    return content.strip() or "我暂时没有生成有效回复，请补充一下你的问题。"


def _chat_with_qwen_medical_assistant(
    user_message: str,
    history: list[dict[str, str]],
    config: AppConfig,
    profile: PatientProfile | None = None,
    recommendations: list[Recommendation] | None = None,
    preference_context: dict[str, Any] | None = None,
    action_context: str = "",
) -> str:
    if not config.dashscope_api_key:
        return "DASHSCOPE_API_KEY 未配置，暂时无法使用 Qwen 联网医疗助手。"

    prompt = config.read_prompt("qwen_medical_assistant.md") or _qwen_assistant_system_prompt()
    messages = _build_assistant_messages(
        prompt=prompt,
        user_message=user_message,
        history=history,
        profile=profile,
        recommendations=recommendations,
        preference_context=preference_context,
        action_context=action_context,
        context_instruction=(
            "当前系统上下文如下。患者资料、偏好和已有推荐以此为准；"
            "如用户询问医院、科室、医生、出诊或实时公开信息，可以使用联网搜索补充，并标注来源链接："
        ),
    )

    try:
        return _call_qwen_responses_with_search(config, messages)
    except Exception:
        return _call_qwen_chat_with_search(config, messages)


def _build_assistant_messages(
    prompt: str,
    user_message: str,
    history: list[dict[str, str]],
    profile: PatientProfile | None = None,
    recommendations: list[Recommendation] | None = None,
    preference_context: dict[str, Any] | None = None,
    action_context: str = "",
    context_instruction: str = "当前系统上下文如下：",
) -> list[dict[str, str]]:
    context = {
        "patient_profile": profile.model_dump() if profile else {},
        "recommendations": [rec.model_dump() for rec in (recommendations or [])[:10]],
        "preference_context": preference_context or {},
        "system_action": action_context,
    }
    messages: list[dict[str, str]] = [
        {"role": "system", "content": prompt},
        {
            "role": "system",
            "content": f"{context_instruction}\n{json.dumps(context, ensure_ascii=False)}",
        },
    ]
    for item in history[-12:]:
        role = item.get("role", "")
        content = item.get("content", "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _call_qwen_responses_with_search(config: AppConfig, messages: list[dict[str, str]]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.qwen_base_url)
    response = client.responses.create(
        model=config.qwen_assistant_model,
        input=_messages_to_responses_input(messages),
        tools=[
            {"type": "web_search"},
            {"type": "web_extractor"},
        ],
        extra_body={"enable_thinking": True},
    )
    content = _extract_responses_text(response)
    return content.strip() or "我暂时没有生成有效回复，请补充一下您的问题。"


def _call_qwen_chat_with_search(config: AppConfig, messages: list[dict[str, str]]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.qwen_base_url)
    response = client.chat.completions.create(
        model=config.qwen_assistant_fallback_model,
        messages=messages,
        temperature=0.3,
        extra_body={
            "enable_search": True,
            "search_options": {
                "forced_search": True,
                "search_strategy": "max",
            },
        },
    )
    content = response.choices[0].message.content or ""
    return content.strip() or "我暂时没有生成有效回复，请补充一下您的问题。"


def _call_qwen_json_with_search(config: AppConfig, messages: list[dict[str, str]]) -> dict[str, Any]:
    try:
        raw = _call_qwen_responses_json_text(config, messages)
    except Exception:
        raw = _call_qwen_chat_json_text(config, messages)
    data = _loads_json_object(raw or "{}")
    if isinstance(data, dict):
        return data
    return {"recommendations": data}


def _call_qwen_responses_json_text(config: AppConfig, messages: list[dict[str, str]]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.qwen_base_url)
    response = client.responses.create(
        model=config.qwen_assistant_model,
        input=_messages_to_responses_input(messages),
        tools=[
            {"type": "web_search"},
            {"type": "web_extractor"},
        ],
        extra_body={"enable_thinking": True},
        temperature=0.2,
    )
    return _extract_responses_text(response)


def _call_qwen_chat_json_text(config: AppConfig, messages: list[dict[str, str]]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.qwen_base_url)
    try:
        response = client.chat.completions.create(
            model=config.qwen_assistant_fallback_model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
            extra_body={
                "enable_search": True,
                "search_options": {
                    "forced_search": True,
                    "search_strategy": "max",
                },
            },
        )
    except Exception:
        response = client.chat.completions.create(
            model=config.qwen_assistant_fallback_model,
            messages=messages,
            temperature=0.2,
            extra_body={
                "enable_search": True,
                "search_options": {
                    "forced_search": True,
                    "search_strategy": "max",
                },
            },
        )
    return response.choices[0].message.content or "{}"


def _messages_to_responses_input(messages: list[dict[str, str]]) -> str:
    role_names = {
        "system": "系统",
        "user": "用户",
        "assistant": "助手",
    }
    lines: list[str] = []
    for message in messages:
        role = role_names.get(message.get("role", ""), message.get("role", "消息"))
        content = str(message.get("content", "")).strip()
        if content:
            lines.append(f"{role}：\n{content}")
    return "\n\n".join(lines)


def _extract_responses_text(response: Any) -> str:
    output_text = getattr(response, "output_text", "")
    if output_text:
        return str(output_text)
    data = response.model_dump() if hasattr(response, "model_dump") else response
    if not isinstance(data, dict):
        return ""
    chunks: list[str] = []
    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("content")
            if text:
                chunks.append(str(text))
    return "\n".join(chunks)


def _call_deepseek_json(config: AppConfig, messages: list[dict[str, str]]) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=config.deepseek_api_key, base_url=config.deepseek_base_url)
    try:
        response = client.chat.completions.create(
            model=config.deepseek_model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except Exception:
        response = client.chat.completions.create(
            model=config.deepseek_model,
            messages=messages,
            temperature=0.2,
        )
    raw = response.choices[0].message.content or "{}"
    data = _loads_json_object(raw)
    if isinstance(data, dict):
        return data
    return {"items": data}


def _ranking_system_prompt() -> str:
    return (
        "你是医疗资源推荐智能体。你可以根据患者病情、医院候选、搜索规划和医生证据进行排序，"
        "医生可以来自 doctor_evidence，即使没有 source_url 也可以输出；"
        "没有医生候选时 doctor 写“待人工确认”；不输出诊断或治疗方案。"
    )


def _assistant_system_prompt() -> str:
    return (
        "你是一个中文医疗助手，可以解释患者问题、检查结果和就医资源推荐。"
        "你必须谨慎表达，不替代医生诊断，不编造医院、医生、地址、距离或来源。"
        "用户要求重新推荐或近一点医院时，基于系统提供的最新推荐结果回答；"
        "没有位置时先询问所在区县、街道、地址或地标。"
    )


def _qwen_assistant_system_prompt() -> str:
    return (
        "你是一个可联网搜索的中文医疗资源助手。你可以根据患者资料解释就医方向，"
        "也可以使用联网搜索核验医院、科室和医生公开资料。涉及医生、出诊、号源、地址、"
        "医院专科等实时信息时要标注来源链接；不能替代医生诊断或治疗。"
    )


def _normalize_assistant_provider(value: str) -> str:
    text = (value or "").strip().lower()
    if "deepseek" in text or "deep" in text:
        return "deepseek"
    if "qwen" in text or "千问" in text or "通义" in text:
        return "qwen"
    return "qwen"


def _loads_json_object(raw: str) -> dict[str, Any] | list[Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(1))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe_doctors(doctors: list[DoctorEvidence]) -> list[DoctorEvidence]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[DoctorEvidence] = []
    for doctor in doctors:
        key = (doctor.hospital, doctor.department, doctor.name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(doctor)
    return unique


def _match_hospital_name(name: str, hospitals: list[HospitalCandidate]) -> HospitalCandidate | None:
    target = _normalize_name(name)
    if not target:
        return None
    for hospital in hospitals:
        current = _normalize_name(hospital.name)
        if target == current or target in current or current in target:
            return hospital
    return None


def _normalize_name(value: str) -> str:
    value = re.sub(r"[（(].*?[）)]", "", value)
    value = re.sub(r"[\s·・,，。:：-]", "", value)
    return value


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    if callback:
        callback(message)
