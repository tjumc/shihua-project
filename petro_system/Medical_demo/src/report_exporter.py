from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

from .config import AppConfig
from .schemas import PatientProfile, Recommendation


URGENCY_LABELS = {
    "routine": "常规就诊",
    "soon": "尽快就诊",
    "urgent": "建议及时就医",
}


def export_reports(
    profile: PatientProfile,
    recommendations: list[Recommendation],
    config: AppConfig,
) -> tuple[list[str], str]:
    config.outputs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = _safe_name(profile.patient_basic.name or "patient")
    base = config.outputs_dir / f"{stamp}_{name}"

    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    csv_path = base.with_suffix(".csv")

    payload = {
        "patient_profile": profile.model_dump(),
        "recommendations": [rec.model_dump() for rec in recommendations],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "disclaimer": "推荐仅供就医资源选择参考，不能替代医生诊断。",
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(profile, recommendations), encoding="utf-8")
    _write_csv(csv_path, recommendations)

    files = [str(json_path), str(md_path), str(csv_path)]
    return files, f"已导出 {len(files)} 个文件到 {config.outputs_dir}"


def recommendations_to_rows(recommendations: list[Recommendation]) -> list[dict[str, object]]:
    rows = []
    for rec in recommendations:
        rows.append(
            {
                "排名": rec.rank,
                "综合分": rec.score,
                "医院": rec.hospital,
                "科室": rec.department,
                "医生": rec.doctor,
                "职称": rec.title,
                "地址": rec.address,
                "推荐理由": "；".join(rec.reasons),
                "官网来源": "；".join(rec.official_source_urls),
                "证据链接": "；".join(rec.evidence_urls),
                "地图链接": rec.map_url,
                "提示": "；".join(rec.caveats),
            }
        )
    return rows


def _build_markdown(profile: PatientProfile, recommendations: list[Recommendation]) -> str:
    urgency = URGENCY_LABELS.get(profile.urgency_level, profile.urgency_level or "待评估")
    lines = [
        "# 就医资源推荐报告",
        "",
        "## 患者摘要",
        "",
        f"- 姓名：{profile.patient_basic.name or '未识别'}",
        f"- 性别：{profile.patient_basic.gender or '未识别'}",
        f"- 年龄：{profile.patient_basic.age or '未识别'}",
        f"- 病情摘要：{profile.present_illness or '未识别'}",
        f"- 主诉：{profile.chief_complaint or '未识别'}",
        f"- 当前症状：{'、'.join(profile.current_symptoms) or '未识别'}",
        f"- 既往史：{'、'.join(profile.past_history) or '未识别'}",
        f"- 疑似诊断/问题：{'、'.join(profile.suspected_diagnoses) or '待评估'}",
        f"- 紧急程度：{urgency}",
        "",
        "## 推荐结果",
        "",
    ]
    for rec in recommendations:
        lines.extend(
            [
                f"### {rec.rank}. {rec.hospital}",
                "",
                f"- 综合分：{rec.score}",
                f"- 推荐科室：{rec.department}",
                f"- 推荐医生：{rec.doctor}{(' / ' + rec.title) if rec.title else ''}",
                f"- 地址：{rec.address or '待确认'}",
                f"- 地图：{rec.map_url or '待确认'}",
                f"- 推荐理由：{'；'.join(rec.reasons)}",
                f"- 官网来源：{'；'.join(rec.official_source_urls) or '待确认'}",
                f"- 证据链接：{'；'.join(rec.evidence_urls) or ('AI直出医生，来源待确认' if rec.doctor != '待人工确认' else '医生/公开来源待人工确认')}",
                f"- 提示：{'；'.join(rec.caveats)}",
                "",
            ]
        )
    lines.extend(
        [
            "## 免责声明",
            "",
            "本报告仅供就医资源选择参考，不能替代医生诊断、治疗建议或保险核保结论。",
        ]
    )
    return "\n".join(lines)


def _write_csv(path: Path, recommendations: list[Recommendation]) -> None:
    rows = recommendations_to_rows(recommendations)
    fieldnames = list(rows[0].keys()) if rows else ["排名", "综合分", "医院", "科室", "医生"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name)[:32] or "patient"
