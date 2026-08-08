from __future__ import annotations

import html
import os
import queue
import re
import threading
import time
from pathlib import Path
from typing import Any

import gradio as gr
import pandas as pd

from src.config import get_config
from src.cities import CITY_CHOICES
from src.department_infer import infer_departments, infer_urgency
from src.deepseek_agent import chat_with_medical_assistant
from src.llm_extract import extract_medical_profile
from src.recommender import recommend_resources
from src.report_exporter import export_reports
from src.schemas import PatientProfile, Recommendation, parse_profile_json


CONFIG = get_config()

URGENCY_LABELS = {
    "routine": "常规就诊",
    "soon": "尽快就诊",
    "urgent": "建议及时就医",
}

EXAM_TYPE_LABELS = {
    "lab": "检验",
    "imaging": "影像",
    "ecg": "心电图",
    "pathology": "病理",
    "other": "其他检查",
}

ASSISTANT_WELCOME = "我是您的AI医疗助手，有什么可以帮助的吗？"
ASSISTANT_PROVIDER_LABELS = {
    "qwen": "Qwen联网",
    "deepseek": "DeepSeek",
}
ASSISTANT_PROVIDER_CHOICES = list(ASSISTANT_PROVIDER_LABELS.values())

RECOMMENDATION_INTENT_WORDS = (
    "重新推荐",
    "再推荐",
    "重推",
    "换一批",
    "重新找",
    "重新生成",
    "帮我推荐",
    "推荐医院",
    "找医院",
    "找个医院",
    "找一个医院",
    "附近医院",
)

NEARBY_INTENT_WORDS = (
    "近点",
    "近一点",
    "附近",
    "离我近",
    "离家近",
    "最近",
    "周边",
    "就近",
)

COMMON_AREA_ALIASES = {
    "浦东": "浦东新区",
    "徐汇": "徐汇区",
    "黄浦": "黄浦区",
    "静安": "静安区",
    "长宁": "长宁区",
    "普陀": "普陀区",
    "虹口": "虹口区",
    "杨浦": "杨浦区",
    "闵行": "闵行区",
    "宝山": "宝山区",
    "嘉定": "嘉定区",
    "金山": "金山区",
    "松江": "松江区",
    "青浦": "青浦区",
    "奉贤": "奉贤区",
    "崇明": "崇明区",
}

THEME = gr.themes.Soft(
    primary_hue="teal",
    secondary_hue="blue",
    neutral_hue="slate",
    radius_size="sm",
)


CSS = """
html,
body,
gradio-app {
  min-height: 100vh;
  background: #f5f7fa;
}
.gradio-container {
  width: min(144vh, calc(100vw - 20px)) !important;
  max-width: min(144vh, calc(100vw - 20px)) !important;
  height: 80vh !important;
  min-height: 80vh !important;
  margin: 10vh auto !important;
  padding: 12px !important;
  background: #f5f7fa !important;
  box-sizing: border-box !important;
  overflow: hidden !important;
}
#app-header {
  border: 1px solid #d8e0e8;
  border-radius: 8px;
  background: #ffffff;
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
  box-sizing: border-box;
  width: 100%;
}
#app-header h1 {
  margin: 0 0 6px 0;
  color: #0f172a;
  font-size: 27px;
  line-height: 1.2;
  letter-spacing: 0;
}
#app-header p {
  margin: 0;
  color: #475569;
  font-size: 15px;
}
.status-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.status-pill {
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  padding: 5px 10px;
  background: #ffffff;
  color: #334155;
  font-size: 13px;
}
.status-pill.ready {
  border-color: #99f6e4;
  background: #ecfdf5;
  color: #0f766e;
}
.status-pill.warn {
  border-color: #fed7aa;
  background: #fff7ed;
  color: #b45309;
}
.primary-note {
  border: 1px solid #d8e0e8;
  border-left: 4px solid #0f766e;
  background: #ffffff;
  padding: 10px 12px;
  border-radius: 8px;
  color: #334155;
  line-height: 1.65;
}
#step-nav {
  border: 1px solid #d8e0e8;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  padding: 8px;
  margin: 0 0 12px 0;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.05);
}
#step-nav button {
  min-height: 38px !important;
  border-radius: 8px !important;
  font-weight: 700 !important;
}
button.step-button {
  background: #ecfdf5 !important;
  border: 1px solid #99f6e4 !important;
  color: #0f766e !important;
  box-shadow: none !important;
}
button.step-button:hover {
  background: #ccfbf1 !important;
  border-color: #5eead4 !important;
  color: #115e59 !important;
}
button.action-button {
  min-height: 38px !important;
  border-radius: 8px !important;
  background: #0f766e !important;
  border-color: #0f766e !important;
  color: #ffffff !important;
  font-weight: 800 !important;
}
#workspace-row {
  align-items: stretch;
  height: calc(80vh - 144px);
  min-height: 0;
  width: 100% !important;
  margin: 0 !important;
  gap: 12px !important;
  box-sizing: border-box;
}
#input-panel,
#main-panel {
  border: 1px solid #d8e0e8;
  border-radius: 8px;
  background: #ffffff;
  padding: 12px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}
#input-panel {
  flex: 0 0 250px !important;
  max-width: 250px;
  height: 100%;
  overflow: auto;
}
#main-panel {
  flex: 1 1 auto !important;
  min-width: 0 !important;
  height: 100%;
  overflow: hidden;
}
#subpage-frame {
  border: 1px solid #d8e0e8;
  border-radius: 8px;
  background: #ffffff;
  height: calc(100% - 58px);
  min-height: 0;
  padding: 12px;
  overflow: auto;
}
#parse-page,
#recommend-page,
#export-page {
  min-height: 100%;
}
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 0 10px 0;
  color: #0f172a;
  font-size: 16px;
  font-weight: 800;
}
.summary-card {
  border: 1px solid #d8e0e8;
  border-radius: 8px;
  background: #ffffff;
  padding: 12px;
  color: #334155;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 10px 0;
}
.summary-item {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  padding: 8px 10px;
  min-height: 54px;
}
.summary-label {
  display: block;
  color: #64748b;
  font-size: 12px;
  margin-bottom: 2px;
}
.summary-value {
  color: #0f172a;
  font-weight: 700;
  line-height: 1.4;
}
.summary-list {
  margin: 8px 0 0 0;
  padding-left: 18px;
  color: #334155;
  line-height: 1.55;
}
.activity-panel {
  border: 1px solid #d8e0e8;
  border-radius: 8px;
  background: #f8fafc;
  padding: 10px 12px;
  color: #334155;
  line-height: 1.55;
}
.activity-panel h3 {
  margin: 0 0 6px 0;
  font-size: 15px;
  color: #0f172a;
}
.activity-panel ul {
  margin: 0;
  padding-left: 18px;
}
.activity-panel li {
  margin: 3px 0;
}
.recommendation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 12px;
}
.recommendation-card {
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: #ffffff;
  padding: 14px;
  min-height: 230px;
}
.rec-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.rec-title h3 {
  margin: 0;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.3;
}
.score-badge {
  flex: 0 0 auto;
  border-radius: 999px;
  padding: 4px 9px;
  background: #e0f2fe;
  color: #075985;
  font-weight: 700;
  font-size: 13px;
}
.rec-meta {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 6px 8px;
  color: #334155;
  font-size: 14px;
  margin: 8px 0;
}
.rec-meta b {
  color: #64748b;
  font-weight: 600;
}
.rec-reasons {
  margin: 10px 0 0 0;
  padding-left: 18px;
  color: #334155;
  font-size: 14px;
}
.rec-links a {
  color: #2563eb;
  text-decoration: none;
  font-weight: 600;
}
.footer-disclaimer {
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}
button.primary {
  background: #0f766e !important;
  border-color: #0f766e !important;
}
@media (max-width: 760px) {
  .gradio-container {
    width: 100vw !important;
    max-width: 100vw !important;
    height: auto !important;
    min-height: 100vh !important;
    margin: 0 auto !important;
    padding: 8px !important;
    overflow: visible !important;
  }
  #app-header h1 {
    font-size: 23px;
  }
  #app-header {
    padding: 14px 16px;
    margin-bottom: 12px;
  }
  #input-panel {
    max-width: none;
    min-height: auto;
  }
  #workspace-row {
    height: auto;
  }
  #main-panel,
  #subpage-frame,
  #parse-page,
  #recommend-page,
  #export-page {
    min-height: auto;
  }
  .summary-grid {
    grid-template-columns: 1fr;
  }
  .recommendation-grid {
    grid-template-columns: 1fr;
  }
}
.gradio-container {
  width: auto !important;
  max-width: 1440px !important;
  height: auto !important;
  min-height: auto !important;
  margin: 0 auto !important;
  padding: 20px 18px 30px !important;
  background: #f5f7fa !important;
  overflow: visible !important;
}
#app-header {
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: linear-gradient(135deg, #ffffff 0%, #eef7f5 100%);
  padding: 18px 20px;
  margin-bottom: 14px;
  box-shadow: none;
}
#app-header h1 {
  margin: 0 0 8px 0;
  font-size: 28px;
}
#app-header p {
  font-size: 14px;
}
#workspace-row {
  height: auto !important;
  min-height: 0 !important;
  width: auto !important;
  margin: 0 !important;
  gap: 0 !important;
}
#input-panel,
#main-panel {
  border: 0;
  box-shadow: none;
  padding: 0;
  background: transparent;
}
#input-panel {
  flex: initial !important;
  max-width: none;
  height: auto;
  overflow: visible;
}
#main-panel {
  flex: initial !important;
  min-width: 430px !important;
  height: auto;
  overflow: visible;
}
#subpage-frame,
#parse-page,
#recommend-page,
#export-page {
  height: auto;
  min-height: 0;
  border: 0;
  padding: 0;
  overflow: visible;
}
.gradio-container {
  max-width: 1440px !important;
  padding: 20px 18px 30px !important;
}
#workspace-row {
  align-items: stretch !important;
  min-height: 560px !important;
  gap: 16px !important;
}
#input-panel,
#main-panel {
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: #ffffff;
  padding: 14px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}
#input-panel {
  flex: 0 0 300px !important;
  max-width: 300px !important;
}
#main-panel {
  flex: 1 1 auto !important;
  min-width: 520px !important;
}
#step-nav {
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0;
  margin: 0 0 8px 0;
  box-shadow: none;
}
#step-nav button {
  min-height: 38px !important;
  border-radius: 8px !important;
  font-weight: 800 !important;
}
button.step-button {
  background: #ecfdf5 !important;
  border: 1px solid #99f6e4 !important;
  color: #0f766e !important;
}
button.step-button:hover {
  background: #ccfbf1 !important;
  border-color: #5eead4 !important;
}
#subpage-frame {
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: #ffffff;
  min-height: 500px;
  padding: 14px;
  overflow: auto;
}
#parse-page,
#recommend-page,
#export-page {
  min-height: 470px;
}
#workspace-row {
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: stretch !important;
  gap: 16px !important;
}
#input-panel {
  flex: 0 0 240px !important;
  width: 240px !important;
  min-width: 240px !important;
  max-width: 240px !important;
}
#main-panel {
  flex: 1 1 0 !important;
  width: auto !important;
  min-width: 0 !important;
  max-width: none !important;
}
@media (max-width: 760px) {
  #workspace-row {
    flex-wrap: wrap !important;
  }
  #input-panel,
  #main-panel {
    flex: 1 1 100% !important;
    width: 100% !important;
    max-width: none !important;
  }
}
html,
body,
gradio-app {
  height: 100vh !important;
  height: 100dvh !important;
  min-height: 100vh !important;
  margin: 0 !important;
  background: #f5f7fa !important;
  overflow-x: hidden !important;
  overflow-y: hidden !important;
}
.gradio-container > .main,
.gradio-container > .main > .wrap,
.gradio-container > .main > .wrap > .contain,
.gradio-container > .main > .wrap > .contain > .gap,
.gradio-container > .gap {
  height: 100% !important;
  min-height: 0 !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 8px !important;
  overflow: hidden !important;
}
.gradio-container {
  width: 100vw !important;
  width: 100dvw !important;
  max-width: 100vw !important;
  max-width: 100dvw !important;
  height: 100vh !important;
  height: 100dvh !important;
  min-height: 100vh !important;
  min-height: 100dvh !important;
  margin: 0 !important;
  padding: 10px 14px !important;
  background: #f5f7fa !important;
  overflow: hidden !important;
  display: flex !important;
  flex-direction: column !important;
  box-sizing: border-box !important;
  box-shadow: none !important;
}
#app-header {
  width: 100% !important;
  flex: 0 0 auto !important;
  box-sizing: border-box !important;
  background: #ffffff !important;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06) !important;
  margin: 0 0 8px 0 !important;
  flex: 0 0 auto !important;
}
#app-header,
#input-panel,
#main-panel,
#step-nav,
#subpage-frame {
  border: 1px solid #d9e2ec !important;
  border-radius: 8px !important;
  background: #ffffff !important;
  box-sizing: border-box !important;
}
#workspace-row {
  width: 100% !important;
  flex: 1 1 auto !important;
  min-height: 0 !important;
  height: 0 !important;
  margin: 0 !important;
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: stretch !important;
  gap: 16px !important;
  box-sizing: border-box !important;
}
#input-panel,
#main-panel,
#step-nav,
#subpage-frame,
.summary-card,
.activity-panel,
.recommendation-card,
.primary-note {
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06) !important;
}
#input-panel,
#main-panel {
  height: 100% !important;
  max-height: 100% !important;
  min-height: 0 !important;
  box-sizing: border-box !important;
}
#input-panel {
  flex: 0 0 240px !important;
  width: 240px !important;
  min-width: 240px !important;
  max-width: 240px !important;
  overflow-y: auto !important;
  overflow-x: hidden !important;
}
#main-panel {
  flex: 1 1 0 !important;
  min-width: 0 !important;
  max-width: none !important;
  height: 100% !important;
  max-height: 100% !important;
  overflow: hidden !important;
  display: flex !important;
  flex-direction: column !important;
}
#step-nav {
  flex: 0 0 auto !important;
  width: 100% !important;
  background: #ffffff !important;
  padding: 8px !important;
  margin: 0 0 12px 0 !important;
}
#subpage-frame {
  flex: 1 1 auto !important;
  width: 100% !important;
  height: 0 !important;
  max-height: 100% !important;
  min-height: 0 !important;
  overflow-y: auto !important;
  overflow-x: hidden !important;
  -webkit-overflow-scrolling: touch !important;
}
#parse-page,
#recommend-page,
#export-page {
  min-height: 100% !important;
}
@media (max-width: 760px) {
  .gradio-container {
    width: 100vw !important;
    max-width: 100vw !important;
    height: auto !important;
    min-height: 100vh !important;
    margin: 0 auto !important;
    padding: 8px !important;
    overflow: visible !important;
  }
  #workspace-row {
    flex-wrap: wrap !important;
  }
  #input-panel,
  #main-panel {
    flex: 1 1 100% !important;
    width: 100% !important;
    min-width: 0 !important;
    max-width: none !important;
    height: auto !important;
  }
}
"""


