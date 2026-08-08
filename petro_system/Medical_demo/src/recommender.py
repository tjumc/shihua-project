from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.parse import urlparse

from .config import AppConfig
from .deepseek_agent import (
    build_search_plan,
    recommend_hospitals_with_assistant_logic,
    recommend_resources_with_qwen_search,
    rerank_with_deepseek,
    suggest_doctors_directly,
)
from .schemas import DepartmentCandidate, DoctorEvidence, HospitalCandidate, PatientProfile, Recommendation
from .search.amap import AmapHospitalSearch, fallback_hospitals
from .search.web_search import THIRD_PARTY_DOCTOR_PLATFORM_TERMS, collect_doctor_evidence


def recommend_resources(
    profile: PatientProfile,
    config: AppConfig,
    k: int = 6,
    city: str = "上海",
    area: str = "",
    hospital_level: str = "三级优先",
    require_doctor_evidence: bool = False,
    log_callback: Callable[[str], None] | None = None,
    provider: str | None = None,
) -> tuple[list[Recommendation], list[HospitalCandidate], str]:
    profile.patient_need.preferred_city = city
    profile.patient_need.preferred_area = area
    profile.patient_need.hospital_level = hospital_level
    profile.patient_need.k = k
    profile.patient_need.require_doctor_evidence = require_doctor_evidence

    log: list[str] = []

    def emit(message: str) -> None:
        log.append(message)
        if log_callback:
            log_callback(message)

    provider_key = _normalize_recommendation_provider(provider or config.recommendation_provider or config.assistant_provider)
    official_source_priority = bool(require_doctor_evidence)
    emit(
        "固定推荐条件："
        f"推荐数量不少于 {int(k)}，医院等级={hospital_level or '不限'}，"
        f"有确切来源（医院官网）优先={'是' if official_source_priority else '否'}，"
        f"推荐引擎={provider_key.upper()}。"
    )
    searcher = AmapHospitalSearch(config)
    target_count = _max_recommendation_count(k)
    assistant_ranked: list[Recommendation] = []
    assistant_hospitals: list[HospitalCandidate] = []

    if provider_key == "qwen":
        if config.dashscope_api_key:
            try:
                emit("开始推荐：Qwen 联网助手正在从病历资料直接搜索医院-科室-医生。")
                qwen_ranked, qwen_hospitals = _recommend_with_qwen_search(
                    profile=profile,
                    config=config,
                    searcher=searcher,
                    k=k,
                    city=city,
                    area=area,
                    hospital_level=hospital_level,
                    official_source_priority=official_source_priority,
                    log_callback=emit,
                )
                assistant_ranked = _merge_recommendations(
                    assistant_ranked,
                    qwen_ranked,
                    k=k,
                    require_doctor_evidence=official_source_priority,
                )
                assistant_hospitals = _merge_hospitals(assistant_hospitals, qwen_hospitals)
                if len(assistant_ranked) >= k:
                    emit(f"Qwen 联网推荐完成：已生成 {len(assistant_ranked)} 个推荐结果。")
                    return assistant_ranked, assistant_hospitals, "\n".join(log)
                if assistant_ranked:
                    emit(f"Qwen 联网推荐生成 {len(assistant_ranked)} 个结果，少于目标下限，尝试 DeepSeek 兜底补充。")
                else:
                    emit("Qwen 联网推荐未产出可用结果，尝试 DeepSeek 兜底。")
            except Exception as exc:
                emit(f"Qwen 联网推荐失败，尝试 DeepSeek 兜底：{exc}")
        else:
            emit("DASHSCOPE_API_KEY 未配置，无法使用 Qwen 联网推荐，尝试 DeepSeek 兜底。")

    use_deepseek_recommender = bool(config.deepseek_api_key)
    if use_deepseek_recommender:
        try:
            emit("开始推荐：DeepSeek 正在根据患者资料生成医院和科室候选。")
            deepseek_ranked, deepseek_hospitals = _recommend_with_assistant_logic(
                profile=profile,
                config=config,
                searcher=searcher,
                k=k,
                city=city,
                area=area,
                hospital_level=hospital_level,
                require_doctor_evidence=require_doctor_evidence,
                log_callback=emit,
            )
            assistant_ranked = _merge_recommendations(
                assistant_ranked,
                deepseek_ranked,
                k=k,
                require_doctor_evidence=official_source_priority,
            )
            assistant_hospitals = _merge_hospitals(assistant_hospitals, deepseek_hospitals)
            if len(assistant_ranked) >= k:
                emit(f"DeepSeek 兜底推荐链路完成：已生成 {len(assistant_ranked)} 个推荐结果。")
                return assistant_ranked, assistant_hospitals, "\n".join(log)
            if assistant_ranked:
                emit(f"AI助手推荐链路累计生成 {len(assistant_ranked)} 个结果，少于目标下限，继续召回医院补充。")
            else:
                emit("AI助手推荐链路未产出可核验结果，切换到原候选召回链路。")
        except Exception as exc:
            emit(f"AI助手推荐链路失败，切换到原候选召回链路：{exc}")

    emit(f"开始推荐：读取患者结构化信息，准备召回{city}医院。")
    hospitals = searcher.search(
        departments=profile.department_candidates,
        city=city,
        area=area,
        limit=max(target_count * 4, 16),
    )
    search_plan: dict[str, Any] = {}
    emit(f"高德召回医院候选 {len(hospitals)} 家。")
    hospitals = _filter_hospitals_by_location(hospitals, city, area)
    location_label = f"{city}{area}" if area else city
    emit(f"地点严格筛选（{location_label}）后剩余 {len(hospitals)} 家。")
    hospitals = _filter_hospitals_by_level(hospitals, hospital_level)
    emit(f"医院等级硬筛选后剩余 {len(hospitals)} 家。")
    if not hospitals:
        emit("没有医院满足当前医院等级条件，推荐结束。")
        if assistant_ranked:
            emit("保留 AI助手已生成的可核验推荐结果。")
            return assistant_ranked, assistant_hospitals, "\n".join(log)
        return [], [], "\n".join(log)
    if use_deepseek_recommender:
        try:
            emit("推理模型正在根据病情和医院候选生成医生/科室检索计划。")
            search_plan = build_search_plan(profile, hospitals, config, limit=max(target_count * 2, 8))
            query_count = len(search_plan.get("search_queries", [])) if isinstance(search_plan, dict) else 0
            emit(f"推理模型已生成搜索规划：{query_count} 条医生/科室核验查询。")
        except Exception as exc:
            emit(f"推理模型搜索规划失败，继续使用规则推荐：{exc}")

    doctor_evidence = collect_doctor_evidence(
        hospitals=hospitals,
        departments=profile.department_candidates,
        config=config,
        profile=profile,
        search_plan=search_plan,
        require_doctor=require_doctor_evidence,
        log_callback=log_callback,
    )
    if doctor_evidence:
        emit(f"网页搜索和推理模型抽取到 {len(doctor_evidence)} 条医生证据。")
    elif use_deepseek_recommender and config.deepseek_api_key:
        emit("网页搜索未抽取到医生，改由 DeepSeek 直接补全医生候选。")
        doctor_evidence = suggest_doctors_directly(
            profile=profile,
            hospitals=hospitals,
            config=config,
            departments=[item.department for item in profile.department_candidates],
            k=max(target_count * 2, 12),
            log_callback=log_callback,
        )
    elif search_plan and config.search_api_key:
        emit("已调用网页搜索，但未抽取到医生；当前未启用 DeepSeek 直出兜底。")
    elif search_plan:
        emit("未配置网页搜索或 DeepSeek 密钥，医生字段将保持“待人工确认”。")

    emit("正在进行规则评分：科室匹配、医院等级、区域偏好、医生证据。")
    heuristic = _heuristic_rank(
        profile=profile,
        hospitals=hospitals,
        doctor_evidence=doctor_evidence,
        k=target_count,
        area=area,
        hospital_level=hospital_level,
        require_doctor_evidence=require_doctor_evidence,
    )
    heuristic = _apply_recommendation_constraints(
        heuristic,
        k=k,
        require_doctor_evidence=require_doctor_evidence,
    )
    emit(f"规则排序得到前 {len(heuristic)} 个候选。")

    if use_deepseek_recommender and config.enable_llm_rerank:
        try:
            emit("推理模型正在基于网页证据和规则候选进行最终重排。")
            llm_ranked = rerank_with_deepseek(
                profile=profile,
                hospitals=hospitals,
                doctor_evidence=doctor_evidence,
                heuristic=heuristic,
                search_plan=search_plan,
                config=config,
                k=target_count,
            )
            if llm_ranked:
                llm_ranked = _merge_recommendations(
                    assistant_ranked,
                    llm_ranked,
                    k=k,
                    require_doctor_evidence=require_doctor_evidence,
                )
                emit("已调用推理模型完成推荐重排。")
                return llm_ranked, _merge_hospitals(assistant_hospitals, hospitals), "\n".join(log)
        except Exception as exc:
            emit(f"推理模型推荐重排失败，保留规则排序：{exc}")
    elif config.dashscope_api_key and config.enable_llm_rerank:
        try:
            emit(f"文本模型 {config.text_model} 正在进行推荐重排。")
            llm_ranked = _rerank_with_llm(profile, hospitals, doctor_evidence, heuristic, config, target_count)
            if llm_ranked:
                llm_ranked = _merge_recommendations(
                    assistant_ranked,
                    llm_ranked,
                    k=k,
                    require_doctor_evidence=require_doctor_evidence,
                )
                emit(f"已调用文本模型 {config.text_model} 进行推荐重排。")
                return llm_ranked, _merge_hospitals(assistant_hospitals, hospitals), "\n".join(log)
        except Exception as exc:
            emit(f"文本模型重排失败，保留规则排序：{exc}")
    else:
        emit("未启用文本模型重排，使用规则排序。")

    heuristic = _merge_recommendations(
        assistant_ranked,
        heuristic,
        k=k,
        require_doctor_evidence=require_doctor_evidence,
    )
    return heuristic, _merge_hospitals(assistant_hospitals, hospitals), "\n".join(log)


