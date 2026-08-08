from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ..config import AppConfig
from ..deepseek_agent import extract_doctor_evidence_from_search
from ..schemas import DepartmentCandidate, DoctorEvidence, HospitalCandidate, PatientProfile


THIRD_PARTY_DOCTOR_PLATFORM_TERMS = (
    "好大夫 微医 名医汇 有来医生 丁香医生 健康160 春雨医生 "
    "寻医问药 39健康 博禾医生 复禾健康 家庭医生在线 医联媒体"
)


def collect_doctor_evidence(
    hospitals: list[HospitalCandidate],
    departments: list[DepartmentCandidate],
    config: AppConfig | None = None,
    profile: PatientProfile | None = None,
    search_plan: dict[str, Any] | None = None,
    require_doctor: bool = False,
    log_callback: Callable[[str], None] | None = None,
) -> list[DoctorEvidence]:
    """Search the web and ask the reasoning model to extract verified doctor evidence."""
    if not config or not profile:
        return []
    if not config.search_api_key or not config.deepseek_api_key:
        _emit(log_callback, "未配置网页搜索或推理模型密钥，跳过医生证据检索。")
        return []
    city = (profile.patient_need.preferred_city or profile.patient_basic.city or "").strip()
    area = (profile.patient_need.preferred_area or "").strip()
    queries = _queries_from_plan(search_plan, hospitals, departments, city=city, area=area)
    if not queries:
        _emit(log_callback, "没有生成有效网页搜索查询，跳过医生证据检索。")
        return []

    query_limit = 22 if require_doctor else 14
    per_query = 8 if require_doctor else 6
    max_pages = 28 if require_doctor else 18
    location_text = f"，地点条件：{city}{area}" if city or area else ""
    priority_text = "，有医院官网来源优先，增加官方资料检索" if require_doctor else ""
    _emit(log_callback, f"准备调用网页搜索服务，候选查询 {len(queries)} 条，执行前 {query_limit} 条{location_text}{priority_text}。")
    search_results = run_web_searches(config, queries[:query_limit], per_query=per_query, log_callback=log_callback)
    if not search_results:
        _emit(log_callback, "网页搜索未返回可用结果。")
        return []
    _emit(log_callback, f"网页搜索返回 {len(search_results)} 条去重结果，开始抓取高优先级页面正文。")
    search_results = enrich_results_with_page_text(search_results, max_pages=max_pages, log_callback=log_callback)
    fetched_count = sum(1 for item in search_results if item.get("page_text"))
    _emit(log_callback, f"已抓取 {fetched_count} 个网页正文，交给推理模型抽取医生证据。")
    return extract_doctor_evidence_from_search(
        profile=profile,
        hospitals=hospitals,
        search_results=search_results,
        config=config,
        log_callback=log_callback,
    )