CSS = """
:root {
  --app-pad-x: 14px;
  --app-pad-y: 10px;
  --header-h: 154px;
  --panel-gap: 8px;
  --column-gap: 16px;
  --input-panel-w: 240px;
  --assistant-panel-w: 330px;
  --input-panel-pad: 14px;
  --border: #d9e2ec;
  --paper: #ffffff;
  --page: #f5f7fa;
  --teal: #0f766e;
  --teal-soft: #ecfdf5;
  --shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}

html,
body,
gradio-app {
  width: 100%;
  height: 100%;
  margin: 0 !important;
  background: var(--page) !important;
  overflow: hidden !important;
}

.gradio-container {
  width: 100vw !important;
  max-width: 100vw !important;
  height: 100vh !important;
  height: 100dvh !important;
  max-height: 100vh !important;
  max-height: 100dvh !important;
  margin: 0 !important;
  padding: 0 !important;
  background: var(--page) !important;
  overflow: hidden !important;
  box-sizing: border-box !important;
}

#app-header {
  position: fixed !important;
  top: var(--app-pad-y) !important;
  left: var(--app-pad-x) !important;
  right: var(--app-pad-x) !important;
  height: var(--header-h) !important;
  z-index: 20 !important;
  box-sizing: border-box !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  background: var(--paper) !important;
  padding: 18px 28px !important;
  box-shadow: var(--shadow) !important;
  overflow: hidden !important;
}

#app-header h1 {
  margin: 0 0 8px 0;
  color: #0f172a;
  font-size: 31px;
  line-height: 1.15;
  letter-spacing: 0;
}

#app-header p {
  margin: 0;
  color: #475569;
  font-size: 16px;
}

.status-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.status-pill {
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  padding: 5px 10px;
  background: #ffffff;
  color: #334155;
  font-size: 13px;
}

.status-pill.ready {
  border-color: #99f6e4;
  background: #ecfdf5;
  color: #0f766e;
}

.status-pill.warn {
  border-color: #fed7aa;
  background: #fff7ed;
  color: #b45309;
}

#workspace-row {
  position: fixed !important;
  left: var(--app-pad-x) !important;
  right: var(--app-pad-x) !important;
  top: calc(var(--app-pad-y) + var(--header-h) + var(--panel-gap)) !important;
  bottom: var(--app-pad-y) !important;
  width: auto !important;
  height: auto !important;
  min-height: 0 !important;
  margin: 0 !important;
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: stretch !important;
  gap: var(--column-gap) !important;
  overflow: hidden !important;
  box-sizing: border-box !important;
}

#input-panel,
#main-panel,
#assistant-panel {
  height: 100% !important;
  min-height: 0 !important;
  box-sizing: border-box !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  background: var(--paper) !important;
  padding: 14px !important;
  box-shadow: var(--shadow) !important;
}

#input-panel {
  flex: 0 0 var(--input-panel-w) !important;
  width: var(--input-panel-w) !important;
  min-width: var(--input-panel-w) !important;
  max-width: var(--input-panel-w) !important;
  padding: var(--input-panel-pad) !important;
  display: grid !important;
  grid-template-rows: max-content max-content max-content !important;
  align-content: start !important;
  gap: 8px !important;
  overflow-y: auto !important;
  overflow-x: hidden !important;
}

#input-panel > .block,
#input-panel > .form {
  position: relative !important;
  flex: 0 0 auto !important;
  min-height: 0 !important;
  margin: 0 !important;
}

#input-panel > .block:nth-of-type(1) {
  grid-row: 1 !important;
  height: auto !important;
}

#input-panel > .block:has(button.boundedheight),
#input-panel > .block:nth-of-type(2) {
  grid-row: 2 !important;
  height: auto !important;
  min-height: 202px !important;
  overflow: visible !important;
}

#input-panel > .block:has(button.boundedheight) button,
#input-panel > .block:nth-of-type(2) button {
  min-height: 54px !important;
  height: 54px !important;
}

#case-upload {
  height: auto !important;
  min-height: 202px !important;
  width: 100% !important;
  max-width: 100% !important;
  display: grid !important;
  grid-template-rows: auto auto auto !important;
  row-gap: 6px !important;
  align-items: start !important;
  overflow: visible !important;
  box-sizing: border-box !important;
}

#case-upload > label {
  position: static !important;
  display: inline-flex !important;
  width: fit-content !important;
  min-height: 0 !important;
  height: auto !important;
  margin: 0 0 6px 0 !important;
  z-index: auto !important;
}

#case-upload > button.boundedheight,
#case-upload > button.center {
  min-height: 142px !important;
  height: 142px !important;
}

#input-panel #case-upload > button.boundedheight,
#input-panel #case-upload > button.center {
  min-height: 142px !important;
  height: 142px !important;
}

#case-upload > button.boundedheight,
#case-upload > button.center.boundedheight {
  width: 100% !important;
  border: 1px solid #99f6e4 !important;
  border-radius: 8px !important;
  background: #f8fffd !important;
  color: transparent !important;
  font-size: 0 !important;
  box-shadow: none !important;
}

#case-upload > button.boundedheight > .wrap,
#case-upload > button.center.boundedheight > .wrap {
  position: static !important;
  width: 100% !important;
  height: 100% !important;
  min-height: 0 !important;
  max-height: none !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 6px !important;
  color: transparent !important;
  font-size: 0 !important;
  overflow: hidden !important;
}

#case-upload > button.boundedheight > .wrap::before,
#case-upload > button.center.boundedheight > .wrap::before {
  content: "⇧";
  display: block;
  color: #14b8a6;
  font-size: 25px;
  font-weight: 800;
  line-height: 1;
}

#case-upload > button.boundedheight .or,
#case-upload > button.center.boundedheight .or {
  display: none !important;
}

#case-upload > button.boundedheight .icon-wrap,
#case-upload > button.center.boundedheight .icon-wrap {
  display: none !important;
  width: 18px !important;
  height: 18px !important;
  margin: 0 !important;
  color: #14b8a6 !important;
}

#case-upload > button.boundedheight .icon-wrap svg,
#case-upload > button.center.boundedheight .icon-wrap svg {
  width: 18px !important;
  height: 18px !important;
}

#case-upload > button.boundedheight > .wrap::after,
#case-upload > button.center.boundedheight > .wrap::after {
  content: "点击上传";
  display: block;
  color: #0f766e;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.2;
}

#case-upload .file-preview,
#case-upload .file-preview-holder,
#case-upload [data-testid="file-preview"] {
  grid-row: 2 !important;
  width: calc(var(--input-panel-w) - (var(--input-panel-pad) * 2)) !important;
  min-width: 0 !important;
  max-width: calc(var(--input-panel-w) - (var(--input-panel-pad) * 2)) !important;
  max-height: none !important;
  justify-self: stretch !important;
  box-sizing: border-box !important;
  overflow: visible !important;
}

#case-upload .file-preview {
  display: block !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 8px !important;
  background: #ffffff !important;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04) !important;
}

#case-upload .file-preview tr.file {
  width: 100% !important;
  min-height: 44px !important;
  display: flex !important;
  align-items: center !important;
  padding: 0 10px !important;
  box-sizing: border-box !important;
}

#case-upload .file-preview .filename {
  flex: 1 1 100% !important;
  min-width: 0 !important;
  max-width: 100% !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
}

#case-upload .file-preview .download {
  display: none !important;
}

#filename-compactor-hook {
  display: none !important;
}

#case-upload > .icon-button-wrapper {
  position: static !important;
  grid-row: 3 !important;
  width: calc(var(--input-panel-w) - (var(--input-panel-pad) * 2)) !important;
  min-width: 0 !important;
  max-width: calc(var(--input-panel-w) - (var(--input-panel-pad) * 2)) !important;
  height: auto !important;
  min-height: 40px !important;
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
  gap: 10px !important;
  padding: 0 !important;
  margin: 4px 0 0 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

#case-upload .file-preview button,
#case-upload [data-testid="file-preview"] button,
#case-upload > .icon-button-wrapper > button {
  position: static !important;
  width: 38px !important;
  height: 38px !important;
  min-height: 38px !important;
  margin: 0 !important;
  border-radius: 8px !important;
  border: 1px solid #ccfbf1 !important;
  background: #f8fffd !important;
  color: #0f766e !important;
  box-shadow: none !important;
}

#input-panel #case-upload > .icon-button-wrapper button {
  width: 38px !important;
  height: 38px !important;
  min-width: 38px !important;
  min-height: 38px !important;
  max-width: 38px !important;
  max-height: 38px !important;
  padding: 0 !important;
  flex: 0 0 38px !important;
}

#input-panel > .form {
  grid-row: 3 !important;
  height: max-content !important;
  min-height: max-content !important;
  overflow: visible !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 8px !important;
}

#input-panel > .form > .block {
  flex: 0 0 auto !important;
  margin: 0 !important;
  min-height: 0 !important;
}

#input-panel > .form > .block.padded {
  padding: 8px 10px !important;
}

#main-panel {
  flex: 1 1 0 !important;
  min-width: 0 !important;
  max-width: none !important;
  overflow: hidden !important;
  display: flex !important;
  flex-direction: column !important;
}

#assistant-panel {
  flex: 0 0 var(--assistant-panel-w) !important;
  width: var(--assistant-panel-w) !important;
  min-width: 300px !important;
  max-width: var(--assistant-panel-w) !important;
  overflow: hidden !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 10px !important;
}

#assistant-panel > .block,
#assistant-panel > .form,
#assistant-panel > .gap {
  flex: 0 0 auto !important;
  min-height: 0 !important;
  margin: 0 !important;
}

#assistant-panel > #assistant-chatbot,
#assistant-panel #assistant-chatbot {
  flex: 1 1 0 !important;
}

.assistant-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #0f172a;
  font-size: 16px;
  font-weight: 800;
}

.assistant-model {
  border: 1px solid #ccfbf1;
  border-radius: 999px;
  padding: 3px 8px;
  background: #ecfdf5;
  color: var(--teal);
  font-size: 12px;
  font-weight: 700;
}

#assistant-chat-view {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  overflow: hidden !important;
}

#assistant-chatbot {
  flex: 1 1 0 !important;
  min-height: 280px !important;
  height: auto !important;
  overflow: hidden !important;
}

#assistant-chatbot,
#assistant-chatbot > div,
#assistant-chatbot .wrap,
#assistant-chatbot .bubble-wrap,
#assistant-chatbot .message-wrap {
  box-sizing: border-box !important;
}

#assistant-chatbot button {
  display: none !important;
}

#assistant-chatbot [data-testid="bot"],
#assistant-chatbot .bot,
#assistant-chatbot .message.bot {
  justify-content: flex-start !important;
}

#assistant-chatbot [data-testid="user"],
#assistant-chatbot .user,
#assistant-chatbot .message.user {
  justify-content: flex-end !important;
}

#assistant-chat-view,
#assistant-chat-view .html-container,
#assistant-chat-view .prose {
  height: 100% !important;
}

.med-chat {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  padding: 2px 2px 4px;
  box-sizing: border-box;
}

.chat-bubble-row {
  display: flex;
  width: 100%;
}

.chat-bubble-row.user {
  justify-content: flex-end;
}

.chat-bubble-row.assistant {
  justify-content: flex-start;
}

.chat-bubble {
  max-width: 86%;
  border-radius: 8px;
  padding: 9px 11px;
  line-height: 1.55;
  font-size: 14px;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.chat-bubble-row.user .chat-bubble {
  background: var(--teal);
  color: #ffffff;
}

.chat-bubble-row.assistant .chat-bubble {
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #1e293b;
}

.chat-role {
  margin-bottom: 3px;
  color: inherit;
  font-size: 12px;
  font-weight: 800;
  opacity: 0.72;
}

.assistant-disclaimer {
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
  text-align: center;
}

#assistant-input {
  flex: 0 0 auto !important;
}

#assistant-input textarea {
  min-height: 68px !important;
  max-height: 116px !important;
  resize: none !important;
}

#assistant-actions {
  flex: 0 0 auto !important;
  gap: 8px !important;
}

#assistant-actions button,
#assistant-send-btn {
  min-height: 38px !important;
  border-radius: 8px !important;
  font-weight: 800 !important;
}

.assistant-secondary-btn,
.assistant-secondary-btn button {
  border: 1px solid #cbd5e1 !important;
  background: #ffffff !important;
  color: #334155 !important;
  box-shadow: none !important;
}

#step-nav {
  flex: 0 0 auto !important;
  width: 100% !important;
  min-height: 58px !important;
  margin: 0 0 12px 0 !important;
  padding: 8px 18px !important;
  box-sizing: border-box !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  background: var(--paper) !important;
  box-shadow: var(--shadow) !important;
}

#step-timeline {
  width: 100% !important;
  margin: 0 !important;
}

#step-timeline,
#step-timeline fieldset,
#step-timeline .wrap,
#step-timeline .container {
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
}

#step-timeline .wrap {
  overflow: visible !important;
}

#step-timeline [role="radiogroup"],
#step-timeline .radio-group,
#step-timeline > .wrap:not(.default) {
  position: relative !important;
  display: grid !important;
  grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
  align-items: end !important;
  gap: 0 !important;
  min-height: 42px !important;
}

#step-timeline [role="radiogroup"]::before,
#step-timeline .radio-group::before,
#step-timeline > .wrap:not(.default)::before {
  content: none !important;
  display: none !important;
}

#step-timeline label {
  position: relative !important;
  z-index: 1 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-height: 42px !important;
  width: 100% !important;
  margin: 0 !important;
  padding: 0 34px 9px !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  color: #64748b !important;
  box-shadow: none !important;
  font-size: 15px !important;
  font-weight: 700 !important;
  cursor: pointer !important;
}

#step-timeline label::before {
  content: "→";
  position: absolute;
  top: 10px;
  right: -12px;
  width: auto;
  height: auto;
  transform: none;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: #94a3b8;
  font-size: 22px;
  font-weight: 800;
  line-height: 1;
}

#step-timeline label:last-of-type::before {
  content: none !important;
  display: none !important;
}

#step-timeline input[type="radio"] {
  position: absolute !important;
  opacity: 0 !important;
  width: 0 !important;
  height: 0 !important;
  margin: 0 !important;
  pointer-events: none !important;
}

#step-timeline label.selected,
#step-timeline label:has(input[type="radio"]:checked) {
  color: var(--teal) !important;
}

#step-timeline label.selected::before,
#step-timeline label:has(input[type="radio"]:checked)::before {
  background: transparent !important;
  border-color: transparent !important;
  color: #94a3b8 !important;
}

#step-timeline label.selected::after,
#step-timeline label:has(input[type="radio"]:checked)::after {
  content: "";
  position: absolute;
  left: 20%;
  right: 20%;
  bottom: 0;
  height: 3px;
  border-radius: 999px;
  background: var(--teal);
}

button.primary,
button.action-button {
  background: var(--teal) !important;
  border-color: var(--teal) !important;
  color: #ffffff !important;
  font-weight: 800 !important;
}

#parse-action-btn,
#recommend-action-btn,
#parse-action-btn button,
#recommend-action-btn button {
  width: 100% !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
}

#parse-action-btn:disabled,
#recommend-action-btn:disabled,
#parse-action-btn button:disabled,
#recommend-action-btn button:disabled {
  background: #94a3b8 !important;
  background-color: #94a3b8 !important;
  border-color: #94a3b8 !important;
  color: #f8fafc !important;
  cursor: not-allowed !important;
  opacity: 0.82 !important;
  filter: saturate(0.25) brightness(1.08) !important;
  box-shadow: inset 0 0 0 999px rgba(148, 163, 184, 0.82) !important;
}

button#parse-action-btn.primary:disabled,
button#recommend-action-btn.primary:disabled,
button#parse-action-btn.primary[disabled],
button#recommend-action-btn.primary[disabled] {
  background: #94a3b8 !important;
  background-color: #94a3b8 !important;
  border-color: #94a3b8 !important;
  color: #f8fafc !important;
  filter: saturate(0.25) brightness(1.08) !important;
  box-shadow: inset 0 0 0 999px rgba(148, 163, 184, 0.82) !important;
}

#parse-action-btn:disabled::after,
#recommend-action-btn:disabled::after,
#parse-action-btn button:disabled::after,
#recommend-action-btn button:disabled::after {
  content: "";
  width: 15px;
  height: 15px;
  margin-left: 10px;
  border: 2px solid rgba(248, 250, 252, 0.5);
  border-top-color: #ffffff;
  border-radius: 999px;
  animation: action-spin 0.8s linear infinite;
}

@keyframes action-spin {
  to {
    transform: rotate(360deg);
  }
}

#subpage-frame {
  flex: 1 1 auto !important;
  width: 100% !important;
  height: 0 !important;
  min-height: 0 !important;
  box-sizing: border-box !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  background: var(--paper) !important;
  padding: 14px !important;
  overflow-y: auto !important;
  overflow-x: hidden !important;
  box-shadow: var(--shadow) !important;
  -webkit-overflow-scrolling: touch !important;
}

#parse-page,
#recommend-page,
#export-page {
  min-height: 100% !important;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 0 10px 0;
  color: #0f172a;
  font-size: 16px;
  font-weight: 800;
}

.primary-note {
  border: 1px solid #d8e0e8;
  border-left: 4px solid var(--teal);
  background: #ffffff;
  padding: 10px 12px;
  border-radius: 8px;
  color: #334155;
  line-height: 1.65;
  box-shadow: var(--shadow);
}

.summary-card {
  border: 1px solid #d8e0e8;
  border-radius: 8px;
  background: #ffffff;
  padding: 12px;
  color: #334155;
  box-shadow: var(--shadow);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 10px 0;
}

.summary-item {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  padding: 8px 10px;
  min-height: 54px;
}

.summary-label {
  display: block;
  color: #64748b;
  font-size: 12px;
  margin-bottom: 2px;
}

.summary-value {
  color: #0f172a;
  font-weight: 700;
  line-height: 1.4;
}

.summary-list {
  margin: 8px 0 0 0;
  padding-left: 18px;
  color: #334155;
  line-height: 1.55;
}

.activity-panel {
  border: 1px solid #d8e0e8;
  border-radius: 8px;
  background: #f8fafc;
  padding: 10px 12px;
  color: #334155;
  line-height: 1.55;
  box-shadow: var(--shadow);
}

.activity-panel h3 {
  margin: 0 0 6px 0;
  font-size: 15px;
  color: #0f172a;
}

.activity-panel ul {
  margin: 0;
  padding-left: 18px;
}

.activity-panel li {
  margin: 3px 0;
}

.recommendation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 12px;
}

.recommendation-card {
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: #ffffff;
  padding: 14px;
  min-height: 230px;
  box-shadow: var(--shadow);
}

#recommend-page .recommendation-card,
#recommend-page .recommendation-card *,
#recommend-page .footer-disclaimer,
.recommendation-card,
.recommendation-card *,
.footer-disclaimer {
  color: #000000 !important;
  opacity: 1 !important;
}

.rec-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.rec-title h3 {
  margin: 0;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.3;
}

.score-badge {
  flex: 0 0 auto;
  border-radius: 999px;
  padding: 4px 9px;
  background: #e0f2fe;
  color: #075985;
  font-weight: 700;
  font-size: 13px;
}

.rec-meta {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 6px 8px;
  color: #334155;
  font-size: 14px;
  margin: 8px 0;
}

.rec-meta b {
  color: #64748b;
  font-weight: 600;
}

.rec-reasons {
  margin: 10px 0 0 0;
  padding-left: 18px;
  color: #334155;
  font-size: 14px;
}

.rec-links a,
.rec-links a:visited,
.rec-links a:hover,
.rec-links a:active {
  color: #2563eb !important;
  text-decoration: none;
  font-weight: 600;
}

.footer-disclaimer {
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 760px) {
  :root {
    --app-pad-x: 8px;
    --app-pad-y: 8px;
    --header-h: 172px;
  }
  #workspace-row {
    flex-direction: column !important;
    overflow-y: auto !important;
  }
  #input-panel,
  #main-panel,
  #assistant-panel {
    width: 100% !important;
    max-width: none !important;
    flex: 0 0 auto !important;
    height: auto !important;
    min-height: 0 !important;
  }
  #main-panel {
    min-height: 640px !important;
  }
  #assistant-panel {
    min-width: 0 !important;
    min-height: 520px !important;
  }
  .summary-grid,
  .recommendation-grid {
    grid-template-columns: 1fr;
  }
}
"""