def _recommend_with_qwen_search(
    profile: PatientProfile,
    config: AppConfig,
    searcher: AmapHospitalSearch,
    k: int,
    city: str,
    area: str,
    hospital_level: str,
    official_source_priority: bool,
    log_callback: Callable[[str], None] | None = None,
) -> tuple[list[Recommendation], list[HospitalCandidate]]:
    data = recommend_resources_with_qwen_search(
        profile=profile,
        config=config,
        k=_max_recommendation_count(k),
        city=city,
        area=area,
        hospital_level=hospital_level,
        official_source_priority=official_source_priority,
    )
    rows = _qwen_recommendation_rows(data)
    if not rows:
        _emit(log_callback, "Qwen 联网助手未返回有效医院-科室-医生候选。")
        return [], []

    hospital_names = [row["hospital"] for row in rows]
    _emit(log_callback, f"Qwen 联网助手给出 {len(hospital_names)} 个医院候选，开始调用高德核验地址和地图。")
    amap_hospitals = searcher.search_by_names(
        names=hospital_names,
        city=city,
        area=area,
        limit=max(len(hospital_names), k + 4, 12),
    )
    amap_hospitals = _filter_hospitals_by_location(amap_hospitals, city, area)
    qwen_hospitals: list[HospitalCandidate] = []
    recommendations: list[Recommendation] = []
    used_keys: set[tuple[str, str]] = set()

    for index, row in enumerate(rows, start=1):
        hospital = _match_hospital_candidate(row["hospital"], amap_hospitals)
        hospital_candidate = hospital or _hospital_from_qwen_row(row, city, area)
        if not _qwen_hospital_matches_level(row, hospital_candidate, hospital_level):
            continue
        key = (_normalize_match_text(hospital_candidate.name), _normalize_department_name(row["department"]))
        if key in used_keys:
            continue
        used_keys.add(key)
        qwen_hospitals.append(hospital_candidate)

        evidence_urls = _dedupe_urls([*row["official_source_urls"], *row["evidence_urls"]])
        official_urls = _dedupe_urls(
            row["official_source_urls"]
            or [url for url in evidence_urls if _looks_like_hospital_official_url(url, hospital_candidate.name)]
        )
        reasons = list(row["reasons"])
        reasons.append("推荐由 Qwen 联网搜索生成，优先核验医院官网/官方渠道。")
        if hospital:
            reasons.append("医院地址和地图链接已通过高德地图 API 核验。")
        if official_urls:
            reasons.append("医生/科室资料包含医院官网或官方渠道来源。")
        elif official_source_priority:
            reasons.append("未检索到医院官网医生来源，排序时低于有官网来源的候选。")

        caveats = row["caveats"] or ["推荐仅供就医资源选择参考，不能替代医生诊断。"]
        if row["doctor"] != "待人工确认" and not official_urls:
            caveats.append("医生姓名未获得医院官网来源时，请以医院官网或挂号平台再次核验。")

        recommendations.append(
            Recommendation(
                rank=index,
                hospital=hospital_candidate.name,
                department=row["department"],
                doctor=row["doctor"],
                title=row["title"],
                score=row["score"],
                address=hospital_candidate.address or row["address"],
                reasons=list(dict.fromkeys(reasons)),
                evidence_urls=evidence_urls,
                official_source_urls=official_urls,
                map_url=hospital_candidate.map_url,
                caveats=list(dict.fromkeys(caveats)),
            )
        )

    recommendations = _apply_recommendation_constraints(
        recommendations,
        k=k,
        require_doctor_evidence=official_source_priority,
    )
    _emit(log_callback, f"Qwen 联网助手清洗后得到 {len(recommendations)} 个推荐结果。")
    return recommendations, _merge_hospitals(qwen_hospitals, amap_hospitals)


