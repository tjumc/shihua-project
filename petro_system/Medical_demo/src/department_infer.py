from __future__ import annotations

from collections import defaultdict

from .schemas import DepartmentCandidate, PatientProfile


DEPARTMENT_KEYWORDS: dict[str, list[str]] = {
    "心血管内科": ["胸痛", "胸闷", "心悸", "心电图", "冠心病", "高血压", "心肌", "心衰"],
    "呼吸与危重症医学科": ["咳嗽", "咳痰", "发热", "肺", "胸部CT", "气促", "呼吸困难", "哮喘"],
    "消化内科": ["腹痛", "腹胀", "胃", "肝", "胆", "胰", "肠", "便血", "黑便", "消化"],
    "神经内科": ["头晕", "头痛", "脑梗", "脑卒中", "肢体麻木", "癫痫", "意识障碍"],
    "骨科": ["骨折", "关节", "腰痛", "颈椎", "腰椎", "膝", "肩", "外伤", "骨质"],
    "内分泌科": ["糖尿病", "血糖", "甲状腺", "尿酸", "痛风", "代谢"],
    "肿瘤科": ["肿瘤", "癌", "结节", "占位", "病理", "化疗", "放疗"],
    "肾内科": ["肌酐", "尿蛋白", "肾", "尿素", "血尿", "肾功能"],
    "泌尿外科": ["前列腺", "泌尿", "尿频", "尿急", "尿痛", "结石"],
    "妇科": ["子宫", "卵巢", "阴道", "月经", "妇科", "宫颈"],
    "皮肤科": ["皮疹", "瘙痒", "皮肤", "湿疹", "荨麻疹"],
}

URGENT_KEYWORDS = ["胸痛", "呼吸困难", "意识障碍", "晕厥", "大出血", "休克", "卒中", "偏瘫"]


def infer_departments(profile: PatientProfile, limit: int = 3) -> list[DepartmentCandidate]:
    text_parts = [
        profile.chief_complaint,
        profile.present_illness,
        " ".join(profile.past_history),
        " ".join(profile.current_symptoms),
        " ".join(profile.suspected_diagnoses),
        " ".join(f"{item.item} {item.result}" for item in profile.exam_results),
    ]
    haystack = " ".join(text_parts)
    scores: dict[str, float] = defaultdict(float)
    reasons: dict[str, list[str]] = defaultdict(list)

    for department, keywords in DEPARTMENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword and keyword in haystack:
                scores[department] += 1.0
                if len(reasons[department]) < 3:
                    reasons[department].append(keyword)

    if not scores:
        scores["全科医学科"] = 0.6
        reasons["全科医学科"].append("资料中未形成明确专科线索，建议先由全科或综合门诊评估")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    candidates = []
    for department, score in ranked:
        confidence = min(0.95, 0.45 + score * 0.12)
        reason_text = "、".join(reasons[department]) or "根据病历综合信息匹配"
        candidates.append(
            DepartmentCandidate(
                department=department,
                reason=f"匹配线索：{reason_text}",
                confidence=round(confidence, 2),
            )
        )
    return candidates


def infer_urgency(profile: PatientProfile) -> tuple[str, list[str]]:
    text = " ".join(
        [
            profile.chief_complaint,
            profile.present_illness,
            " ".join(profile.current_symptoms),
            " ".join(profile.risk_flags),
        ]
    )
    flags = [keyword for keyword in URGENT_KEYWORDS if keyword in text]
    if flags:
        return "urgent", [f"发现可能需要及时就医的风险线索：{keyword}" for keyword in flags]
    if profile.exam_results and any(item.abnormal for item in profile.exam_results):
        return "soon", ["存在异常检查结果，建议尽快预约相应专科"]
    return "routine", []