APP_JS = r"""
(() => {
  const start = () => {
    if (window.__medicalDemoFilenameCompactorStarted) return;
    if (!document.body) {
      window.setTimeout(start, 50);
      return;
    }
    window.__medicalDemoFilenameCompactorStarted = true;

  const compactFileName = (name) => {
    const cleaned = (name || "").replace(/\s+/g, "").trim();
    if (!cleaned) return cleaned;
    const dotIndex = cleaned.lastIndexOf(".");
    const base = dotIndex > 0 ? cleaned.slice(0, dotIndex) : cleaned;
    const ext = dotIndex > 0 ? cleaned.slice(dotIndex) : "";
    const chars = Array.from(base);
    if (chars.length <= 6) return cleaned;
    return `${chars.slice(0, 6).join("")}…${ext}`;
  };

  const updateUploadNames = () => {
    document.querySelectorAll("#case-upload .file-preview .filename").forEach((node) => {
      const displayed = (node.textContent || "").trim();
      const stored = node.dataset.fullName || "";
      const storedVisible = compactFileName(stored);
      const source = stored && displayed === storedVisible ? stored : displayed;
      if (!source) return;
      const visible = compactFileName(source);
      node.dataset.fullName = source;
      node.title = source.replace(/\s+/g, "").trim();
      if (displayed !== visible) node.textContent = visible;
    });
  };

  const scrollAssistantChat = () => {
    document.querySelectorAll("#assistant-chat-view .med-chat").forEach((node) => {
      node.scrollTop = node.scrollHeight;
    });
  };

  updateUploadNames();
  scrollAssistantChat();
  new MutationObserver(() => {
    updateUploadNames();
    scrollAssistantChat();
  }).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
"""