def _qwen_recommendation_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    rows = data.get("recommendations") or data.get("items") or data.get("results") or []
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        hospital = str(row.get("hospital") or row.get("hospital_name") or "").strip()
        department = str(row.get("department") or row.get("dept") or "").strip()
        if not hospital or not department:
            continue
        doctor = str(row.get("doctor") or row.get("doctor_name") or "待人工确认").strip() or "待人工确认"
        normalized.append(
            {
                "hospital": hospital,
                "department": department,
                "doctor": doctor,
                "title": str(row.get("title", "")).strip(),
                "score": _score_from_value(row.get("score"), default=max(70, 98 - len(normalized) * 3)),
                "address": str(row.get("address", "")).strip(),
                "hospital_level": str(row.get("hospital_level") or row.get("level") or "").strip(),
                "reasons": _as_list(row.get("reasons") or row.get("reason")),
                "evidence_urls": _dedupe_urls(_as_list(row.get("evidence_urls") or row.get("source_urls") or row.get("urls"))),
                "official_source_urls": _dedupe_urls(_as_list(row.get("official_source_urls") or row.get("official_urls"))),
                "caveats": _as_list(row.get("caveats")),
            }
        )
    return normalized


def _hospital_from_qwen_row(row: dict[str, Any], city: str, area: str) -> HospitalCandidate:
    evidence_urls = _dedupe_urls([*row.get("official_source_urls", []), *row.get("evidence_urls", [])])
    return HospitalCandidate(
        name=row["hospital"],
        address=row.get("address", ""),
        city=city,
        district=area,
        level=row.get("hospital_level", ""),
        source="qwen_search",
        evidence_url=evidence_urls[0] if evidence_urls else "",
        map_url=f"https://www.amap.com/search?query={row['hospital']}",
    )