def run_web_searches(
    config: AppConfig,
    queries: list[dict[str, str]],
    per_query: int = 5,
    log_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    provider = (config.web_search_provider or "bocha").lower()
    results: list[dict[str, Any]] = []
    for query_item in queries:
        query = query_item.get("query", "").strip()
        if not query:
            continue
        _emit(log_callback, f"网页搜索：{query}")
        try:
            if provider == "tavily":
                rows = _search_tavily(config.search_api_key, query, per_query)
            else:
                rows = _search_bocha(config.search_api_key, query, per_query)
            _emit(log_callback, f"检索完成：{query}，返回 {len(rows)} 条结果。")
        except Exception:
            _emit(log_callback, f"检索失败：{query}")
            rows = []
        for row in rows:
            row.update(
                {
                    "query": query,
                    "hospital": query_item.get("hospital", ""),
                    "department": query_item.get("department", ""),
                    "city": query_item.get("city", ""),
                    "area": query_item.get("area", ""),
                    "provider": provider,
                }
            )
            results.append(row)
    return _dedupe_results(results)


def enrich_results_with_page_text(
    results: list[dict[str, Any]],
    max_pages: int = 12,
    log_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    ranked = sorted(results, key=_result_priority, reverse=True)
    enriched: list[dict[str, Any]] = []
    fetched = 0
    for item in ranked:
        row = dict(item)
        if fetched < max_pages and _should_fetch_url(row):
            _emit(log_callback, f"抓取网页正文：{row.get('title', '')[:40]} | {row.get('url', '')}")
            text = _fetch_page_text(row.get("url", ""))
            if text:
                row["page_text"] = text
                row["source_kind"] = "fetched_page"
                fetched += 1
                _emit(log_callback, f"正文抓取成功：{len(text)} 字。")
            else:
                _emit(log_callback, "正文抓取失败或页面不可读，保留搜索摘要。")
        enriched.append(row)
    return enriched


def _queries_from_plan(
    search_plan: dict[str, Any] | None,
    hospitals: list[HospitalCandidate],
    departments: list[DepartmentCandidate],
    city: str = "",
    area: str = "",
) -> list[dict[str, str]]:
    queries: list[dict[str, str]] = []
    if isinstance(search_plan, dict):
        for item in search_plan.get("search_queries", []) or []:
            if not isinstance(item, dict):
                continue
            query = str(item.get("query", "")).strip()
            if query:
                queries.append(
                    {
                        "query": _with_location_terms(query, city, area),
                        "hospital": str(item.get("hospital", "")),
                        "department": str(item.get("department", "")),
                        "city": city,
                        "area": area,
                    }
                )
    if queries:
        return _augment_queries(queries, hospitals, departments, city=city, area=area)

    top_departments = departments[:3] or [DepartmentCandidate(department="专家门诊")]
    for hospital in hospitals[:8]:
        for department in top_departments:
            queries.append(
                {
                    "hospital": hospital.name,
                    "department": department.department,
                    "query": _with_location_terms(
                        f"{hospital.name} {department.department} 医生 专家 擅长 出诊 第三方医生查询平台",
                        city,
                        area,
                    ),
                    "city": city,
                    "area": area,
                }
            )
    return _augment_queries(queries, hospitals, departments, city=city, area=area)


def _augment_queries(
    queries: list[dict[str, str]],
    hospitals: list[HospitalCandidate],
    departments: list[DepartmentCandidate],
    city: str = "",
    area: str = "",
) -> list[dict[str, str]]:
    augmented = list(queries)
    top_departments = departments[:3] or [DepartmentCandidate(department="专家门诊")]
    for hospital in hospitals[:8]:
        for department in top_departments:
            augmented.extend(
                [
                    {
                        "hospital": hospital.name,
                        "department": department.department,
                        "query": _with_location_terms(
                            f"{hospital.name} {department.department} 医生 专家 擅长 出诊",
                            city,
                            area,
                        ),
                        "city": city,
                        "area": area,
                    },
                    {
                        "hospital": hospital.name,
                        "department": department.department,
                        "query": _with_location_terms(
                            f"{hospital.name} {department.department} 医生主页 专家门诊 挂号",
                            city,
                            area,
                        ),
                        "city": city,
                        "area": area,
                    },
                    {
                        "hospital": hospital.name,
                        "department": department.department,
                        "query": _with_location_terms(
                            f"{hospital.name} {department.department} 医生团队 专家介绍 互联网公开资料",
                            city,
                            area,
                        ),
                        "city": city,
                        "area": area,
                    },
                    {
                        "hospital": hospital.name,
                        "department": department.department,
                        "query": _with_location_terms(
                            f"{hospital.name} {department.department} 主任医师 副主任医师 出诊",
                            city,
                            area,
                        ),
                        "city": city,
                        "area": area,
                    },
                    {
                        "hospital": hospital.name,
                        "department": department.department,
                        "query": _with_location_terms(
                            f"{hospital.name} {department.department} {THIRD_PARTY_DOCTOR_PLATFORM_TERMS} 医生",
                            city,
                            area,
                        ),
                        "city": city,
                        "area": area,
                    },
                ]
            )
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in augmented:
        query = item.get("query", "").strip()
        if not query or query in seen:
            continue
        seen.add(query)
        unique.append(item)
    return unique


def _with_location_terms(query: str, city: str = "", area: str = "") -> str:
    parts = []
    if city and city not in query:
        parts.append(city)
    if area and area not in query:
        parts.append(area)
    parts.append(query)
    return " ".join(part for part in parts if part).strip()


def _search_bocha(api_key: str, query: str, count: int) -> list[dict[str, Any]]:
    response = requests.post(
        "https://api.bochaai.com/v1/web-search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "count": count,
            "summary": True,
            "freshness": "noLimit",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    values = (
        payload.get("data", {})
        .get("webPages", {})
        .get("value", [])
    )
    if not values and isinstance(payload.get("webPages"), dict):
        values = payload.get("webPages", {}).get("value", [])
    rows = []
    for item in values or []:
        title = item.get("name") or item.get("title") or ""
        url = item.get("url") or ""
        snippet = item.get("snippet") or item.get("summary") or item.get("description") or ""
        if not title or not url:
            continue
        rows.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "site_name": item.get("siteName") or item.get("site_name") or "",
                "published_at": item.get("datePublished") or "",
            }
        )
    return rows


def _search_tavily(api_key: str, query: str, count: int) -> list[dict[str, Any]]:
    body = {
        "query": query,
        "search_depth": "advanced",
        "max_results": count,
        "include_answer": False,
        "include_raw_content": False,
    }
    response = requests.post(
        "https://api.tavily.com/search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=20,
    )
    if response.status_code in {401, 403}:
        body_with_key = dict(body)
        body_with_key["api_key"] = api_key
        response = requests.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json=body_with_key,
            timeout=20,
        )
    response.raise_for_status()
    payload = response.json()
    rows = []
    for item in payload.get("results", []) or []:
        title = item.get("title") or ""
        url = item.get("url") or ""
        snippet = item.get("content") or item.get("snippet") or ""
        if not title or not url:
            continue
        rows.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "site_name": "",
                "published_at": "",
            }
        )
    return rows