def header_html() -> str:
    statuses = CONFIG.key_status()
    pills = []
    for name, value in statuses.items():
        cls = "ready" if "已配置" in value and not value.startswith("未配置") else "warn"
        pills.append(f'<span class="status-pill {cls}">{html.escape(name)}：{html.escape(value)}</span>')
    return f"""
    <div id="app-header">
      <h1>就医资源推荐系统</h1>
      <p>使用流程：上传病历资料 → 解析栏 → 推荐栏 → 报告栏</p>
      <div class="status-grid">{''.join(pills)}</div>
    </div>
    """


def normalize_file_paths(files: Any) -> list[str]:
    if not files:
        return []
    if isinstance(files, (str, Path)):
        return [str(files)]
    paths = []
    for item in files:
        if isinstance(item, (str, Path)):
            paths.append(str(item))
        elif hasattr(item, "name"):
            paths.append(str(item.name))
        elif isinstance(item, dict) and item.get("path"):
            paths.append(str(item["path"]))
    return paths


def parse_records(
    files: Any,
    k: int,
    city: str,
    area: str,
    hospital_level: str,
    require_doctor: bool,
    progress: gr.Progress = gr.Progress(track_tqdm=True),
) -> tuple[pd.DataFrame, str, str, pd.DataFrame, str]:
    file_paths = normalize_file_paths(files)
    if not file_paths:
        empty_profile = PatientProfile()
        return (
            pd.DataFrame(),
            empty_profile.to_json_text(),
            "",
            pd.DataFrame(),
            render_activity("解析状态", ["请先上传 PDF 或图片资料。"]),
        )

    parse_mode = (CONFIG.medical_record_parse_mode or "qwen_ocr").strip().lower()
    mode_name = "快速文字识别" if parse_mode in {"qwen_ocr", "ocr", "qwen-vl-ocr"} else "视觉结构化解析"
    profile, doc_rows, log = extract_medical_profile(
        file_paths=file_paths,
        config=CONFIG,
        max_pages_per_file=0,
        progress=progress,
    )
    profile.patient_need.k = int(k)
    profile.patient_need.preferred_city = city or CONFIG.default_city
    profile.patient_need.preferred_area = (area or "").strip()
    profile.patient_need.hospital_level = hospital_level
    profile.patient_need.require_doctor_evidence = bool(require_doctor)

    if not profile.department_candidates:
        profile.department_candidates = infer_departments(profile)
    urgency, flags = infer_urgency(profile)
    profile.urgency_level = urgency
    for flag in flags:
        if flag not in profile.risk_flags:
            profile.risk_flags.append(flag)

    summary = build_patient_summary(profile)
    dept_rows = [
        {
            "推荐科室": item.department,
            "置信度": item.confidence,
            "依据": item.reason,
        }
        for item in profile.department_candidates
    ]
    return (
        pd.DataFrame(doc_rows),
        profile.to_json_text(),
        summary,
        pd.DataFrame(dept_rows),
        render_activity("解析完成", [f"解析方式：{mode_name}"] + (log.splitlines()[-9:] or ["已完成资料读取和结构化整理。"])),
    )