def _recommend_with_assistant_logic(
    profile: PatientProfile,
    config: AppConfig,
    searcher: AmapHospitalSearch,
    k: int,
    city: str,
    area: str,
    hospital_level: str,
    require_doctor_evidence: bool,
    log_callback: Callable[[str], None] | None = None,
) -> tuple[list[Recommendation], list[HospitalCandidate]]:
    data = recommend_hospitals_with_assistant_logic(
        profile=profile,
        config=config,
        k=k,
        city=city,
        area=area,
        hospital_level=hospital_level,
        require_doctor_evidence=require_doctor_evidence,
    )
    rows = _assistant_recommendation_rows(data)
    if not rows:
        _emit(log_callback, "AI助手未返回有效医院/科室候选。")
        return [], []

    hospital_names = [row["hospital"] for row in rows]
    _emit(log_callback, f"AI助手给出 {len(hospital_names)} 个医院候选，开始调用高德核验地址和地图。")
    amap_hospitals = searcher.search_by_names(
        names=hospital_names,
        city=city,
        area=area,
        limit=max(k + 4, 12),
    )
    _emit(log_callback, f"高德核验通过医院 {len(amap_hospitals)} 家。")
    if not amap_hospitals:
        return [], []
    location_filtered_hospitals = _filter_hospitals_by_location(amap_hospitals, city, area)
    location_label = f"{city}{area}" if area else city
    _emit(log_callback, f"地点严格筛选（{location_label}）后剩余 {len(location_filtered_hospitals)} 家。")
    if not location_filtered_hospitals:
        return [], amap_hospitals
    level_filtered_hospitals = _filter_hospitals_by_level(location_filtered_hospitals, hospital_level)
    _emit(log_callback, f"医院等级硬筛选后剩余 {len(level_filtered_hospitals)} 家。")
    if not level_filtered_hospitals:
        return [], amap_hospitals

    matched_items: list[tuple[dict[str, Any], HospitalCandidate]] = []
    used_hospitals: set[str] = set()
    for row in rows:
        hospital = _match_hospital_candidate(row["hospital"], level_filtered_hospitals)
        if not hospital or hospital.name in used_hospitals:
            continue
        used_hospitals.add(hospital.name)
        matched_items.append((row, hospital))
    if not matched_items:
        _emit(log_callback, "AI助手候选未能与高德医院结果匹配。")
        return [], level_filtered_hospitals

    departments = _departments_from_assistant_rows([row for row, _ in matched_items])
    search_plan = _doctor_search_plan_from_assistant_rows(matched_items, profile)
    doctor_evidence = collect_doctor_evidence(
        hospitals=[hospital for _, hospital in matched_items],
        departments=departments,
        config=config,
        profile=profile,
        search_plan=search_plan,
        require_doctor=require_doctor_evidence,
        log_callback=log_callback,
    )
    if doctor_evidence:
        _emit(log_callback, f"网页搜索并抽取到 {len(doctor_evidence)} 条医生证据。")
    else:
        _emit(log_callback, "网页搜索未抽取到医生，改由 DeepSeek 直接补全医生候选。")
        doctor_evidence = suggest_doctors_directly(
            profile=profile,
            hospitals=[hospital for _, hospital in matched_items],
            config=config,
            departments=[row["department"] for row, _ in matched_items],
            k=max(k * 2, 12),
            log_callback=log_callback,
        )

    recommendations: list[Recommendation] = []
    for row, hospital in matched_items:
        department = row["department"]
        doctor, title, _, doctor_url = _match_doctor(doctor_evidence, hospital.name, department)
        evidence_urls = []
        if hospital.evidence_url:
            evidence_urls.append(hospital.evidence_url)
        if doctor_url:
            evidence_urls.append(doctor_url)
        reasons = _as_list(row.get("reasons"))
        reasons.append("医院地址、区县和地图链接已通过高德地图 API 核验。")
        if doctor == "待人工确认":
            reasons.append("未找到可核验医生公开来源，建议人工确认专家门诊。")
        elif not doctor_url:
            reasons.append("医生由 DeepSeek 直接补全，未强制网页来源；挂号前请再次确认。")
        caveats = _as_list(row.get("caveats")) or ["推荐仅供就医资源选择参考，不能替代医生诊断。"]
        if require_doctor_evidence and doctor == "待人工确认":
            caveats.append("已开启医院官网来源优先；当前该医院暂未获得官网医生来源，建议人工确认专家门诊。")
        if doctor != "待人工确认" and not doctor_url:
            caveats.append("医生姓名为 AI 直出候选，可能存在时效或出诊变动，请以医院/挂号平台为准。")
        recommendations.append(
            Recommendation(
                rank=0,
                hospital=hospital.name,
                department=department,
                doctor=doctor,
                title=title,
                score=_score_from_value(row.get("score"), default=max(70, 96 - (len(recommendations) + 1) * 3)),
                address=hospital.address,
                reasons=list(dict.fromkeys(reasons)),
                evidence_urls=list(dict.fromkeys(evidence_urls)),
                map_url=hospital.map_url,
                caveats=list(dict.fromkeys(caveats)),
            )
        )
    recommendations = _apply_recommendation_constraints(
        recommendations,
        k=k,
        require_doctor_evidence=require_doctor_evidence,
    )
    if len(recommendations) < k:
        _emit(log_callback, f"按固定条件仅筛出 {len(recommendations)} 个推荐。")
    return recommendations, level_filtered_hospitals