def _dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in results:
        url = item.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(item)
    return unique


def _result_priority(item: dict[str, Any]) -> int:
    text = " ".join(
        str(item.get(key, "")) for key in ["title", "snippet", "url", "site_name"]
    )
    score = 0
    city = str(item.get("city", "")).strip()
    area = str(item.get("area", "")).strip()
    hospital = str(item.get("hospital", "")).strip()
    if city and city in text:
        score += 4
    if area and area in text:
        score += 6
    if hospital and hospital in text:
        score += 5
    for keyword in ["官网", "官方", "医院", "科室", "专家", "医生", "门诊", "擅长", "主任医师", "副主任医师"]:
        if keyword in text:
            score += 2
    for keyword in ["医生团队", "专家介绍", "医院官网", "官方网站", "出诊", "专家门诊"]:
        if keyword in text:
            score += 3
    if _looks_like_medical_platform(item.get("url", "")):
        score += 2
    if _looks_like_file(item.get("url", "")):
        score -= 3
    return score


def _should_fetch_url(item: dict[str, Any]) -> bool:
    url = item.get("url", "")
    if not url.startswith(("http://", "https://")):
        return False
    if _looks_like_file(url):
        return False
    if _looks_like_search_engine(url):
        return False
    return _result_priority(item) > 0


def _fetch_page_text(url: str) -> str:
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
                )
            },
            timeout=12,
        )
        response.raise_for_status()
    except Exception:
        return ""
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return ""
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
        tag.decompose()
    title = soup.get_text("\n", strip=True)
    title = re.sub(r"\n{2,}", "\n", title)
    title = re.sub(r"[ \t]{2,}", " ", title)
    return title[:12000]


def _looks_like_file(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar"))


def _looks_like_search_engine(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    blocked_hosts = [
        "www.baidu.com",
        "m.baidu.com",
        "www.sogou.com",
        "m.sogou.com",
        "www.so.com",
        "m.so.com",
        "cn.bing.com",
        "www.bing.com",
        "www.google.com",
        "google.com",
    ]
    return host in blocked_hosts


def _looks_like_medical_platform(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    platforms = [
        "haodf.com",
        "chunyuyisheng.com",
        "guahao.com",
        "weiyi.com",
        "120ask.com",
        "39.net",
        "xywy.com",
        "99.com.cn",
        "fh21.com.cn",
        "bohe.cn",
        "duobiyi.com",
        "familydoctor.com.cn",
        "cnkang.com",
        "mingyihui.net",
        "yilianmeiti.com",
        "youlai.cn",
        "91160.com",
        "dxy.com",
        "medlive.cn",
        "myzx.cn",
        "daifu.com",
        "cn-healthcare.com",
        "baike.baidu.com",
        "wikipedia.org",
    ]
    return any(domain in host for domain in platforms)


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    if callback:
        callback(message)