def run_recommendation(
    profile_text: str,
    k: int,
    city: str,
    area: str,
    hospital_level: str,
    require_doctor: bool,
    assistant_provider: str,
) -> Any:
    try:
        profile = parse_profile_json(profile_text)
    except Exception as exc:
        yield (
            render_notice(f"患者信息读取失败：{exc}", level="warn"),
            render_notice("推荐未执行。", level="warn"),
            [],
        )
        return

    if not profile.department_candidates:
        profile.department_candidates = infer_departments(profile)

    log_lines: list[str] = []
    event_queue: queue.Queue[str] = queue.Queue()
    result: dict[str, Any] = {}

    def add_log(message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        event_queue.put(f"[{stamp}] {message}")

    def worker() -> None:
        try:
            recommendations, hospitals, log = recommend_resources(
                profile=profile,
                config=CONFIG,
                k=int(k),
                city=city or CONFIG.default_city,
                area=(area or "").strip(),
                hospital_level=hospital_level,
                require_doctor_evidence=bool(require_doctor),
                provider=normalize_assistant_provider_choice(assistant_provider),
                log_callback=add_log,
            )
            result["recommendations"] = recommendations
            result["hospitals"] = hospitals
            result["log"] = log
        except Exception as exc:
            result["error"] = str(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    yield (
        render_notice("正在生成推荐：系统已开始调用 AI 联网助手搜索医院-科室-医生。"),
        render_activity("推荐状态", ["推荐任务已启动。"]),
        [],
    )

    while thread.is_alive() or not event_queue.empty():
        updated = False
        while not event_queue.empty():
            log_lines.append(event_queue.get())
            updated = True
        if updated:
            yield (
                render_notice("正在生成推荐：请稍候，系统正在完成 AI 联网搜索、官网来源核验和地图核验。"),
                render_activity("推荐状态", log_lines[-8:]),
                [],
            )
        time.sleep(0.25)

    if result.get("error"):
        log_lines.append(f"[{time.strftime('%H:%M:%S')}] 推荐执行失败：{result['error']}")
        yield (
            render_notice(f"推荐执行失败：{result['error']}", level="warn"),
            render_activity("推荐状态", log_lines[-8:]),
            [],
        )
        return

    recommendations = result.get("recommendations", [])
    hospitals = result.get("hospitals", [])
    final_log = result.get("log", "")
    rec_state = [rec.model_dump() for rec in recommendations]
    if final_log:
        log_lines.append("--- 汇总 ---")
        log_lines.extend(final_log.splitlines())
    log_lines.append(f"候选医院：{len(hospitals)} 家。")
    requested_k = int(k)
    if len(recommendations) < requested_k:
        finish_message = (
            f"推荐完成：已按固定条件筛选（推荐数量不少于 {requested_k}、医院等级 {hospital_level}、"
            f"有确切来源（医院官网）优先 {'是' if require_doctor else '否'}），当前可用候选为 {len(recommendations)} 个。"
        )
    else:
        finish_message = (
            f"推荐完成：已生成 {len(recommendations)} 个推荐结果（不少于目标 {requested_k}），可继续导出报告。"
        )
    yield (
        render_recommendations(recommendations),
        render_notice(finish_message),
        rec_state,
    )


def export_current_report(profile_text: str, rec_state: list[dict[str, Any]]) -> tuple[list[str], str]:
    if not rec_state:
        return [], render_notice("暂无推荐结果可导出。", level="warn")
    try:
        profile = parse_profile_json(profile_text)
        recommendations = [Recommendation.model_validate(item) for item in rec_state]
    except Exception as exc:
        return [], render_notice(f"导出失败：{exc}", level="warn")
    files, message = export_reports(profile, recommendations, CONFIG)
    return files, render_notice(message)


def initial_assistant_history() -> list[dict[str, str]]:
    return [{"role": "assistant", "content": ASSISTANT_WELCOME}]


def normalize_assistant_history(history: Any) -> list[dict[str, str]]:
    if not isinstance(history, list):
        return initial_assistant_history()

    normalized: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = "user" if item.get("role") == "user" else "assistant"
        content = str(item.get("content", "")).strip()
        if content:
            normalized.append({"role": role, "content": content})
    return normalized or initial_assistant_history()


def render_assistant_chat(history: Any) -> str:
    rows = []
    for item in normalize_assistant_history(history):
        role = "user" if item.get("role") == "user" else "assistant"
        label = "我" if role == "user" else "AI助手"
        content = format_chat_text(item.get("content", ""))
        rows.append(
            f"""
            <div class="chat-bubble-row {role}">
              <div class="chat-bubble">
                <div class="chat-role">{label}</div>
                <div>{content}</div>
              </div>
            </div>
            """
        )
    return f"""
    <div class="med-chat">
      {''.join(rows)}
      <div class="assistant-disclaimer">AI 回复仅供就医参考，不能替代医生诊断或急救判断。</div>
    </div>
    """


def format_chat_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return html.escape(text).replace("\n", "<br>")


def parse_profile_for_assistant(profile_text: str) -> PatientProfile | None:
    try:
        profile = parse_profile_json(profile_text)
    except Exception:
        return None
    if not profile_has_context(profile):
        return None
    return profile


def profile_has_context(profile: PatientProfile) -> bool:
    return any(
        [
            profile.patient_basic.name,
            profile.chief_complaint,
            profile.present_illness,
            profile.current_symptoms,
            profile.exam_results,
            profile.suspected_diagnoses,
            profile.department_candidates,
            profile.risk_flags,
            profile.source_files,
            profile.raw_document_text,
        ]
    )


def recommendations_from_state(rec_state: Any) -> list[Recommendation]:
    if not isinstance(rec_state, list):
        return []

    recommendations: list[Recommendation] = []
    for item in rec_state:
        try:
            recommendations.append(Recommendation.model_validate(item))
        except Exception:
            continue
    return recommendations


def is_nearby_intent(message: str) -> bool:
    compact = re.sub(r"\s+", "", message or "")
    return any(word in compact for word in NEARBY_INTENT_WORDS)


def is_recommendation_intent(message: str) -> bool:
    compact = re.sub(r"\s+", "", message or "")
    if is_nearby_intent(compact):
        return True
    if any(word in compact for word in RECOMMENDATION_INTENT_WORDS):
        return True
    return "医院" in compact and ("推荐" in compact or "找" in compact)


def extract_area_from_message(message: str) -> str:
    compact = re.sub(r"\s+", "", message or "")
    for alias, area in COMMON_AREA_ALIASES.items():
        if alias in compact:
            return area

    matches = re.findall(r"([\u4e00-\u9fa5]{2,12}(?:区|县|镇|乡|街道))", compact)
    for match in matches:
        area = match
        for city_name in CITY_CHOICES:
            if area.startswith(city_name) and len(area) > len(city_name):
                area = area[len(city_name) :]
                break
        if area and area not in CITY_CHOICES:
            return area
    return ""


def clamp_recommendation_count(k: Any, message: str) -> int:
    try:
        count = int(float(k))
    except Exception:
        count = 6
    return max(1, min(10, count))


def fallback_assistant_reply(
    user_message: str,
    action_context: str,
    recommendations: list[Recommendation],
    error: Exception | None = None,
) -> str:
    if action_context:
        lines = [action_context]
        if recommendations:
            top = recommendations[0]
            lines.append(f"当前优先可考虑：{top.hospital}，{top.department}，地址：{top.address or '待确认'}。")
            lines.append("请结合挂号可及性、交通和医生面诊意见最终决定。")
        if error:
            lines.append(f"AI助手回复暂时失败：{error}")
        return "\n".join(lines)
    if error:
        return f"AI助手暂时响应失败：{error}"
    return "我已收到，请再补充一点症状、检查结果或就医位置，我会继续帮您分析。"


def build_profile_resume_for_assistant(profile: PatientProfile) -> str:
    name = profile.patient_basic.name or "未识别"
    gender = profile.patient_basic.gender or "未识别"
    age = profile.patient_basic.age if profile.patient_basic.age is not None else "未识别"
    departments = "、".join(item.department for item in profile.department_candidates) or "待推断"
    symptoms = "、".join(profile.current_symptoms[:8]) or "未识别"
    diagnoses = "、".join(profile.suspected_diagnoses[:6]) or "待评估"
    risks = "、".join(profile.risk_flags[:6]) or "暂无明确危急信号"
    exams = []
    for item in profile.exam_results[:6]:
        label = item.item or EXAM_TYPE_LABELS.get(item.type, item.type) or "检查项目"
        abnormal = "（异常）" if item.abnormal else ""
        exams.append(f"{label}：{item.result[:80]}{abnormal}")
    exam_text = "；".join(exams) or "暂无关键检查摘录"
    return (
        "已加载当前患者资料：\n"
        f"- 基本信息：{name}，{gender}，{age}岁\n"
        f"- 主诉：{profile.chief_complaint or '未识别'}\n"
        f"- 病情摘要：{(profile.present_illness or '未识别')[:180]}\n"
        f"- 当前症状：{symptoms}\n"
        f"- 疑似问题：{diagnoses}\n"
        f"- 推荐科室：{departments}\n"
        f"- 风险提示：{risks}\n"
        f"- 关键检查：{exam_text}"
    )


def load_patient_profile_to_assistant(
    profile_text: str,
    history: Any,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    current_history = normalize_assistant_history(history)
    profile = parse_profile_for_assistant(profile_text)
    if not profile:
        message = "当前还没有可加载的患者资料。请先上传并解析病历资料。"
    else:
        message = build_profile_resume_for_assistant(profile)

    current_history = [
        item
        for item in current_history
        if not str(item.get("content", "")).startswith("已加载当前患者资料：")
    ]
    current_history.append({"role": "assistant", "content": message})
    current_history = current_history[-24:]
    return current_history, current_history


def handle_assistant_message(
    message: str,
    history: Any,
    profile_text: str,
    rec_state: list[dict[str, Any]],
    k: int,
    city: str,
    area: str,
    hospital_level: str,
    require_doctor: bool,
    assistant_provider: str,
) -> Any:
    prior_history = normalize_assistant_history(history)
    user_message = (message or "").strip()
    assistant_provider_key = normalize_assistant_provider_choice(assistant_provider)
    if not user_message:
        yield (
            prior_history,
            prior_history,
            message or "",
            gr.update(),
            gr.update(),
            rec_state or [],
            area or "",
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
        )
        return

    visible_history = prior_history + [{"role": "user", "content": user_message}]
    profile = parse_profile_for_assistant(profile_text)
    recommendations = recommendations_from_state(rec_state)
    effective_area = extract_area_from_message(user_message) or (area or "").strip()
    effective_city = city or CONFIG.default_city
    effective_k = clamp_recommendation_count(k, user_message)
    action_context = ""
    recommendation_cards_update: Any = gr.update()
    recommendation_status_update: Any = gr.update()
    updated_rec_state = rec_state or []
    parse_page_update: Any = gr.update()
    recommend_page_update: Any = gr.update()
    export_page_update: Any = gr.update()
    step_nav_update: Any = gr.update()

    if is_recommendation_intent(user_message):
        if not profile:
            action_context = "用户希望更新就医推荐，但当前还没有完成病历解析。请提示用户先上传并解析病例资料。"
        elif is_nearby_intent(user_message) and not effective_area:
            action_context = "用户希望寻找更近的医院，但当前没有区县、街道、地址或地标。请先询问用户所在位置。"
        else:
            parse_page_update, recommend_page_update, export_page_update = show_recommend_page()
            step_nav_update = gr.update(value="推荐栏")
            working_history = visible_history + [
                {"role": "assistant", "content": "我已开始重新推荐，推荐结果会直接显示在推荐栏。"}
            ]
            yield (
                working_history,
                working_history,
                "",
                render_notice("正在生成推荐：AI助手已直接调用推荐程序。"),
                render_activity("推荐状态", ["AI助手已触发推荐程序。"]),
                updated_rec_state,
                effective_area,
                parse_page_update,
                recommend_page_update,
                export_page_update,
                step_nav_update,
            )

            log_lines: list[str] = []
            event_queue: queue.Queue[str] = queue.Queue()
            result: dict[str, Any] = {}

            def add_log(message: str) -> None:
                stamp = time.strftime("%H:%M:%S")
                event_queue.put(f"[{stamp}] {message}")

            def worker() -> None:
                try:
                    recs, hospitals, log = recommend_resources(
                        profile=profile,
                        config=CONFIG,
                        k=effective_k,
                        city=effective_city,
                        area=effective_area,
                        hospital_level=hospital_level,
                        require_doctor_evidence=bool(require_doctor),
                        provider=assistant_provider_key,
                        log_callback=add_log,
                    )
                    result["recommendations"] = recs
                    result["hospitals"] = hospitals
                    result["log"] = log
                except Exception as exc:
                    result["error"] = str(exc)

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            while thread.is_alive() or not event_queue.empty():
                updated = False
                while not event_queue.empty():
                    log_lines.append(event_queue.get())
                    updated = True
                if updated:
                    yield (
                        working_history,
                        working_history,
                        "",
                        render_notice("正在生成推荐：AI 助手正在联网搜索、核验官网来源并更新推荐栏。"),
                        render_activity("推荐状态", log_lines[-8:]),
                        updated_rec_state,
                        effective_area,
                        parse_page_update,
                        recommend_page_update,
                        export_page_update,
                        step_nav_update,
                    )
                time.sleep(0.25)

            if result.get("error"):
                reply = f"重新推荐失败：{result['error']}"
                visible_history.append({"role": "assistant", "content": reply})
                yield (
                    visible_history,
                    visible_history,
                    "",
                    render_notice("推荐执行失败。", level="warn"),
                    render_activity("推荐状态", [*log_lines[-7:], reply]),
                    updated_rec_state,
                    effective_area,
                    parse_page_update,
                    recommend_page_update,
                    export_page_update,
                    step_nav_update,
                )
                return

            recommendations = result.get("recommendations", [])
            hospitals = result.get("hospitals", [])
            final_log = result.get("log", "")
            updated_rec_state = [rec.model_dump() for rec in recommendations]
            if final_log:
                log_lines.append("--- 汇总 ---")
                log_lines.extend(final_log.splitlines())
            log_lines.append(f"候选医院：{len(hospitals)} 家。")
            area_label = f"、区域：{effective_area}" if effective_area else ""
            strict_note = "，已按推荐数量下限、医院等级筛选，并对有医院官网来源的结果优先排序"
            count_note = (
                f"，当前可用候选为 {len(recommendations)} 个结果"
                if len(recommendations) < effective_k
                else f"，共 {len(recommendations)} 个结果"
            )
            reply = f"已重新推荐，结果已经显示在推荐栏：城市：{effective_city}{area_label}{strict_note}{count_note}。"
            visible_history.append({"role": "assistant", "content": reply})
            visible_history = visible_history[-24:]
            yield (
                visible_history,
                visible_history,
                "",
                render_recommendations(recommendations),
                render_notice(reply),
                updated_rec_state,
                effective_area,
                parse_page_update,
                recommend_page_update,
                export_page_update,
                step_nav_update,
            )
            return

    preference_context = {
        "city": effective_city,
        "area": effective_area,
        "hospital_level": hospital_level,
        "k": effective_k,
        "require_doctor_evidence": bool(require_doctor),
        "official_source_priority": bool(require_doctor),
    }
    try:
        reply = chat_with_medical_assistant(
            user_message=user_message,
            history=prior_history,
            config=CONFIG,
            profile=profile,
            recommendations=recommendations,
            preference_context=preference_context,
            action_context=action_context,
            provider=assistant_provider_key,
        )
    except Exception as exc:
        reply = fallback_assistant_reply(user_message, action_context, recommendations, exc)

    visible_history.append({"role": "assistant", "content": reply})
    visible_history = visible_history[-24:]
    yield (
        visible_history,
        visible_history,
        "",
        recommendation_cards_update,
        recommendation_status_update,
        updated_rec_state,
        effective_area,
        parse_page_update,
        recommend_page_update,
        export_page_update,
        step_nav_update,
    )


def clear_assistant_chat() -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
    history = initial_assistant_history()
    return history, history, ""


def build_patient_summary(profile: PatientProfile) -> str:
    exams = profile.exam_results[:8]
    dept = "、".join(item.department for item in profile.department_candidates) or "待推断"
    exam_lines = "".join(
        "<li>"
        f"{html.escape(item.item or EXAM_TYPE_LABELS.get(item.type, item.type) or '检查项目')}："
        f"{html.escape(item.result[:120])}"
        f"{'（异常）' if item.abnormal else ''}"
        "</li>"
        for item in exams
    )
    missing = "、".join(profile.missing_information) or "暂无明显缺失"
    risk = "、".join(profile.risk_flags) or "未识别到明确危急信号"
    name = profile.patient_basic.name or "未识别"
    gender = profile.patient_basic.gender or "未识别"
    age = str(profile.patient_basic.age or "未识别")
    illness_summary = profile.present_illness or "推理模型未能生成明确病情摘要。"
    urgency = URGENCY_LABELS.get(profile.urgency_level, profile.urgency_level or "待评估")
    return f"""
<div class="summary-card">
  <div class="section-title">患者摘要</div>
  <div class="summary-grid">
    <div class="summary-item"><span class="summary-label">姓名</span><span class="summary-value">{html.escape(name)}</span></div>
    <div class="summary-item"><span class="summary-label">性别</span><span class="summary-value">{html.escape(gender)}</span></div>
    <div class="summary-item"><span class="summary-label">年龄</span><span class="summary-value">{html.escape(age)}</span></div>
    <div class="summary-item"><span class="summary-label">推荐科室</span><span class="summary-value">{html.escape(dept)}</span></div>
    <div class="summary-item"><span class="summary-label">紧急程度</span><span class="summary-value">{html.escape(urgency)}</span></div>
    <div class="summary-item"><span class="summary-label">疑似问题</span><span class="summary-value">{html.escape('、'.join(profile.suspected_diagnoses) or '待评估')}</span></div>
  </div>
  <div><b>病情摘要：</b>{html.escape(illness_summary)}</div>
  <div><b>主诉：</b>{html.escape(profile.chief_complaint or '未识别')}</div>
  <div><b>既往史：</b>{html.escape('、'.join(profile.past_history) or '未识别')}</div>
  <div><b>风险提示：</b>{html.escape(risk)}</div>
  <div><b>缺失信息：</b>{html.escape(missing)}</div>
  <div style="margin-top:8px;"><b>关键检查摘录</b></div>
  <ul class="summary-list">{exam_lines or '<li>暂无可展示检查项。</li>'}</ul>
</div>
"""


def render_notice(message: str, level: str = "info") -> str:
    color = "#0f766e" if level == "info" else "#b45309"
    return f'<div class="primary-note" style="border-left-color:{color};">{html.escape(message)}</div>'


def render_activity(title: str, lines: list[str]) -> str:
    if not lines:
        lines = ["等待任务开始。"]
    items = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
    return f"""
    <div class="activity-panel">
      <h3>{html.escape(title)}</h3>
      <ul>{items}</ul>
    </div>
    """


def render_recommendations(recommendations: list[Recommendation]) -> str:
    if not recommendations:
        return render_notice("暂无推荐结果。", level="warn")
    cards = []
    for rec in recommendations:
        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in rec.reasons)
        evidence_parts = []
        if rec.official_source_urls:
            evidence_parts.extend(
                f'<a href="{html.escape(url)}" target="_blank">官网来源</a>' for url in rec.official_source_urls
            )
        other_urls = [url for url in rec.evidence_urls if url not in rec.official_source_urls]
        if other_urls:
            evidence_parts.extend(
                f'<a href="{html.escape(url)}" target="_blank">补充来源</a>' for url in other_urls
            )
        if evidence_parts:
            evidence = "　".join(evidence_parts)
        elif rec.doctor != "待人工确认":
            evidence = "AI直出医生，来源待确认"
        else:
            evidence = "医生/公开来源待人工确认"
        map_link = (
            f'<a href="{html.escape(rec.map_url)}" target="_blank">地图</a>' if rec.map_url else "待确认"
        )
        doctor = rec.doctor
        if rec.title:
            doctor = f"{doctor} / {rec.title}"
        cards.append(
            f"""
            <div class="recommendation-card">
              <div class="rec-title">
                <h3>{rec.rank}. {html.escape(rec.hospital)}</h3>
                <span class="score-badge">{rec.score}</span>
              </div>
              <div class="rec-meta">
                <b>科室</b><span>{html.escape(rec.department)}</span>
                <b>医生</b><span>{html.escape(doctor)}</span>
                <b>地址</b><span>{html.escape(rec.address or '待确认')}</span>
                <b>链接</b><span class="rec-links">{evidence}　{map_link}</span>
              </div>
              <ul class="rec-reasons">{reasons}</ul>
            </div>
            """
        )
    return f"""
    <div class="recommendation-grid">
      {''.join(cards)}
    </div>
    <p class="footer-disclaimer">推荐仅供就医资源选择参考，不能替代医生诊断、治疗建议或保险核保结论。</p>
    """


def show_subpage(page: str) -> tuple[Any, Any, Any]:
    return (
        gr.update(visible=page == "parse"),
        gr.update(visible=page == "recommend"),
        gr.update(visible=page == "export"),
    )


def show_parse_page() -> tuple[Any, Any, Any]:
    return show_subpage("parse")


def show_recommend_page() -> tuple[Any, Any, Any]:
    return show_subpage("recommend")


def show_export_page() -> tuple[Any, Any, Any]:
    return show_subpage("export")


def show_step_page(step: str) -> tuple[Any, Any, Any]:
    step_text = str(step)
    if "推荐" in step_text or step_text.startswith("2"):
        return show_recommend_page()
    if "报告" in step_text or step_text.startswith("3"):
        return show_export_page()
    return show_parse_page()


def disable_action_button() -> Any:
    return gr.update(interactive=False)


def enable_action_button() -> Any:
    return gr.update(interactive=True)


def normalize_assistant_provider_choice(value: Any) -> str:
    text = str(value or CONFIG.assistant_provider or "").strip().lower()
    if "deepseek" in text or "deep" in text:
        return "deepseek"
    if "qwen" in text or "千问" in text or "通义" in text or "联网" in text:
        return "qwen"
    return "qwen"


def default_assistant_provider_label() -> str:
    provider = normalize_assistant_provider_choice(CONFIG.assistant_provider)
    return ASSISTANT_PROVIDER_LABELS.get(provider, ASSISTANT_PROVIDER_LABELS["qwen"])


def build_app() -> gr.Blocks:
    with gr.Blocks(
        title="就医资源推荐系统",
        fill_width=True,
        fill_height=True,
    ) as demo:
        gr.HTML(header_html())
        gr.HTML(
            "",
            elem_id="filename-compactor-hook",
            js_on_load=APP_JS,
            container=False,
            padding=False,
        )
        profile_state = gr.State(PatientProfile().to_json_text())
        recommendation_state = gr.State([])
        assistant_history = gr.State(initial_assistant_history())
        area = gr.State("")

        default_city = CONFIG.default_city if CONFIG.default_city in CITY_CHOICES else "上海"

        with gr.Row(elem_id="workspace-row", equal_height=True):
            with gr.Column(scale=1, min_width=240, elem_id="input-panel"):
                gr.HTML('<div class="section-title">资料与偏好</div>')
                files = gr.File(
                    label="上传病例",
                    file_count="multiple",
                    file_types=[".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"],
                    type="filepath",
                    elem_id="case-upload",
                )
                k = gr.Slider(1, 10, value=6, step=1, label="推荐数量（不少于）")
                city = gr.Dropdown(
                    choices=CITY_CHOICES,
                    value=default_city,
                    allow_custom_value=True,
                    filterable=True,
                    label="就诊城市",
                )
                hospital_level = gr.Dropdown(
                    choices=["三级优先", "三级甲等优先", "专科医院优先", "不限"],
                    value="三级优先",
                    label="医院等级偏好",
                )
                require_doctor = gr.Checkbox(value=False, label="有确切来源（医院官网）优先")

            with gr.Column(scale=4, min_width=0, elem_id="main-panel"):
                with gr.Column(elem_id="step-nav"):
                    step_nav = gr.Radio(
                        choices=["解析栏", "推荐栏", "报告栏"],
                        value="解析栏",
                        show_label=False,
                        container=False,
                        elem_id="step-timeline",
                    )

                with gr.Column(elem_id="subpage-frame"):
                    with gr.Column(visible=True, elem_id="parse-page") as parse_page:
                        gr.HTML('<div class="section-title">病历资料解析</div>')
                        parse_btn = gr.Button(
                            "开始解析",
                            variant="primary",
                            elem_id="parse-action-btn",
                            elem_classes=["primary"],
                        )
                        parse_status = gr.HTML(render_activity("解析状态", ["等待上传资料并开始解析。"]))
                        summary = gr.HTML("")
                        with gr.Row(equal_height=True):
                            doc_table = gr.Dataframe(label="文件解析状态", wrap=True)
                            dept_table = gr.Dataframe(label="科室推断", wrap=True)

                    with gr.Column(visible=False, elem_id="recommend-page") as recommend_page:
                        gr.HTML('<div class="section-title">推荐生成</div>')
                        recommend_btn = gr.Button(
                            "生成推荐",
                            variant="primary",
                            elem_id="recommend-action-btn",
                            elem_classes=["primary"],
                        )
                        recommendation_status = gr.HTML(render_notice("完成解析后点击“生成推荐”。"))
                        recommendation_cards = gr.HTML(render_notice("等待推荐结果。"))

                    with gr.Column(visible=False, elem_id="export-page") as export_page:
                        gr.HTML('<div class="section-title">报告导出</div>')
                        export_btn = gr.Button("导出报告")
                        export_files = gr.File(label="导出文件", file_count="multiple")
                        export_status = gr.HTML(render_notice("生成推荐后可导出报告。"))
                        gr.Markdown(
                            "<span class='footer-disclaimer'>本工具只做就医资源推荐辅助，不替代医生诊断或治疗建议。</span>"
                        )

            with gr.Column(scale=1, min_width=300, elem_id="assistant-panel"):
                gr.HTML('<div class="assistant-title"><span>AI医疗助手</span><span class="assistant-model">Qwen联网</span></div>')
                assistant_provider = gr.State("qwen")
                assistant_chat = gr.Chatbot(
                    value=initial_assistant_history(),
                    show_label=False,
                    layout="bubble",
                    height="100%",
                    min_height=280,
                    autoscroll=True,
                    buttons=[],
                    feedback_options=None,
                    elem_id="assistant-chatbot",
                )
                assistant_input = gr.Textbox(
                    label="",
                    placeholder="输入问题，例如：帮我重新推荐，或找一个近点的医院",
                    show_label=False,
                    lines=2,
                    max_lines=4,
                    autofocus=False,
                    elem_id="assistant-input",
                )
                with gr.Row(elem_id="assistant-actions"):
                    load_profile_btn = gr.Button("加载资料", elem_classes=["assistant-secondary-btn"])
                    clear_chat_btn = gr.Button("清空", elem_classes=["assistant-secondary-btn"])
                    send_chat_btn = gr.Button(
                        "发送",
                        variant="primary",
                        elem_id="assistant-send-btn",
                        elem_classes=["primary"],
                    )

        step_nav.change(
            fn=show_step_page,
            inputs=[step_nav],
            outputs=[parse_page, recommend_page, export_page],
            show_progress=False,
        )
        parse_event = parse_btn.click(
            fn=disable_action_button,
            inputs=None,
            outputs=parse_btn,
            show_progress=False,
        )
        parse_run = parse_event.then(
            fn=parse_records,
            inputs=[files, k, city, area, hospital_level, require_doctor],
            outputs=[doc_table, profile_state, summary, dept_table, parse_status],
            show_progress="full",
            show_progress_on=parse_status,
        )
        parse_run.success(
            fn=enable_action_button,
            inputs=None,
            outputs=parse_btn,
            show_progress=False,
        )
        parse_run.success(
            fn=load_patient_profile_to_assistant,
            inputs=[profile_state, assistant_history],
            outputs=[assistant_chat, assistant_history],
            show_progress=False,
        )
        parse_run.failure(
            fn=enable_action_button,
            inputs=None,
            outputs=parse_btn,
            show_progress=False,
        )
        recommend_event = recommend_btn.click(
            fn=disable_action_button,
            inputs=None,
            outputs=recommend_btn,
            show_progress=False,
        )
        recommend_run = recommend_event.then(
            fn=run_recommendation,
            inputs=[profile_state, k, city, area, hospital_level, require_doctor, assistant_provider],
            outputs=[recommendation_cards, recommendation_status, recommendation_state],
            show_progress=True,
        )
        recommend_run.success(
            fn=enable_action_button,
            inputs=None,
            outputs=recommend_btn,
            show_progress=False,
        )
        recommend_run.failure(
            fn=enable_action_button,
            inputs=None,
            outputs=recommend_btn,
            show_progress=False,
        )
        export_btn.click(
            fn=export_current_report,
            inputs=[profile_state, recommendation_state],
            outputs=[export_files, export_status],
            show_progress=True,
        )
        load_profile_btn.click(
            fn=load_patient_profile_to_assistant,
            inputs=[profile_state, assistant_history],
            outputs=[assistant_chat, assistant_history],
            show_progress=False,
        )
        assistant_inputs = [
            assistant_input,
            assistant_history,
            profile_state,
            recommendation_state,
            k,
            city,
            area,
            hospital_level,
            require_doctor,
            assistant_provider,
        ]
        assistant_outputs = [
            assistant_chat,
            assistant_history,
            assistant_input,
            recommendation_cards,
            recommendation_status,
            recommendation_state,
            area,
            parse_page,
            recommend_page,
            export_page,
            step_nav,
        ]
        send_chat_btn.click(
            fn=handle_assistant_message,
            inputs=assistant_inputs,
            outputs=assistant_outputs,
            show_progress=True,
        )
        assistant_input.submit(
            fn=handle_assistant_message,
            inputs=assistant_inputs,
            outputs=assistant_outputs,
            show_progress=True,
        )
        clear_chat_btn.click(
            fn=clear_assistant_chat,
            inputs=None,
            outputs=[assistant_chat, assistant_history, assistant_input],
            show_progress=False,
        )
    return demo


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    host = os.getenv("HOST", "0.0.0.0")
    app = build_app()
    app.queue(default_concurrency_limit=4).launch(
        server_name=host,
        server_port=port,
        share=True,
        show_error=True,
        theme=THEME,
        css=CSS,
    )