def _assistant_recommendation_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("recommendations", []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        hospital = str(row.get("hospital") or row.get("hospital_name") or "").strip()
        department = str(row.get("department") or row.get("dept") or "").strip()
        if not hospital or not department:
            continue
        normalized.append(
            {
                "hospital": hospital,
                "department": department,
                "score": row.get("score", 0),
                "reasons": _as_list(row.get("reasons")),
                "caveats": _as_list(row.get("caveats")),
            }
        )
    return normalized


def _departments_from_assistant_rows(rows: list[dict[str, Any]]) -> list[DepartmentCandidate]:
    departments: list[DepartmentCandidate] = []
    seen: set[str] = set()
    for row in rows:
        department = str(row.get("department", "")).strip()
        if not department or department in seen:
            continue
        seen.add(department)
        reason = "AI助手根据患者资料推荐的重点就诊科室"
        reasons = _as_list(row.get("reasons"))
        if reasons:
            reason = reasons[0]
        departments.append(DepartmentCandidate(department=department, reason=reason, confidence=0.82))
    return departments or profile_safe_departments(rows)


def profile_safe_departments(rows: list[dict[str, Any]]) -> list[DepartmentCandidate]:
    for row in rows:
        department = str(row.get("department", "")).strip()
        if department:
            return [DepartmentCandidate(department=department, reason="AI助手推荐科室", confidence=0.75)]
    return [DepartmentCandidate(department="专家门诊", reason="未形成明确科室，建议人工确认", confidence=0.5)]


def _doctor_search_plan_from_assistant_rows(
    matched_items: list[tuple[dict[str, Any], HospitalCandidate]],
    profile: PatientProfile,
) -> dict[str, Any]:
    symptom_terms = _patient_search_terms(profile)
    city = (profile.patient_need.preferred_city or profile.patient_basic.city or "").strip()
    area = (profile.patient_need.preferred_area or "").strip()
    location_terms = " ".join(part for part in [city, area] if part).strip()
    search_queries = []
    for row, hospital in matched_items:
        department = row["department"]
        search_queries.extend(
            [
                {
                    "hospital": hospital.name,
                    "department": department,
                    "query": f"{location_terms} {hospital.name} {department} 医生 专家 擅长 出诊 {symptom_terms}".strip(),
                    "purpose": "通过全网公开资料核验医生姓名和擅长方向",
                },
                {
                    "hospital": hospital.name,
                    "department": department,
                    "query": f"{location_terms} {hospital.name} {department} 医生主页 医生团队 专家介绍 挂号 {symptom_terms}".strip(),
                    "purpose": "检索医院页面和第三方医疗平台上的医生公开信息",
                },
                {
                    "hospital": hospital.name,
                    "department": department,
                    "query": f"{location_terms} {hospital.name} {department} 专家门诊 主任医师 副主任医师 {symptom_terms}".strip(),
                    "purpose": "核验专家门诊公开信息",
                },
                {
                    "hospital": hospital.name,
                    "department": department,
                    "query": f"{location_terms} {hospital.name} {department} {THIRD_PARTY_DOCTOR_PLATFORM_TERMS} 专家 {symptom_terms}".strip(),
                    "purpose": "补充检索第三方医生查询平台的医生主页和擅长方向",
                },
            ]
        )
    return {
        "department_focus": [
            {"department": row["department"], "reason": "AI助手推荐科室"}
            for row, _ in matched_items
        ],
        "search_queries": search_queries,
        "ranking_strategy": [
            "医院和科室来自AI助手推荐，并经高德地图核验医院地点。",
            "有医院官网/官方渠道来源的推荐优先排序；医生可来自网页抽取或 DeepSeek 直接补全。",
            "没有医生候选时 doctor 保持“待人工确认”。",
        ],
    }


def _patient_search_terms(profile: PatientProfile) -> str:
    terms = []
    terms.extend(profile.current_symptoms[:3])
    terms.extend(profile.suspected_diagnoses[:2])
    if profile.chief_complaint:
        terms.append(profile.chief_complaint[:30])
    return " ".join(term for term in terms if term)[:80]


def _match_hospital_candidate(name: str, hospitals: list[HospitalCandidate]) -> HospitalCandidate | None:
    for hospital in hospitals:
        if _same_hospital(hospital.name, name):
            return hospital
    return None


def _score_from_value(value: Any, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        if match:
            return float(match.group(0))
    return float(default)


def _max_recommendation_count(k: int) -> int:
    return max(int(k), int(k) + 4)


def _merge_recommendations(
    primary: list[Recommendation],
    secondary: list[Recommendation],
    k: int,
    require_doctor_evidence: bool,
) -> list[Recommendation]:
    seen: set[tuple[str, str]] = set()
    rows: list[Recommendation] = []
    for rec in [*primary, *secondary]:
        key = (_normalize_match_text(rec.hospital), _normalize_department_name(rec.department))
        if key in seen:
            continue
        seen.add(key)
        rows.append(rec)
    return _apply_recommendation_constraints(
        rows,
        k=k,
        require_doctor_evidence=require_doctor_evidence,
    )


def _merge_hospitals(
    primary: list[HospitalCandidate],
    secondary: list[HospitalCandidate],
) -> list[HospitalCandidate]:
    seen: set[str] = set()
    rows: list[HospitalCandidate] = []
    for hospital in [*primary, *secondary]:
        key = _normalize_match_text(hospital.name)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(hospital)
    return rows


def _filter_hospitals_by_location(
    hospitals: list[HospitalCandidate],
    city: str,
    area: str = "",
) -> list[HospitalCandidate]:
    return [hospital for hospital in hospitals if _hospital_matches_location(hospital, city, area)]


def _hospital_matches_location(
    hospital: HospitalCandidate,
    city: str,
    area: str = "",
) -> bool:
    if city and hospital.city and hospital.city != city:
        return False
    if city and hospital.source == "fallback" and hospital.address and city not in hospital.address:
        return False
    if area and area not in hospital.address and area not in hospital.district:
        return False
    return True


def _filter_hospitals_by_level(
    hospitals: list[HospitalCandidate],
    hospital_level: str,
) -> list[HospitalCandidate]:
    if not hospital_level or hospital_level == "不限":
        return hospitals
    return [hospital for hospital in hospitals if _hospital_matches_level(hospital, hospital_level)]


def _hospital_matches_level(hospital: HospitalCandidate, hospital_level: str) -> bool:
    text = f"{hospital.name} {hospital.level} {hospital.address} {hospital.district}"
    known_level = _known_hospital_level(hospital)
    if known_level:
        text = f"{text} {known_level}"

    if "三级甲等" in hospital_level:
        return any(keyword in text for keyword in ["三级甲等", "三甲"])
    if "三级" in hospital_level:
        return any(keyword in text for keyword in ["三级甲等", "三甲", "三级", "三级优先"])
    if "专科" in hospital_level:
        specialty_keywords = [
            "专科",
            "胸科",
            "肿瘤",
            "儿童",
            "妇产",
            "口腔",
            "眼耳鼻喉",
            "精神",
            "皮肤",
            "传染",
            "肺科",
            "骨科",
            "脑科",
            "心血管病",
        ]
        return any(keyword in text for keyword in specialty_keywords)
    return True


def _qwen_hospital_matches_level(
    row: dict[str, Any],
    hospital: HospitalCandidate,
    hospital_level: str,
) -> bool:
    if not hospital_level or hospital_level == "不限":
        return True
    text = " ".join(
        [
            hospital.name,
            hospital.level,
            _known_hospital_level(hospital),
            str(row.get("hospital_level", "")),
            " ".join(row.get("reasons", []) or []),
        ]
    )
    if "三级甲等" in hospital_level:
        return any(keyword in text for keyword in ["三级甲等", "三甲"])
    if "三级" in hospital_level:
        return any(keyword in text for keyword in ["三级甲等", "三甲", "三级"])
    if "专科" in hospital_level:
        return _hospital_matches_level(hospital, hospital_level) or any(
            keyword in text
            for keyword in ["专科", "胸科", "肿瘤", "儿童", "妇产", "口腔", "精神", "皮肤", "肺科"]
        )
    return True


def _known_hospital_level(hospital: HospitalCandidate) -> str:
    for known in fallback_hospitals(city=hospital.city or "上海"):
        if _same_hospital(known.name, hospital.name):
            return known.level
    return ""


def _apply_recommendation_constraints(
    recommendations: list[Recommendation],
    k: int,
    require_doctor_evidence: bool,
) -> list[Recommendation]:
    rows = list(recommendations)
    if require_doctor_evidence:
        rows.sort(
            key=lambda rec: (
                1 if _has_official_source(rec) else 0,
                1 if _has_doctor_source(rec) else 0,
                float(rec.score or 0),
            ),
            reverse=True,
        )
    rows = rows[: _max_recommendation_count(k)]
    for index, rec in enumerate(rows, start=1):
        rec.rank = index
    return rows


def _has_doctor_source(rec: Recommendation) -> bool:
    return rec.doctor != "待人工确认" and bool(rec.evidence_urls or rec.official_source_urls)


def _has_official_source(rec: Recommendation) -> bool:
    if rec.official_source_urls:
        return True
    return any(_looks_like_hospital_official_url(url, rec.hospital) for url in rec.evidence_urls)


def _heuristic_rank(
    profile: PatientProfile,
    hospitals: list[HospitalCandidate],
    doctor_evidence: list[DoctorEvidence],
    k: int,
    area: str,
    hospital_level: str,
    require_doctor_evidence: bool,
) -> list[Recommendation]:
    rows: list[tuple[float, Recommendation]] = []
    for hospital in hospitals:
        department, specialty_score, department_reason = _best_department_match(profile, hospital)
        level_score = _level_score(hospital, hospital_level)
        doctor, title, doctor_score, doctor_url = _match_doctor(doctor_evidence, hospital.name, department)
        area_score = 1.0 if area and (area in hospital.address or area in hospital.district) else 0.55
        if not area:
            area_score = 0.7
        source_score = 0.9 if hospital.source == "amap" else 0.65
        urgency_score = 0.9 if profile.urgency_level == "urgent" and "急诊医学科" in hospital.strengths else 0.65
        if profile.urgency_level != "urgent":
            urgency_score = 0.75

        score = (
            0.30 * specialty_score
            + 0.20 * level_score
            + 0.15 * doctor_score
            + 0.15 * area_score
            + 0.10 * urgency_score
            + 0.10 * source_score
        )

        reasons = [
            department_reason,
            f"医院等级匹配：{hospital.level or '待核验'}",
        ]
        if area:
            reasons.append("地址或行政区与偏好区域匹配" if area_score >= 1 else "不在偏好区域内，但专科匹配度较高")
        if profile.urgency_level == "urgent":
            reasons.append("资料存在风险线索，建议优先确认急诊或快速门诊资源")
        if doctor == "待人工确认":
            reasons.append("未找到已核验医生来源，建议人工确认专家门诊")
        elif not doctor_url:
            reasons.append("医生由 DeepSeek 直接补全，未强制网页来源；挂号前请再次确认")

        evidence_urls = []
        if hospital.evidence_url:
            evidence_urls.append(hospital.evidence_url)
        if doctor_url:
            evidence_urls.append(doctor_url)

        caveats = ["推荐仅供就医资源选择参考，不能替代医生诊断。"]
        if require_doctor_evidence and doctor == "待人工确认":
            caveats.append("已开启医院官网来源优先；当前该医院暂未获得官网医生来源，建议人工确认专家门诊。")
        if doctor != "待人工确认" and not doctor_url:
            caveats.append("医生姓名为 AI 直出候选，可能存在时效或出诊变动，请以医院/挂号平台为准。")

        rec = Recommendation(
            rank=0,
            hospital=hospital.name,
            department=department,
            doctor=doctor,
            title=title,
            score=round(score * 100, 1),
            address=hospital.address,
            reasons=reasons,
            evidence_urls=evidence_urls,
            map_url=hospital.map_url,
            caveats=caveats,
        )
        rows.append((score, rec))

    rows.sort(key=lambda item: item[0], reverse=True)
    recommendations = [row[1] for row in rows[:k]]
    for index, rec in enumerate(recommendations, start=1):
        rec.rank = index
    return recommendations


def _best_department_match(profile: PatientProfile, hospital: HospitalCandidate) -> tuple[str, float, str]:
    if not profile.department_candidates:
        return "全科医学科", 0.55, "病历信息暂未形成明确专科线索"

    for candidate in profile.department_candidates:
        if candidate.department in hospital.strengths:
            return (
                candidate.department,
                max(0.85, candidate.confidence),
                f"患者线索与医院优势科室 {candidate.department} 匹配：{candidate.reason}",
            )

    first = profile.department_candidates[0]
    if not hospital.strengths:
        return (
            first.department,
            max(0.62, first.confidence - 0.05),
            f"根据患者资料优先推荐 {first.department}：{first.reason}",
        )
    return (
        first.department,
        max(0.52, first.confidence - 0.18),
        f"根据患者资料优先考虑 {first.department}，医院优势科室需进一步核验",
    )


def _level_score(hospital: HospitalCandidate, hospital_level: str) -> float:
    if not hospital_level or hospital_level == "不限":
        return 0.7
    if "三级" in hospital.level or "三甲" in hospital.level:
        return 1.0
    if "专科" in hospital.level and "专科" in hospital_level:
        return 0.9
    if "三级" in hospital_level:
        return 0.55
    return 0.7


def _match_doctor(
    doctors: list[DoctorEvidence],
    hospital: str,
    department: str,
) -> tuple[str, str, float, str]:
    for doctor in doctors:
        if _same_hospital(doctor.hospital, hospital) and _same_department(doctor.department, department):
            return doctor.name, doctor.title, 1.0 if doctor.source_url else 0.75, doctor.source_url
    for doctor in doctors:
        if _same_hospital(doctor.hospital, hospital):
            return doctor.name, doctor.title, 0.68 if doctor.source_url else 0.58, doctor.source_url
    return "待人工确认", "", 0.35, ""


def _same_hospital(left: str, right: str) -> bool:
    left_norm = _normalize_match_text(left)
    right_norm = _normalize_match_text(right)
    return left_norm == right_norm or left_norm in right_norm or right_norm in left_norm


def _same_department(left: str, right: str) -> bool:
    left_norm = _normalize_department_name(left)
    right_norm = _normalize_department_name(right)
    return left_norm == right_norm or left_norm in right_norm or right_norm in left_norm


def _normalize_match_text(value: str) -> str:
    value = re.sub(r"[（(].*?[）)]", "", value)
    return re.sub(r"[\s·・,，。:：-]", "", value)


def _normalize_department_name(value: str) -> str:
    value = _normalize_match_text(value)
    aliases = {
        "心内科": "心血管内科",
        "心脏内科": "心血管内科",
        "呼吸科": "呼吸与危重症医学科",
        "呼吸内科": "呼吸与危重症医学科",
        "肿瘤内科": "肿瘤科",
        "消化科": "消化内科",
    }
    return aliases.get(value, value)


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        text = str(url).strip()
        if not text or not text.startswith(("http://", "https://")):
            continue
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _looks_like_hospital_official_url(url: str, hospital: str = "") -> bool:
    host = urlparse(url).netloc.lower()
    if not host:
        return False
    third_party_domains = [
        "haodf.com",
        "guahao.com",
        "weiyi.com",
        "mingyihui.net",
        "youlai.cn",
        "dxy.com",
        "bohe.cn",
        "39.net",
        "xywy.com",
        "120ask.com",
        "chunyuyisheng.com",
        "91160.com",
        "fh21.com.cn",
        "familydoctor.com.cn",
        "baidu.com",
        "zhihu.com",
        "sina.com",
        "sohu.com",
        "qq.com",
        "163.com",
        "toutiao.com",
        "wikipedia.org",
    ]
    if any(domain in host for domain in third_party_domains):
        return False
    official_markers = [
        "hospital",
        "hosp",
        "yiyuan",
        "huashan",
        "zs-hospital",
        "zshospital",
        "renji",
        "shsmu",
        "rjh",
        "shchildren",
        "shdc",
        "fudan",
        "fckyy",
        "sph",
        "shgh",
        "xkyy",
        "chhospital",
        "tongji",
        "xinhua",
    ]
    hospital_text = _normalize_match_text(hospital).lower()
    return any(marker in host for marker in official_markers) or (
        bool(hospital_text) and any(part and part in host for part in re.findall(r"[a-z0-9]+", hospital_text))
    )


def _normalize_recommendation_provider(value: str) -> str:
    text = (value or "").strip().lower()
    if "deepseek" in text or "deep" in text:
        return "deepseek"
    if "qwen" in text or "千问" in text or "通义" in text or "联网" in text:
        return "qwen"
    return "qwen"


def _rerank_with_llm(
    profile: PatientProfile,
    hospitals: list[HospitalCandidate],
    doctor_evidence: list[DoctorEvidence],
    heuristic: list[Recommendation],
    config: AppConfig,
    k: int,
) -> list[Recommendation]:
    from openai import OpenAI

    prompt = config.read_prompt("rank_hospitals.md") or "请重排医疗资源推荐，输出严格 JSON。"
    hospital_map = {hospital.name: hospital for hospital in hospitals}
    base_map = {rec.hospital: rec for rec in heuristic}
    doctor_names = {(doctor.hospital, doctor.name) for doctor in doctor_evidence if doctor.name}
    payload = {
        "patient_profile": profile.model_dump(),
        "candidate_hospitals": [hospital.model_dump() for hospital in hospitals[:24]],
        "doctor_evidence": [doctor.model_dump() for doctor in doctor_evidence],
        "heuristic_top": [rec.model_dump() for rec in heuristic],
        "k": k,
    }
    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)
    messages = [
        {"role": "system", "content": "你是严谨的医疗资源推荐排序助手。"},
        {"role": "user", "content": f"{prompt}\n\n输入数据：\n{json.dumps(payload, ensure_ascii=False)}"},
    ]
    try:
        response = client.chat.completions.create(
            model=config.text_model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except Exception:
        response = client.chat.completions.create(
            model=config.text_model,
            messages=messages,
            temperature=0.2,
        )
    raw = response.choices[0].message.content or "{}"
    data = _loads_json_object(raw)
    if isinstance(data, dict):
        rows = data.get("recommendations", [])
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    if not isinstance(rows, list):
        return []

    recommendations: list[Recommendation] = []
    for index, row in enumerate(rows[:k], start=1):
        if not isinstance(row, dict):
            continue
        hospital_name = row.get("hospital") or row.get("hospital_name") or ""
        if not hospital_name or hospital_name not in hospital_map:
            continue
        base = base_map.get(hospital_name)
        hospital = hospital_map[hospital_name]
        department = row.get("department") or (base.department if base else "")
        doctor = row.get("doctor") or "待人工确认"
        if doctor != "待人工确认" and doctor_names and (hospital_name, doctor) not in doctor_names:
            doctor = "待人工确认"
        rec = Recommendation(
            rank=index,
            hospital=hospital_name,
            department=department,
            doctor=doctor,
            title=row.get("title", ""),
            score=float(row.get("score", base.score if base else 70)),
            address=hospital.address,
            reasons=_as_list(row.get("reasons")) or (base.reasons if base else []),
            evidence_urls=_as_list(row.get("evidence_urls")),
            map_url=hospital.map_url,
            caveats=_as_list(row.get("caveats")) or ["推荐仅供就医资源选择参考，不能替代医生诊断。"],
        )
        recommendations.append(rec)
    return recommendations


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


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    if callback:
        callback(message)
