from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is optional at import time
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    if value.startswith("your_") or value.startswith("optional_"):
        return ""
    return value


@dataclass(frozen=True)
class AppConfig:
    project_root: Path = PROJECT_ROOT
    dashscope_api_key: str = _env("DASHSCOPE_API_KEY")
    amap_api_key: str = _env("AMAP_API_KEY")
    search_api_key: str = _env("SEARCH_API_KEY")
    deepseek_api_key: str = _env("DEEPSEEK_API_KEY")
    dashscope_base_url: str = _env(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    deepseek_base_url: str = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    qwen_base_url: str = _env(
        "QWEN_BASE_URL",
        _env("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )
    text_model: str = _env("LLM_MODEL_TEXT", "qwen-plus")
    vision_model: str = _env("LLM_MODEL_VISION", "qwen3-vl-plus")
    ocr_model: str = _env("DASHSCOPE_OCR_MODEL", "qwen-vl-ocr-2025-11-20")
    medical_record_parse_mode: str = _env("MEDICAL_RECORD_PARSE_MODE", "qwen_ocr")
    deepseek_model: str = _env("DEEPSEEK_MODEL", "deepseek-v4-pro")
    assistant_provider: str = _env("ASSISTANT_PROVIDER", "qwen")
    qwen_assistant_model: str = _env("QWEN_ASSISTANT_MODEL", "qwen3.7-max")
    qwen_assistant_fallback_model: str = _env("QWEN_ASSISTANT_FALLBACK_MODEL", "qwen3.7-max")
    recommendation_provider: str = _env("RECOMMENDATION_PROVIDER", "qwen")
    search_provider: str = _env("SEARCH_PROVIDER", "deepseek_agent")
    web_search_provider: str = _env("WEB_SEARCH_PROVIDER", "bocha")
    qwen_vl_pages_per_call: int = int(_env("QWEN_VL_PAGES_PER_CALL", "2") or "2")
    default_city: str = _env("DEFAULT_CITY", "上海")
    enable_llm_rerank: bool = _env("ENABLE_LLM_RERANK", "1") == "1"

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def prompt_dir(self) -> Path:
        return self.project_root / "prompts"

    @property
    def demo_mode(self) -> bool:
        return not bool(self.dashscope_api_key)

    @property
    def use_deepseek_agent(self) -> bool:
        return self.recommendation_provider.lower() == "deepseek" and bool(self.deepseek_api_key)

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.uploads_dir, self.cache_dir, self.outputs_dir):
            path.mkdir(parents=True, exist_ok=True)

    def read_prompt(self, name: str) -> str:
        path = self.prompt_dir / name
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def key_status(self) -> dict[str, str]:
        return {
            "文字识别模型": "已配置" if self.dashscope_api_key else "未配置，演示模式",
            "高德地图": "已配置" if self.amap_api_key else "未配置，使用内置候选",
            "推荐智能体": self._recommendation_status(),
            "AI助手": self._assistant_status(),
            "网页搜索": "已配置" if self.search_api_key else "未配置，优先使用 DeepSeek 直出医生兜底",
        }

    def _recommendation_status(self) -> str:
        provider = self.recommendation_provider.lower()
        if provider == "qwen":
            return f"Qwen已配置（{self.qwen_assistant_model}）" if self.dashscope_api_key else "Qwen未配置，使用规则重排"
        if provider == "deepseek":
            return "DeepSeek已配置" if self.deepseek_api_key else "DeepSeek未配置，使用规则重排"
        return f"未知推荐引擎：{self.recommendation_provider}"

    def _assistant_status(self) -> str:
        provider = self.assistant_provider.lower()
        if provider == "qwen":
            return "Qwen联网已配置" if self.dashscope_api_key else "Qwen未配置，需DASHSCOPE_API_KEY"
        if provider == "deepseek":
            return "DeepSeek已配置" if self.deepseek_api_key else "DeepSeek未配置"
        return f"未知助手：{self.assistant_provider}"


def get_config() -> AppConfig:
    config = AppConfig()
    config.ensure_dirs()
    return config
