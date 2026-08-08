from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
import re

import requests

from ..config import AppConfig
from ..schemas import DepartmentCandidate, HospitalCandidate


@dataclass
class AmapHospitalSearch:
    config: AppConfig

    def search(
        self,
        departments: list[DepartmentCandidate],
        city: str = "上海",
        area: str = "",
        limit: int = 24,
    ) -> list[HospitalCandidate]:
        if not self.config.amap_api_key:
            return fallback_hospitals(city=city, area=area)
        try:
            return self._search_amap(departments, city, area, limit)
        except Exception:
            return fallback_hospitals(city=city, area=area)

    def search_by_names(
        self,
        names: list[str],
        city: str = "上海",
        area: str = "",
        limit: int = 12,
    ) -> list[HospitalCandidate]:
        unique_names = [name for name in dict.fromkeys(item.strip() for item in names) if name]
        if not unique_names:
            return []
        if not self.config.amap_api_key:
            return _match_fallback_by_names(unique_names, city, area)[:limit]

        candidates: list[HospitalCandidate] = []
        seen: set[str] = set()
        try:
            for name in unique_names:
                for hospital in self._search_amap_by_name(name, city, area):
                    if hospital.name in seen:
                        continue
                    seen.add(hospital.name)
                    candidates.append(hospital)
                    if len(candidates) >= limit:
                        return candidates
        except Exception:
            return _match_fallback_by_names(unique_names, city, area)[:limit]
        return candidates or _match_fallback_by_names(unique_names, city, area)[:limit]

    def _search_amap(
        self,
        departments: list[DepartmentCandidate],
        city: str,
        area: str,
        limit: int,
    ) -> list[HospitalCandidate]:
        queries = self._build_queries(departments, city, area)
        seen: set[str] = set()
        candidates: list[HospitalCandidate] = []

        for query in queries:
            params = {
                "key": self.config.amap_api_key,
                "keywords": query,
                "city": city,
                "citylimit": "true",
                "types": "090100|090101|090102",
                "offset": "20",
                "page": "1",
                "extensions": "base",
            }
            response = requests.get(
                "https://restapi.amap.com/v3/place/text",
                params=params,
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
            for poi in payload.get("pois", []):
                name = poi.get("name", "")
                if not name or name in seen:
                    continue
                hospital = _poi_to_hospital(poi, city)
                if not _hospital_matches_location(hospital, city, area):
                    continue
                seen.add(name)
                candidates.append(hospital)
                if len(candidates) >= limit:
                    return candidates
        return candidates or fallback_hospitals(city=city, area=area)

    def _search_amap_by_name(
        self,
        name: str,
        city: str,
        area: str,
    ) -> list[HospitalCandidate]:
        params = {
            "key": self.config.amap_api_key,
            "keywords": f"{city}{area}{name}" if area else f"{city}{name}",
            "city": city,
            "citylimit": "true",
            "types": "090100|090101|090102",
            "offset": "10",
            "page": "1",
            "extensions": "base",
        }
        response = requests.get(
            "https://restapi.amap.com/v3/place/text",
            params=params,
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        target = _normalize_name(name)
        rows: list[HospitalCandidate] = []
        for poi in payload.get("pois", []):
            poi_name = poi.get("name", "")
            if not poi_name:
                continue
            current = _normalize_name(poi_name)
            if target and not (target == current or target in current or current in target):
                continue
            hospital = _poi_to_hospital(poi, city)
            if area and area not in hospital.address and area not in hospital.district:
                continue
            rows.append(hospital)
        if rows:
            return rows

        loose_rows = []
        for poi in payload.get("pois", [])[:3]:
            if poi.get("name"):
                hospital = _poi_to_hospital(poi, city)
                if _hospital_matches_location(hospital, city, area):
                    loose_rows.append(hospital)
        return loose_rows

    @staticmethod
    def _build_queries(
        departments: list[DepartmentCandidate],
        city: str,
        area: str,
    ) -> list[str]:
        base = f"{city}{area}医院" if area else f"{city}医院"
        queries = [base, f"{city}三甲医院"]
        for item in departments[:3]:
            queries.append(f"{city}{area}{item.department} 医院" if area else f"{city}{item.department} 医院")
        return list(dict.fromkeys(queries))


def fallback_hospitals(city: str = "上海", area: str = "") -> list[HospitalCandidate]:
    if city and city != "上海":
        return []

    hospitals = [
        HospitalCandidate(
            name="复旦大学附属中山医院",
            address="上海市徐汇区枫林路180号",
            city=city,
            district="徐汇区",
            level="三级甲等",
            strengths=["心血管内科", "呼吸与危重症医学科", "消化内科", "肾内科"],
            source="fallback",
        ),
        HospitalCandidate(
            name="上海交通大学医学院附属瑞金医院",
            address="上海市黄浦区瑞金二路197号",
            city=city,
            district="黄浦区",
            level="三级甲等",
            strengths=["内分泌科", "血液科", "普外科", "消化内科"],
            source="fallback",
        ),
        HospitalCandidate(
            name="复旦大学附属华山医院",
            address="上海市静安区乌鲁木齐中路12号",
            city=city,
            district="静安区",
            level="三级甲等",
            strengths=["神经内科", "神经外科", "皮肤科", "感染科"],
            source="fallback",
        ),
        HospitalCandidate(
            name="上海市第六人民医院",
            address="上海市徐汇区宜山路600号",
            city=city,
            district="徐汇区",
            level="三级甲等",
            strengths=["骨科", "内分泌科", "超声医学科", "急诊医学科"],
            source="fallback",
        ),
        HospitalCandidate(
            name="上海交通大学医学院附属仁济医院",
            address="上海市浦东新区浦建路160号",
            city=city,
            district="浦东新区",
            level="三级甲等",
            strengths=["消化内科", "风湿免疫科", "泌尿外科", "肾内科"],
            source="fallback",
        ),
        HospitalCandidate(
            name="上海市胸科医院",
            address="上海市徐汇区淮海西路241号",
            city=city,
            district="徐汇区",
            level="三级甲等",
            strengths=["呼吸与危重症医学科", "胸外科", "肿瘤科", "心血管内科"],
            source="fallback",
        ),
        HospitalCandidate(
            name="复旦大学附属肿瘤医院",
            address="上海市徐汇区东安路270号",
            city=city,
            district="徐汇区",
            level="三级甲等",
            strengths=["肿瘤科", "病理科", "放疗科", "肿瘤外科"],
            source="fallback",
        ),
        HospitalCandidate(
            name="上海市第一人民医院",
            address="上海市虹口区海宁路100号",
            city=city,
            district="虹口区",
            level="三级甲等",
            strengths=["眼科", "泌尿外科", "心血管内科", "急诊医学科"],
            source="fallback",
        ),
        HospitalCandidate(
            name="上海市精神卫生中心",
            address="上海市徐汇区宛平南路600号",
            city=city,
            district="徐汇区",
            level="三级甲等",
            strengths=["精神科", "心理咨询"],
            source="fallback",
        ),
    ]
    for hospital in hospitals:
        hospital.map_url = _map_url(hospital.name, city, hospital.location)
    if area:
        return [hospital for hospital in hospitals if _hospital_matches_location(hospital, city, area)]
    return hospitals


def _poi_to_hospital(poi: dict, city: str) -> HospitalCandidate:
    name = poi.get("name", "")
    location = poi.get("location", "")
    return HospitalCandidate(
        name=name,
        address=poi.get("address") or "",
        city=city,
        district=poi.get("adname") or "",
        phone=poi.get("tel") or "",
        location=location,
        level=_guess_level(name, poi.get("type", "")),
        strengths=[],
        source="amap",
        map_url=_map_url(name, city, location),
    )


def _match_fallback_by_names(names: list[str], city: str, area: str) -> list[HospitalCandidate]:
    hospitals = fallback_hospitals(city=city, area=area)
    rows: list[HospitalCandidate] = []
    for name in names:
        target = _normalize_name(name)
        for hospital in hospitals:
            current = _normalize_name(hospital.name)
            if target == current or target in current or current in target:
                rows.append(hospital)
                break
    return rows


def _hospital_matches_location(hospital: HospitalCandidate, city: str, area: str = "") -> bool:
    if city and hospital.city and hospital.city != city:
        return False
    if city and hospital.address and city not in hospital.address and hospital.source == "fallback":
        return False
    if area and area not in hospital.address and area not in hospital.district:
        return False
    return True


def _normalize_name(value: str) -> str:
    value = re.sub(r"[（(].*?[）)]", "", value)
    return re.sub(r"[\s·・,，。:：-]", "", value)


def _guess_level(name: str, poi_type: str) -> str:
    if "三甲" in name or "三级甲等" in name:
        return "三级甲等"
    if "医院" in name and ("附属" in name or "大学" in name):
        return "三级优先"
    if "专科" in poi_type:
        return "专科医院"
    return ""


def _map_url(name: str, city: str, location: str = "") -> str:
    query = urllib.parse.quote(f"{city} {name}")
    if location:
        return f"https://uri.amap.com/marker?position={location}&name={urllib.parse.quote(name)}"
    return f"https://www.amap.com/search?query={query}"
