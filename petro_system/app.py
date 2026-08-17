from __future__ import annotations

import html
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import gradio as gr

from Medical_demo.src.config import get_config as get_medical_demo_config
from Medical_demo.src.deepseek_agent import _extract_responses_text, _messages_to_responses_input

BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from petro_rules.repository import (  # noqa: E402
    STATUS_LABELS,
    RuleValidationError,
    dashboard_data,
    get_rule,
    list_import_batches,
    list_rules,
    next_rule_number,
    save_rule,
    set_rule_archived,
)

APP_TITLE = "石化领域多学科知识规则库系统"
ASSISTANT_CONFIG = get_medical_demo_config()

CATEGORY_CHOICES = [
    ("全部分类", "ALL"),
    ("操作规程", "SOP"),
    ("质量标准", "QS"),
    ("流程特征", "FLOW"),
    ("工艺规范", "PROC"),
    ("调度经验", "EXP"),
]
STATUS_CHOICES = [
    ("全部状态", "all"),
    ("已发布", "published"),
    ("草稿", "draft"),
    ("已归档", "archived"),
]
FORM_STATUS_CHOICES = [
    ("已发布", "published"),
    ("草稿", "draft"),
    ("已归档", "archived"),
]
RULE_TABLE_HEADERS = ["规则编号", "规则名称", "类别", "子类型", "状态"]
IMPORT_TABLE_HEADERS = [
    "批次",
    "文件",
    "状态",
    "总数",
    "新增",
    "更新",
    "未变化",
    "失败",
    "导入时间",
]

COLORS = {
    "blue": "#1664e8",
    "ink": "#10265b",
    "muted": "#667795",
    "line": "#dfe7f2",
}


CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700;800&display=swap');

:root {
  --blue: #1664e8;
  --blue-dark: #123b8b;
  --ink: #142653;
  --muted: #667795;
  --line: #dfe7f2;
  --page: #f6f8fc;
  --panel: #ffffff;
  --shadow: 0 3px 14px rgba(29, 75, 151, 0.07);
}

html, body, gradio-app {
  width: 100%;
  min-width: 320px;
  min-height: 100%;
  margin: 0;
  background: var(--page) !important;
  color: var(--ink);
  font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  letter-spacing: 0;
}

body { overflow-x: hidden; }

.gradio-container {
  width: 100vw !important;
  max-width: none !important;
  min-height: 100vh !important;
  padding: 0 !important;
  margin: 0 !important;
  background: var(--page) !important;
}

.gradio-container > .main,
.gradio-container > .main > .wrap,
.gradio-container > .main > .wrap > .contain,
.gradio-container > .main > .wrap > .contain > .gap {
  width: 100% !important;
  max-width: none !important;
  min-height: 100vh !important;
  padding: 0 !important;
  margin: 0 !important;
  gap: 0 !important;
}
.gradio-container div:has(#top-panel):has(#dashboard-grid) {
  width: 100% !important;
  max-width: none !important;
  padding: 0 !important;
  margin: 0 !important;
  gap: 0 !important;
  row-gap: 0 !important;
}
.gradio-container .main:has(#top-panel),
.gradio-container .wrap:has(#top-panel),
.gradio-container .contain:has(#top-panel),
.gradio-container .gap:has(#top-panel) {
  width: 100% !important;
  max-width: none !important;
  padding: 0 !important;
  margin: 0 !important;
  gap: 0 !important;
}

.dashboard-header {
  position: relative;
  height: 102px;
  box-sizing: border-box;
  display: flex;
  align-items: flex-start;
  overflow: hidden;
  padding: 7px 42px 5px 300px;
  border-bottom: 1px solid #e3ebf5;
  background-color: #f4f9ff;
  background-image: url('/gradio_api/file=images/toppannel.png');
  background-repeat: no-repeat;
  background-position: center;
  background-size: 100% 100%;
}

.dashboard-header::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  width: 295px;
  height: 102px;
  display: none;
  background:
    linear-gradient(180deg, rgba(242, 249, 255, 0.1), rgba(229, 242, 251, .75)),
    repeating-linear-gradient(90deg, transparent 0 32px, rgba(72, 143, 207, .22) 33px 35px, transparent 36px 54px),
    linear-gradient(164deg, transparent 0 36%, rgba(101, 157, 203, .42) 37% 38%, transparent 39% 100%);
  clip-path: polygon(0 16%, 4% 16%, 4% 58%, 8% 58%, 8% 7%, 11% 7%, 11% 62%, 15% 62%, 15% 27%, 18% 27%, 18% 68%, 23% 68%, 23% 18%, 25% 18%, 25% 75%, 29% 75%, 29% 100%, 0 100%);
}

.dashboard-header::after {
  display: none;
  position: absolute;
  left: 0;
  bottom: 0;
  width: 310px;
  height: 31px;
  background: linear-gradient(180deg, transparent, rgba(133, 190, 232, .26));
}

.brand-lockup { position: relative; z-index: 1; min-width: 0; }
.brand-lockup h1 {
  margin: 0;
  color: var(--blue-dark);
  font-size: clamp(24px, 2.05vw, 35px);
  line-height: 1.15;
  font-weight: 800;
  white-space: nowrap;
}
.brand-lockup p {
  margin: 17px 0 0;
  color: #466389;
  font-size: 16px;
  letter-spacing: 1px;
}

.header-nav {
  position: absolute;
  right: 39px;
  top: 0;
  height: 102px;
  display: flex;
  align-items: center;
  gap: 54px;
}
.home-nav {
  position: relative;
  display: flex;
  align-items: center;
  gap: 15px;
  height: 100%;
  padding: 0 16px;
  color: var(--blue);
  font-size: 17px;
  font-weight: 700;
  white-space: nowrap;
}
.home-nav::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: 4px;
  height: 4px;
  border-radius: 3px;
  background: var(--blue);
}
.home-icon { font-size: 30px; line-height: 1; }
.account-nav {
  display: flex;
  align-items: center;
  gap: 13px;
  color: #172654;
  font-size: 16px;
  font-weight: 700;
  white-space: nowrap;
}
.account-avatar {
  position: relative;
  width: 57px;
  height: 57px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: var(--blue);
  background: #e9f1ff;
  font-size: 0;
}
.account-avatar::before { content: ""; position: absolute; top: 12px; left: 21px; width: 16px; height: 16px; border-radius: 50%; background: var(--blue); }
.account-avatar::after { content: ""; position: absolute; left: 14px; bottom: 10px; width: 30px; height: 16px; border-radius: 16px 16px 9px 9px; background: var(--blue); }
.account-chevron { font-size: 19px; margin-left: 2px; }

#dashboard-grid {
  width: 100%;
  height: calc(100vh - 122px);
  min-height: 0;
  box-sizing: border-box;
  display: grid !important;
  grid-template-columns: minmax(310px, 26.7%) minmax(520px, 1fr) minmax(350px, 24.8%);
  gap: 14px !important;
  align-items: stretch !important;
  padding: 0 6px 3px;
  margin: 0 !important;
}
#dashboard-grid > .block {
  min-width: 0 !important;
  padding: 0 !important;
}

#top-panel { width: 100%; }
#left-rail,
#right-rail {
  min-width: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  gap: 13px !important;
  align-self: stretch !important;
}
#center-column {
  min-width: 0 !important;
  box-sizing: border-box;
  padding: 0 12px 12px !important;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  box-shadow: var(--shadow);
  overflow-x: hidden;
  overflow-y: auto;
}
#right-rail {
  position: relative;
  left: -2px;
  width: calc(100% + 4px) !important;
  max-width: calc(100% + 4px) !important;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  box-shadow: var(--shadow);
  overflow: hidden;
}
#center-stack { gap: 0 !important; }
#center-column #view-tabs {
  width: calc(100% + 24px) !important;
  margin: 0 -12px !important;
}

.side-stack,
.center-stack { min-width: 0; display: flex; flex-direction: column; gap: 13px; }
#left-rail {
  position: relative;
  top: -10px;
  left: -13px;
  width: calc(100% + 26px) !important;
  max-width: calc(100% + 26px) !important;
  height: calc(100% - 5px) !important;
  min-height: 0 !important;
}
#left-rail > .block { padding: 0 !important; margin: 0 !important; }
#left-rail > .wrap {
  height: 100% !important;
  min-height: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  gap: 13px !important;
}
#extraction-html,
#visual-html {
  padding: 0 !important;
  margin: 0 !important;
}
#extraction-html { position: absolute !important; top: 0; left: 0; right: 0; height: 365px !important; }
.panel {
  box-sizing: border-box;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.panel-head {
  height: 48px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 22px;
  border-bottom: 1px solid #edf2f8;
  color: var(--blue) !important;
  font-size: 17px;
  font-weight: 800;
}
.panel-head span:last-child { color: var(--blue) !important; }
.panel-head .head-icon { font-size: 23px; }

#extract-panel { height: 100%; min-height: 0; }
#visual-panel {
  position: absolute !important;
  top: 384px;
  right: auto;
  bottom: -15px;
  left: 12px;
  width: calc(100% - 24px) !important;
  max-width: calc(100% - 24px) !important;
  min-height: 0;
  display: flex !important;
  flex-direction: column !important;
  gap: 0 !important;
  padding: 0 !important;
  border: 1px solid var(--line) !important;
  border-radius: 10px !important;
  background: #fff !important;
  box-shadow: var(--shadow) !important;
  overflow: hidden !important;
}
#visual-panel > .block { padding: 0 !important; margin: 0 !important; }
.panel-body { padding: 14px 20px 18px; }
#visual-panel .panel-body { padding-top: 0; }
.upload-copy {
  height: 156px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px dashed #9fc2ff;
  border-radius: 10px;
  background: linear-gradient(180deg, #fbfdff, #ffffff);
  text-align: center;
}
.upload-copy .upload-icon { color: var(--blue); font-size: 53px; line-height: 1; margin-bottom: 4px; }
.upload-copy strong { color: #17254d; font-size: 16px; }
.upload-copy small { margin-top: 7px; color: #7583a0; font-size: 13px; }
#source-file {
  position: absolute !important;
  top: 70px;
  left: 20px;
  right: 20px;
  z-index: 3;
  width: auto !important;
  margin: 0 !important;
  min-height: 140px !important;
  opacity: 0;
  cursor: pointer;
}
#source-file .file-upload { min-height: 140px !important; border: 0 !important; background: transparent !important; }
#source-file .file-upload > div { min-height: 140px !important; }
#source-file .file-upload p, #source-file .file-upload button { display: none !important; }
.mini-title { margin: 14px 0 10px; color: #182957; font-size: 15px; font-weight: 800; }
.process-flow { display: flex; align-items: flex-start; gap: 4px; }
.process-step { flex: 1; text-align: center; position: relative; min-width: 0; }
.process-step:not(:last-child)::after {
  content: "→";
  position: absolute;
  right: -7px;
  top: 3px;
  color: #9bb0cf;
  font-size: 25px;
  line-height: 1;
}
.step-number {
  width: 33px;
  height: 33px;
  display: grid;
  place-items: center;
  margin: 0 auto 6px;
  border-radius: 50%;
  color: var(--blue);
  background: #edf4ff;
  font-size: 17px;
  font-weight: 800;
}
.step-label { color: #172650; font-size: 14px; font-weight: 700; white-space: nowrap; }
.step-note { margin-top: 4px; color: #7f8da7; font-size: 11px; white-space: nowrap; }
.visual-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
#visual-panel .visual-grid {
  margin-top: 8px;
}
#visual-panel .visual-card { height: 102px; min-height: 102px; }
.visual-card {
  min-height: 90px;
  box-sizing: border-box;
  padding: 12px 9px 10px;
  border: 1px solid #dbe5f2;
  border-radius: 9px;
  text-align: center;
  background: #fbfdff;
}
.visual-card .visual-icon { display: block; margin-bottom: 5px; font-size: 27px; }
.visual-card strong { display: block; font-size: 14px; line-height: 1.25; }
.visual-card small { display: block; margin-top: 6px; color: #6a7894; font-size: 12px; }
.visual-card.blue { color: #1761d9; background: #f4f8ff; }
.visual-card.green { color: #35aa6f; background: #f4fcf7; }
.visual-card.purple { color: #8051dc; background: #faf6ff; }
.visual-card.orange { color: #f28b1f; background: #fffaf1; }
.visual-card.cyan { color: #1aaecb; background: #f1fbfd; }
.visual-card.navy { color: #2459bb; background: #f4f7ff; }
#open-dashboard { position: absolute !important; left: 11px; right: 11px; bottom: 11px; width: auto !important; margin: 0 !important; min-height: 38px; border: 0 !important; border-radius: 6px !important; background: var(--blue) !important; color: white !important; font-weight: 700; }

#center-panel { flex: 1 1 auto; min-height: 0; border: 0; border-radius: 0; box-shadow: none; }
#view-tabs {
  width: 100%;
  height: 34px !important;
  min-height: 34px !important;
  box-sizing: border-box !important;
  padding: 2px 5px 0 !important;
  border: 0 !important;
  border-bottom: 1px solid #edf2f8 !important;
  background: #fff;
  overflow: visible !important;
}
#view-tabs label {
  height: 30px !important;
  min-height: 30px !important;
  box-sizing: border-box !important;
  padding: 0 13px !important;
  border: 1px solid #e2e8f1 !important;
  border-radius: 4px 4px 2px 2px !important;
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%) !important;
  color: #1a2851 !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  box-shadow: 0 1px 5px rgba(24, 55, 106, .12) !important;
}
#view-tabs label.selected {
  border-color: #d9e4f6 !important;
  color: var(--blue) !important;
  background: #fff !important;
  box-shadow: inset 0 -2px 0 var(--blue), 0 1px 6px rgba(22, 100, 232, .14) !important;
}
#view-tabs input { display: none !important; }
#view-tabs .wrap {
  width: 100% !important;
  height: 30px !important;
  display: flex !important;
  align-items: stretch !important;
  justify-content: flex-start !important;
  gap: 4px !important;
  padding: 0 !important;
}
#view-tabs .wrap label { flex: 0 0 100px !important; justify-content: center; }
#graph-view { min-height: 312px; }
.graph-stage { position: relative; height: 306px; margin: 0 10px; overflow: hidden; background: radial-gradient(circle at 50% 50%, rgba(238, 246, 255, .7), transparent 55%); }
.graph-lines { position: absolute; inset: 0; width: 100%; height: 100%; }
.graph-line { stroke: #8db6ff; stroke-width: 1.5; fill: none; }
.graph-dot { fill: #71a5f9; }
.graph-node { --node-color: #175ee6; position: absolute; display: flex; align-items: center; gap: 8px; color: #17254c; font-size: 14px; font-weight: 700; white-space: nowrap; }
.graph-node .node-orb { width: 25px; height: 25px; border-radius: 50%; box-sizing: border-box; box-shadow: 0 0 0 3px rgba(255,255,255,.95), 0 0 0 4px var(--node-color); background: var(--node-color); }
.graph-node.left { flex-direction: row-reverse; }
.graph-node.top { --node-color: #175ee6; left: 50%; top: 5px; transform: translateX(-50%); flex-direction: column-reverse; gap: 7px; }
.graph-node.center { left: 50%; top: 50%; transform: translate(-50%, -50%); }
.graph-node.center .node-orb { width: 102px; height: 102px; border: 0; box-shadow: none; color: #175ee6; background: #175ee6; }
.graph-node.center span:last-child { position: absolute; left: 0; right: 0; top: 38px; color: #fff; text-align: center; font-size: 18px; font-weight: 500; }
.graph-node.nw { --node-color: #2bb76d; left: 12%; top: 51px; }
.graph-node.ne { --node-color: #2bb76d; right: 13%; top: 51px; }
.graph-node.w { --node-color: #1bb0c8; left: 6%; top: 124px; }
.graph-node.e { --node-color: #7d4be0; right: 6%; top: 124px; }
.graph-node.sw { --node-color: #7c4bdc; left: 13%; top: 183px; }
.graph-node.se { --node-color: #fb8c17; right: 11%; top: 183px; }
.graph-node.bottom { --node-color: #16b4cd; left: 50%; bottom: 3px; transform: translateX(-50%); flex-direction: column; }
.graph-caption { display: none; }
.graph-placeholder { height: 306px; display: grid; place-items: center; color: #6d7d9b; font-size: 15px; }
.center-subgrid { display: grid; grid-template-columns: 1.22fr 1fr; gap: 13px; padding: 0 0 13px; }
.subpanel { min-height: 193px; box-sizing: border-box; border: 1px solid var(--line); border-radius: 10px; background: #fff; overflow: hidden; }
.subpanel h3 { margin: 0; padding: 15px 21px 0; color: var(--blue); font-size: 16px; line-height: 1.2; }
.donut-layout { display: grid; grid-template-columns: 190px 1fr; align-items: center; gap: 4px; padding: 8px 15px 15px; }
.donut { width: 148px; height: 148px; position: relative; margin: 0 auto; border-radius: 50%; background: conic-gradient(#3974eb 0 16.8%, #39b875 16.8% 35.6%, #7c49dd 35.6% 50.4%, #f98a1b 50.4% 72.1%, #20afc6 72.1% 87.6%, #2c5dbc 87.6% 100%); }
.donut::after { content: ""; position: absolute; inset: 31px; border-radius: 50%; background: #fff; }
.donut-label { position: absolute; inset: 0; z-index: 1; display: grid; place-content: center; text-align: center; color: #192852; font-size: 14px; font-weight: 700; line-height: 1.35; }
.legend { display: grid; gap: 7px; color: #415172; font-size: 13px; }
.legend-row { display: grid; grid-template-columns: 12px 1fr auto; gap: 7px; align-items: center; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; }
.legend-row b { font-weight: 500; }
.selected-card { padding: 16px 22px; color: #334161; }
.selected-card h4 { margin: 0 0 12px; color: #172650; font-size: 21px; }
.selected-card dl { display: grid; grid-template-columns: 75px 1fr; gap: 9px 0; margin: 0; font-size: 14px; }
.selected-card dt { color: #72809a; }
.selected-card dd { margin: 0; color: #283657; font-weight: 600; }
.selected-card dd strong { color: #1c2d5a; font-size: 16px; }
.center-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 13px; padding: 0 0 0; }
.metric-card { display: flex; align-items: center; gap: 15px; min-height: 113px; box-sizing: border-box; padding: 16px 20px; border: 1px solid var(--line); border-radius: 10px; background: #fff; }
.metric-icon { width: 53px; height: 53px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 15px; background: #edf4ff; color: var(--blue); font-size: 28px; }
.metric-label { color: #596986; font-size: 13px; }
.metric-value { margin-top: 4px; color: #172650; font-size: 23px; font-weight: 800; line-height: 1; }
.metric-value span { margin-left: 5px; color: #384a6f; font-size: 13px; font-weight: 500; }
.metric-note { margin-top: 8px; color: #7584a0; font-size: 12px; }

#assistant-panel { position: absolute !important; inset: 0 !important; width: 100% !important; min-height: 0; gap: 0 !important; padding: 0 !important; border: 0 !important; border-radius: 0 !important; box-shadow: none !important; background: transparent !important; }
#assistant-panel > .block { margin: 0 !important; padding: 0 !important; }
#assistant-panel .prose { margin: 0 !important; padding: 0 !important; }
.assistant-wrap { min-height: 100%; display: flex; flex-direction: column; }
.assistant-head { height: 50px; box-sizing: border-box; display: flex; align-items: center; gap: 9px; padding: 0 17px; border-bottom: 1px solid #edf2f8; color: var(--blue) !important; font-size: 17px; font-weight: 800; }
.assistant-robot-icon { position: relative; width: 27px; height: 27px; display: grid; place-items: center; border-radius: 50%; background: var(--blue); color: #fff; font-size: 0; }
.assistant-robot-icon::before { content: "▣"; font-size: 15px; line-height: 1; }
.assistant-head span:not(.assistant-state):not(.assistant-robot-icon) { color: var(--blue) !important; }
.assistant-head .assistant-state { margin-left: auto; color: #6e8fca; font-size: 11px; font-weight: 600; }
#assistant-chatbot { flex: 1 1 0 !important; min-height: 280px !important; height: auto !important; margin: 0 !important; padding: 0 7px !important; border: 0 !important; overflow: hidden !important; background: #fff !important; }
#assistant-chatbot .wrapper,
#assistant-chatbot .bubble-wrap { height: 100% !important; box-sizing: border-box !important; }
#assistant-chatbot .bubble-wrap { gap: 10px !important; padding: 9px 3px 7px !important; overflow-y: auto !important; }
#assistant-chatbot button,
#assistant-chatbot .icon-button-wrapper { display: none !important; }
#assistant-chatbot .message-row { position: relative; width: 100%; box-sizing: border-box; }
#assistant-chatbot .message-row.bot-row { justify-content: flex-start !important; padding-left: 37px !important; }
#assistant-chatbot .message-row.user-row { justify-content: flex-end !important; padding-right: 37px !important; }
#assistant-chatbot .message-row.bot-row::before,
#assistant-chatbot .message-row.user-row::after { position: absolute; top: 5px; width: 29px; height: 29px; display: grid; place-items: center; border-radius: 50%; background: var(--blue); color: #fff; font-size: 14px; font-weight: 800; line-height: 1; box-shadow: 0 0 0 2px #eaf2ff; }
#assistant-chatbot .message-row.bot-row::before { content: "▣"; left: 1px; }
#assistant-chatbot .message-row.user-row::after { content: "♟"; right: 1px; }
#assistant-chatbot .message-row .flex-wrap { max-width: 100% !important; }
#assistant-chatbot .bot.message,
#assistant-chatbot .user.message { max-width: 100% !important; padding: 0 !important; border: 0 !important; background: transparent !important; box-shadow: none !important; }
#assistant-chatbot .bot.message > .message,
#assistant-chatbot .user.message > .message { padding: 8px 11px !important; border-radius: 9px !important; box-shadow: none !important; font-size: 13px !important; line-height: 1.55 !important; }
#assistant-chatbot .bot.message > .message { border: 1px solid #dfe7f2 !important; background: #fff !important; color: #26385e !important; }
#assistant-chatbot .user.message > .message { border: 1px solid #d8e5f8 !important; background: #eaf2ff !important; color: #26385e !important; }
#assistant-chatbot .message-content p { margin: 0 0 4px !important; }
#assistant-chatbot .message-content p:last-child { margin-bottom: 0 !important; }
#assistant-chatbot .message-content,
#assistant-chatbot .message-content .md,
#assistant-chatbot .message-content .prose { font-size: 13px !important; line-height: 1.55 !important; }
#assistant-chatbot .message-content ul { margin: 4px 0 0 !important; padding-left: 18px !important; }
#assistant-chatbot .message-content li { margin: 0 !important; }
#assistant-chatbot .message-content small { display: block; margin-top: 3px; color: #7284a4; font-size: 11px; text-align: right; }
#assistant-input-row { align-items: center !important; gap: 8px !important; padding: 4px 12px !important; margin: 0 !important; border-top: 1px solid #edf2f8; }
#assistant-input { border: 1px solid #dce6f2 !important; border-radius: 8px !important; margin: 0 !important; box-shadow: none !important; }
#assistant-input textarea { min-height: 34px !important; padding: 7px 12px !important; font-size: 13px !important; }
#assistant-send-btn { min-width: 58px !important; max-width: 64px !important; min-height: 36px !important; border: 0 !important; border-radius: 6px !important; background: var(--blue) !important; color: #fff !important; font-weight: 700 !important; }
#assistant-send-btn:hover, #open-dashboard:hover { background: #0d55ca !important; }
.assistant-loading { display: inline-flex; align-items: center; gap: 8px; color: #566987; }
.assistant-loading::before { content: ""; width: 13px; height: 13px; box-sizing: border-box; border: 2px solid #c8d9f4; border-top-color: var(--blue); border-radius: 50%; animation: assistant-spin .75s linear infinite; }
@keyframes assistant-spin { to { transform: rotate(360deg); } }
.assistant-note { padding: 3px 14px; color: #8592a8; text-align: center; font-size: 11px; line-height: 18px; }
#assistant-panel .html-container:has(.assistant-note) { height: 24px !important; padding: 0 12px !important; }
#assistant-panel > .block:has(.assistant-note) { height: 24px !important; min-height: 24px !important; overflow: hidden !important; }

.hidden-state { display: none !important; }
.status-line { min-height: 20px; padding: 6px 14px 2px; color: #5f7192; font-size: 12px; }
.status-line:empty { display: none; }
#node-select { margin: 0 22px 15px; }
#node-select label { color: #71809c !important; font-size: 12px !important; }
#node-select input, #node-select .wrap { border-radius: 7px !important; border-color: #dce6f2 !important; }

#database-overview,
#rules-view,
#imports-view { width: 100%; min-width: 0; padding: 12px 4px 18px; }
#rules-view, #imports-view { gap: 10px !important; }
.db-overview { display: grid; gap: 12px; }
.db-kpis { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid #e0e7f0; border-radius: 7px; background: #fff; }
.db-kpis > div { min-width: 0; padding: 15px 16px; border-right: 1px solid #e8edf4; }
.db-kpis > div:last-child { border-right: 0; }
.db-kpis span { display: block; color: #667795; font-size: 12px; }
.db-kpis strong { display: inline-block; margin-top: 5px; color: #152b5c; font-size: 25px; line-height: 1; }
.db-kpis small { margin-left: 4px; color: #71809b; font-size: 11px; }
.db-section { padding: 14px 16px; border: 1px solid #e0e7f0; border-radius: 7px; background: #fff; }
.db-section h3 { margin: 0 0 13px; color: #1a3f79; font-size: 15px; }
.db-category-list { display: grid; gap: 11px; }
.db-category-row { display: grid; grid-template-columns: minmax(145px, 190px) minmax(120px, 1fr) 48px; align-items: center; gap: 11px; }
.db-category-row > div:first-child { display: flex; justify-content: space-between; gap: 8px; min-width: 0; font-size: 12px; }
.db-category-row strong { overflow: hidden; color: #25375a; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.db-category-row span, .db-category-row b { color: #74819a; font-size: 11px; font-weight: 500; text-align: right; }
.db-category-track { height: 8px; overflow: hidden; border-radius: 4px; background: #eef2f7; }
.db-category-track i { display: block; height: 100%; border-radius: 4px; }
.db-two-columns { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 12px; }
.db-section table { width: 100%; border-collapse: collapse; }
.db-section th, .db-section td { padding: 7px 6px; border-bottom: 1px solid #edf1f6; color: #445371; font-size: 11px; text-align: left; }
.db-section th { color: #6a7892; font-weight: 600; }
.db-section th:last-child, .db-section td:last-child { text-align: right; }

#rules-toolbar { align-items: end !important; gap: 8px !important; }
#rules-toolbar > .block { min-width: 0 !important; }
#rules-toolbar label, #rule-editor label { color: #586a88 !important; font-size: 11px !important; }
#rules-toolbar input, #rules-toolbar .wrap,
#rule-editor input, #rule-editor textarea, #rule-editor .wrap {
  border-color: #dbe3ed !important;
  border-radius: 5px !important;
  box-shadow: none !important;
}
#new-rule-btn, #refresh-rules-btn, #previous-page-btn, #next-page-btn,
#save-rule-btn, #archive-rule-btn {
  min-height: 36px !important;
  border-radius: 5px !important;
  font-size: 12px !important;
}
#new-rule-btn, #save-rule-btn { border-color: var(--blue) !important; background: var(--blue) !important; color: #fff !important; }
#archive-rule-btn { color: #9a3412 !important; background: #fff !important; }
#rule-table { min-width: 0 !important; border: 1px solid #dfe6ef !important; border-radius: 6px !important; overflow: hidden !important; }
#rule-table table { font-size: 11px !important; }
#rule-table th { color: #405273 !important; background: #f5f8fc !important; }
#rule-table td { max-width: 220px; color: #2f405f !important; }
#rule-table tbody tr:hover td { background: #edf4ff !important; }
.db-page-info { display: flex; align-items: center; justify-content: space-between; min-height: 24px; color: #687895; font-size: 11px; }
.db-page-info b { color: #1f3d70; }
#pagination-row { align-items: center !important; gap: 7px !important; }
#pagination-row > .block { margin: 0 !important; }
#rule-editor { margin-top: 2px; border: 1px solid #dfe6ef !important; border-radius: 7px !important; background: #fbfcfe !important; }
#rule-editor > .label-wrap { color: #173a74 !important; font-size: 13px !important; font-weight: 700 !important; }
#rule-editor .form { gap: 8px !important; padding: 11px !important; }
#rule-editor .form > .block, #rule-editor .form > .row { margin: 0 !important; }
.db-editor-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; padding: 2px 1px 5px; }
.db-editor-heading strong { overflow-wrap: anywhere; color: #1c315d; font-size: 14px; }
.db-editor-heading span { flex: 0 0 auto; color: #74829b; font-size: 11px; }
.db-action-message { min-height: 18px; color: #8a5b16; font-size: 11px; }
.db-action-message.success { color: #18794e; }
#rule-editor-actions { align-items: center !important; gap: 8px !important; }
#imports-view .table-wrap { border-radius: 6px !important; }
#imports-view table { font-size: 11px !important; }

@media (max-width: 1250px) {
  .db-kpis { grid-template-columns: repeat(2, 1fr); }
  .db-kpis > div:nth-child(2) { border-right: 0; }
  .db-kpis > div:nth-child(-n+2) { border-bottom: 1px solid #e8edf4; }
  .db-two-columns { grid-template-columns: 1fr; }
}

@media (max-width: 1250px) {
  .dashboard-header { padding-left: 235px; }
  #dashboard-grid { grid-template-columns: minmax(290px, 27%) minmax(500px, 1fr) minmax(330px, 28%); gap: 9px !important; }
  .header-nav { right: 20px; gap: 25px; }
  .brand-lockup p { font-size: 14px; }
}
@media (max-width: 980px) {
  html, body, gradio-app { overflow-y: auto; }
  .dashboard-header { height: 106px; padding: 15px 20px; }
  .dashboard-header::before { opacity: .32; }
  .brand-lockup h1 { font-size: 25px; }
  .brand-lockup p { margin-top: 5px; font-size: 13px; }
  .header-nav { top: 0; right: 16px; height: 106px; gap: 10px; }
  .account-nav { font-size: 14px; }
  .account-avatar { width: 43px; height: 43px; font-size: 23px; }
  .home-nav { padding: 0 7px; }
  #dashboard-grid { min-height: auto; grid-template-columns: 1fr 1fr; padding: 9px; }
  #dashboard-grid > .block:nth-child(2) { grid-column: 1 / -1; grid-row: 1; }
  #dashboard-grid > .block:nth-child(1) { grid-column: 1; grid-row: 2; }
  #dashboard-grid > .block:nth-child(3) { grid-column: 2; grid-row: 2; }
  .center-stack { min-height: 760px; }
}
@media (max-width: 640px) {
  .dashboard-header { height: 99px; align-items: flex-start; padding: 15px 15px; }
  .brand-lockup { padding-right: 88px; }
  .brand-lockup h1 { font-size: 20px; white-space: normal; }
  .brand-lockup p { font-size: 11px; letter-spacing: 0; }
  .header-nav { height: 99px; right: 10px; }
  .home-nav { display: none; }
  .account-nav span:not(.account-avatar):not(.account-chevron) { display: none; }
  #dashboard-grid { display: flex !important; flex-direction: column; height: auto; padding: 7px; }
  .side-stack, .center-stack { width: 100%; }
  #dashboard-grid > .block:nth-child(2), #dashboard-grid > .block:nth-child(1), #dashboard-grid > .block:nth-child(3) { width: 100%; }
  #left-rail {
    position: relative;
    top: 0;
    left: 0;
    width: 100% !important;
    max-width: 100% !important;
    height: auto !important;
    min-height: 0 !important;
  }
  #extraction-html { position: relative !important; height: 365px !important; }
  #visual-panel {
    position: relative !important;
    inset: auto !important;
    width: calc(100% - 24px) !important;
    max-width: calc(100% - 24px) !important;
    margin: 12px !important;
  }
  #center-column { width: 100% !important; min-height: 760px; }
  #right-rail {
    position: relative;
    left: 0;
    width: 100% !important;
    max-width: 100% !important;
    min-height: 520px;
  }
  .visual-grid { grid-template-columns: repeat(2, 1fr); }
  .center-subgrid { grid-template-columns: 1fr; }
  .center-metrics { grid-template-columns: 1fr; }
  .graph-stage { height: 270px; }
  .graph-node { font-size: 11px; }
  .graph-node.center .node-orb { width: 80px; height: 80px; }
  .graph-node.center span:last-child { top: 29px; font-size: 15px; }
  .donut-layout { grid-template-columns: 1fr; }
  .legend { padding: 0 22px; }
  .db-kpis { grid-template-columns: 1fr 1fr; }
  .db-category-row { grid-template-columns: minmax(120px, 1fr) 52px; }
  .db-category-track { grid-column: 1 / -1; grid-row: 2; }
  .db-editor-heading { align-items: flex-start; flex-direction: column; }
}
"""


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def header_html() -> str:
    return """
    <header class="dashboard-header" id="top-panel">
      <div class="brand-lockup">
        <h1>石化领域多学科知识规则库系统</h1>
        <p>规则抽取 · 可视化展示 · 智能辅助</p>
      </div>
      <div class="header-nav">
        <div class="home-nav"><span class="home-icon">⌂</span><span>首页</span></div>
        <div class="account-nav"><span class="account-avatar">●</span><span>管理员</span><span class="account-chevron">⌄</span></div>
      </div>
    </header>
    """


def extraction_html(imported_count: int = 0) -> str:
    import_note = "已导入 %d 份文档，等待规则识别。" % imported_count if imported_count else "支持 PDF / DOCX / XLSX / TXT 等格式"
    return f"""
    <section class="panel" id="extract-panel">
      <div class="panel-head"><span class="head-icon">▣</span><span>A. 知识规则抽取</span></div>
      <div class="panel-body">
        <div class="upload-copy">
          <div class="upload-icon">⇧</div>
          <strong>点击或拖拽文件到此处上传</strong>
          <small>{_esc(import_note)}</small>
          <small class="upload-hint">选择文件后可开始结构化解析</small>
        </div>
        <div class="mini-title">抽取流程</div>
        <div class="process-flow">
          <div class="process-step"><div class="step-number">1</div><div class="step-label">文档导入</div><div class="step-note">上传多源文档</div></div>
          <div class="process-step"><div class="step-number">2</div><div class="step-label">文本解析</div><div class="step-note">结构化识别</div></div>
          <div class="process-step"><div class="step-number">3</div><div class="step-label">规则识别</div><div class="step-note">识别规则要素</div></div>
          <div class="process-step"><div class="step-number">4</div><div class="step-label">分类入库</div><div class="step-note">知识存储化</div></div>
        </div>
        <div class="status-line">{_esc(import_note if imported_count else "")}</div>
      </div>
    </section>
    """


def visual_html() -> str:
    data = dashboard_data()
    counts = {item["code"]: item["count"] for item in data["categories"]}
    cards = [
        ("blue", "Σ", "规则总量", f'{data["active_count"]:,} 条'),
        ("orange", "▤", "操作规程", f'{counts.get("SOP", 0):,} 条'),
        ("green", "✓", "质量标准", f'{counts.get("QS", 0):,} 条'),
        ("purple", "⌘", "流程特征", f'{counts.get("FLOW", 0):,} 条'),
        ("cyan", "◇", "工艺规范", f'{counts.get("PROC", 0):,} 条'),
        ("navy", "◎", "调度经验", f'{counts.get("EXP", 0):,} 条'),
    ]
    card_html = "".join(
        f'<div class="visual-card {tone}"><span class="visual-icon">{icon}</span><strong>{label}</strong><small>{count}</small></div>'
        for tone, icon, label, count in cards
    )
    return f"""
    <div class="panel-head"><span class="head-icon">▦</span><span>B. 可视化展示</span></div>
    <div class="panel-body"><div class="visual-grid">{card_html}</div></div>
    """


def graph_html() -> str:
    return """
    <div class="graph-stage">
      <svg class="graph-lines" viewBox="0 0 760 314" preserveAspectRatio="none" aria-hidden="true">
        <path class="graph-line" d="M380 157 L380 45"/><path class="graph-line" d="M380 157 L103 65"/><path class="graph-line" d="M380 157 L589 65"/>
        <path class="graph-line" d="M380 157 L57 140"/><path class="graph-line" d="M380 157 L642 140"/><path class="graph-line" d="M380 157 L111 201"/><path class="graph-line" d="M380 157 L604 201"/><path class="graph-line" d="M380 157 L380 270"/>
        <circle class="graph-dot" cx="380" cy="94" r="4"/><circle class="graph-dot" cx="243" cy="111" r="4"/><circle class="graph-dot" cx="517" cy="97" r="4"/><circle class="graph-dot" cx="226" cy="149" r="4"/><circle class="graph-dot" cx="534" cy="147" r="4"/><circle class="graph-dot" cx="250" cy="178" r="4"/><circle class="graph-dot" cx="510" cy="183" r="4"/><circle class="graph-dot" cx="380" cy="238" r="4"/>
      </svg>
      <div class="graph-node top"><span class="node-orb"></span><span>原料单元</span></div>
      <div class="graph-node nw"><span class="node-orb"></span><span>报警温范</span></div>
      <div class="graph-node ne"><span class="node-orb"></span><span>工艺规程</span></div>
      <div class="graph-node w"><span class="node-orb"></span><span>安全环保</span></div>
      <div class="graph-node e"><span class="node-orb"></span><span>流程特征</span></div>
      <div class="graph-node sw"><span class="node-orb"></span><span>通用规则</span></div>
      <div class="graph-node se"><span class="node-orb"></span><span>操作规程</span></div>
      <div class="graph-node bottom"><span class="node-orb"></span><span>设备设施</span></div>
      <div class="graph-node center"><span class="node-orb"></span><span>乙烯装置</span></div>
    </div>
    """


def donut_html() -> str:
    rows = [
        ("#3974eb", "总量概览", "21,548", "16.87%"),
        ("#39b875", "工艺规范", "24,173", "18.84%"),
        ("#7c49dd", "流程特征", "18,965", "14.80%"),
        ("#f98a1b", "操作规程", "27,846", "21.73%"),
        ("#20afc6", "设备设施", "19,873", "15.50%"),
        ("#2c5dbc", "通用规则", "15,957", "12.46%"),
    ]
    legend = "".join(f'<div class="legend-row"><span class="legend-dot" style="background:{c}"></span><b>{n}</b><span>{v} ({p})</span></div>' for c, n, v, p in rows)
    return f"""
    <section class="subpanel"><h3>规则分类分布</h3><div class="donut-layout"><div class="donut"><div class="donut-label">总计<br><strong>128,362</strong> 条</div></div><div class="legend">{legend}</div></div></section>
    """


def selected_html(node: str = "乙烯装置") -> str:
    node = node or "乙烯装置"
    details = {
        "乙烯装置": ("装置", "12,845 条", "7 个", "2024-05-10"),
        "原料单元": ("单元", "8,430 条", "5 个", "2024-04-28"),
        "工艺规程": ("规范", "24,173 条", "12 个", "2024-05-08"),
        "操作规程": ("规程", "27,846 条", "9 个", "2024-05-09"),
        "设备设施": ("设施", "19,873 条", "11 个", "2024-05-06"),
        "通用规则": ("规则", "15,957 条", "14 个", "2024-05-02"),
        "安全环保": ("规则", "16,520 条", "8 个", "2024-05-01"),
        "流程特征": ("特征", "18,965 条", "10 个", "2024-05-07"),
        "报警温范": ("规则", "6,832 条", "4 个", "2024-04-25"),
    }
    category, related, cover, updated = details.get(node, details["乙烯装置"])
    return f"""
    <section class="subpanel"><h3>当前选中节点</h3><div class="selected-card"><h4>{_esc(node)}</h4><dl><dt>类别：</dt><dd>{_esc(category)}</dd><dt>关联规则：</dt><dd><strong>{_esc(related)}</strong></dd><dt>覆盖单元：</dt><dd>{_esc(cover)}</dd><dt>更新时间：</dt><dd>{_esc(updated)}</dd></dl></div></section>
    """


def metrics_html(imported_count: int = 0) -> str:
    total = "128,362" if not imported_count else f"{128362 + imported_count * 128:,}"
    return f"""
    <div class="center-metrics">
      <div class="metric-card"><div class="metric-icon">▤</div><div><div class="metric-label">规则总量</div><div class="metric-value">{total}<span>条</span></div><div class="metric-note">规则总数</div></div></div>
      <div class="metric-card"><div class="metric-icon">▰</div><div><div class="metric-label">关联文档</div><div class="metric-value">8,742<span>份</span></div><div class="metric-note">已解析文档</div></div></div>
      <div class="metric-card"><div class="metric-icon">▥</div><div><div class="metric-label">高频规则</div><div class="metric-value">98<span>个</span></div><div class="metric-note">近化覆盖高频单元</div></div></div>
    </div>
    """


def dashboard_overview_html() -> str:
    data = dashboard_data()
    category_colors = {
        "SOP": "#ef8a24",
        "QS": "#36a269",
        "FLOW": "#7652c7",
        "PROC": "#148ba8",
        "EXP": "#315eaa",
    }
    category_rows = "".join(
        f"""
        <div class="db-category-row">
          <div><strong>{_esc(item['name'])}</strong><span>{item['count']} 条</span></div>
          <div class="db-category-track"><i style="width:{item['percent']}%;background:{category_colors[item['code']]}"></i></div>
          <b>{item['percent']:.1f}%</b>
        </div>
        """
        for item in data["categories"]
    )
    subtype_rows = "".join(
        f'<tr><td>{_esc(item["subtype"])}</td><td>{item["count"]}</td></tr>'
        for item in data["subtypes"]
    )
    recent_rows = "".join(
        f'<tr><td>{_esc(item["rule_no"])}</td><td>{_esc(item["rule_name"])}</td><td>{_esc(item["updated_at"])}</td></tr>'
        for item in data["recent"]
    )
    return f"""
    <div class="db-overview">
      <div class="db-kpis">
        <div><span>有效规则</span><strong>{data['active_count']:,}</strong><small>条</small></div>
        <div><span>来源文档</span><strong>{data['source_count']:,}</strong><small>份</small></div>
        <div><span>草稿</span><strong>{data['draft_count']:,}</strong><small>条</small></div>
        <div><span>已归档</span><strong>{data['archived_count']:,}</strong><small>条</small></div>
      </div>
      <section class="db-section">
        <h3>五类规则分布</h3>
        <div class="db-category-list">{category_rows}</div>
      </section>
      <div class="db-two-columns">
        <section class="db-section">
          <h3>主要子类型</h3>
          <table><thead><tr><th>子类型</th><th>数量</th></tr></thead><tbody>{subtype_rows}</tbody></table>
        </section>
        <section class="db-section">
          <h3>最近更新</h3>
          <table><thead><tr><th>编号</th><th>名称</th><th>时间</th></tr></thead><tbody>{recent_rows}</tbody></table>
        </section>
      </div>
    </div>
    """


def import_table_data() -> list[list[Any]]:
    status_labels = {
        "success": "成功",
        "running": "进行中",
        "failed": "失败",
        "conflict": "待确认",
    }
    return [
        [
            item["id"],
            item["source_file_name"],
            status_labels.get(item["status"], item["status"]),
            item["expected_count"],
            item["inserted_count"],
            item["updated_count"],
            item["unchanged_count"],
            item["failed_count"],
            item["created_at"],
        ]
        for item in list_import_batches()
    ]


def rule_table_payload(
    keyword: str = "",
    category: str = "ALL",
    status: str = "all",
    page: int = 1,
) -> tuple[list[list[Any]], list[str], str, int]:
    result = list_rules(keyword, category, status, page=page, page_size=20)
    rows = [
        [
            item["rule_no"],
            item["rule_name"],
            item["category_name"].replace("规则", ""),
            item["subtype"],
            STATUS_LABELS.get(item["status"], item["status"]),
        ]
        for item in result.rows
    ]
    rule_numbers = [item["rule_no"] for item in result.rows]
    info = (
        f'<div class="db-page-info"><span>共 <b>{result.total}</b> 条</span>'
        f'<span>第 <b>{result.page}</b> / {result.pages} 页</span></div>'
    )
    return rows, rule_numbers, info, result.page


def filter_rule_table(
    keyword: str, category: str, status: str
) -> tuple[list[list[Any]], list[str], str, int]:
    return rule_table_payload(keyword, category, status, 1)


def previous_rule_page(
    keyword: str, category: str, status: str, page: int
) -> tuple[list[list[Any]], list[str], str, int]:
    return rule_table_payload(keyword, category, status, max(1, int(page or 1) - 1))


def next_rule_page(
    keyword: str, category: str, status: str, page: int
) -> tuple[list[list[Any]], list[str], str, int]:
    return rule_table_payload(keyword, category, status, int(page or 1) + 1)


def _editor_values(rule: dict[str, Any], message: str = "") -> tuple[Any, ...]:
    archived = rule["deleted_at"] is not None
    heading = (
        f'<div class="db-editor-heading"><strong>{_esc(rule["rule_name"])}</strong>'
        f'<span>{_esc(rule["rule_no"])} · 版本 {rule["version"]}</span></div>'
    )
    return (
        rule["rule_no"],
        "edit",
        heading,
        rule["rule_no"],
        rule["rule_name"],
        rule["category_code"],
        rule["status"],
        rule["subtype"],
        rule["applicable_scope"],
        rule["trigger_condition"] or "",
        rule["rule_content"],
        rule["parameter_text"] or "",
        rule["source_file"],
        rule["source_page"],
        rule["source_basis"],
        rule["notes"] or "",
        gr.update(value="恢复规则" if archived else "归档规则", interactive=True),
        f'<div class="db-action-message">{_esc(message)}</div>' if message else "",
    )


def select_rule_from_table(rule_numbers: list[str], evt: gr.SelectData) -> tuple[Any, ...]:
    index = evt.index[0] if isinstance(evt.index, (tuple, list)) else evt.index
    if not isinstance(index, int) or index < 0 or index >= len(rule_numbers or []):
        raise gr.Error("请选择有效的规则行")
    rule = get_rule(rule_numbers[index])
    if not rule:
        raise gr.Error("该规则不存在或已被移除")
    return _editor_values(rule)


def new_rule_form() -> tuple[Any, ...]:
    category = "SOP"
    rule_no = next_rule_number(category)
    return (
        "",
        "new",
        '<div class="db-editor-heading"><strong>新增规则</strong><span>保存后写入本地数据库</span></div>',
        rule_no,
        "",
        category,
        "draft",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        gr.update(value="归档规则", interactive=False),
        "",
    )


def update_new_rule_number(mode: str, category: str, current_rule_no: str) -> str:
    return next_rule_number(category) if mode == "new" else current_rule_no


def save_rule_form(
    original_rule_no: str,
    mode: str,
    rule_no: str,
    rule_name: str,
    category_code: str,
    status: str,
    subtype: str,
    applicable_scope: str,
    trigger_condition: str,
    rule_content: str,
    parameter_text: str,
    source_file: str,
    source_page: str,
    source_basis: str,
    notes: str,
) -> tuple[str, str, str, Any, str, str]:
    current = get_rule(original_rule_no) if original_rule_no else None
    if current and current["deleted_at"] is not None:
        raise gr.Error("已归档规则需先恢复后才能编辑")
    try:
        saved_rule_no = save_rule(
            {
                "rule_no": rule_no,
                "rule_name": rule_name,
                "category_code": category_code,
                "status": status,
                "subtype": subtype,
                "applicable_scope": applicable_scope,
                "trigger_condition": trigger_condition,
                "rule_content": rule_content,
                "parameter_text": parameter_text,
                "source_file": source_file,
                "source_page": source_page,
                "source_basis": source_basis,
                "notes": notes,
            },
            original_rule_no=original_rule_no if mode == "edit" else None,
        )
    except RuleValidationError as exc:
        raise gr.Error(str(exc)) from exc
    saved = get_rule(saved_rule_no)
    heading = (
        f'<div class="db-editor-heading"><strong>{_esc(saved["rule_name"])}</strong>'
        f'<span>{_esc(saved_rule_no)} · 版本 {saved["version"]}</span></div>'
    )
    return (
        saved_rule_no,
        "edit",
        heading,
        gr.update(value="归档规则", interactive=True),
        '<div class="db-action-message success">规则已保存到本地数据库。</div>',
        saved["status"],
    )


def toggle_rule_archive(rule_no: str) -> tuple[Any, ...]:
    rule = get_rule(rule_no)
    if not rule:
        raise gr.Error("请先选择一条规则")
    archived = rule["deleted_at"] is not None
    set_rule_archived(rule_no, not archived)
    updated = get_rule(rule_no)
    action = "恢复" if archived else "归档"
    values = list(_editor_values(updated, f"规则已{action}。"))
    return tuple(values)


def switch_database_view(tab: str) -> tuple[Any, ...]:
    tab = tab or "规则管理"
    return (
        gr.update(visible=tab == "分类统计"),
        gr.update(visible=tab == "规则管理"),
        gr.update(visible=tab == "导入记录"),
        dashboard_overview_html() if tab == "分类统计" else gr.update(),
        import_table_data() if tab == "导入记录" else gr.update(),
    )


def center_view(tab: str = "知识图谱", node: str = "乙烯装置", imported_count: int = 0) -> str:
    if tab == "规则树":
        body = """
        <div class="graph-placeholder"><div><strong>规则树</strong><br><small>乙烯装置　└─ 工艺规程　└─ 裂解炉操作　└─ 温度控制</small></div></div>
        """
    elif tab == "分类统计":
        body = """
        <div class="graph-placeholder"><div><strong>分类统计</strong><br><small>工艺规范与操作规程占据当前规则库的主要分类。</small></div></div>
        """
    elif tab == "规则查询":
        body = """
        <div class="graph-placeholder"><div><strong>规则查询</strong><br><small>输入关键词即可检索规则库中的标准、规程和设备关联关系。</small></div></div>
        """
    else:
        body = graph_html()
    return f"""
    <section class="panel" id="center-panel"><div id="graph-view">{body}</div></section>
    <div class="center-subgrid">{donut_html()}{selected_html(node)}</div>
    {metrics_html(imported_count)}
    """


def chat_message(role: str, text: str, timestamp: str | None = None) -> dict[str, Any]:
    stamp = timestamp or datetime.now().strftime("%H:%M")
    rendered = f'{str(text).strip()}\n\n<small>{stamp}</small>'
    return {"role": role, "content": rendered}


def assistant_welcome() -> list[dict[str, Any]]:
    return [
        chat_message(
            "assistant",
            "您好！我是石化知识助手。\n您可以对我提出知识检索、流程核查、规范解读等问题，我将提供专业辅助。",
            "10:24",
        ),
        chat_message("user", "乙烯装置裂解炉出口温度的控制建议？", "10:25"),
        chat_message(
            "assistant",
            "根据相关工艺规范和操作规程，乙烯装置裂解炉出口温度一般控制在 830~850℃ 范围内，具体建议如下：\n\n• 正常运行：830~850℃\n• 高负荷运行：≤850℃\n• 紧急情况：≤870℃",
            "10:26",
        ),
    ]


def upload_status(files: Any) -> tuple[str, str, int]:
    if not files:
        return extraction_html(), "", 0
    if isinstance(files, (str, Path)):
        items = [files]
    else:
        items = list(files)
    names = []
    for item in items:
        name = getattr(item, "name", item)
        names.append(Path(str(name)).name)
    count = len(names)
    note = f"已导入 {count} 份文档：" + "、".join(names[:3]) + ("等" if count > 3 else "")
    return extraction_html(count), note, count


def update_view(tab: str, node: str, imported_count: int = 0) -> str:
    return center_view(tab or "知识图谱", node or "乙烯装置", int(imported_count or 0))


def _history_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        chunks = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text", "")))
        return "".join(chunks)
    if isinstance(value, dict) and value.get("type") == "text":
        return str(value.get("text", ""))
    return str(value or "")


def _clean_chat_text(value: Any) -> str:
    text = _history_text(value)
    text = re.sub(r"\s*<small[^>]*>.*?</small>\s*$", "", text, flags=re.DOTALL | re.IGNORECASE)
    return html.unescape(text).strip()


def _assistant_api_history(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in history[-12:]:
        role = "user" if item.get("role") == "user" else "assistant"
        content = _clean_chat_text(item.get("content"))
        if content:
            messages.append({"role": role, "content": content})
    return messages


def _assistant_messages(
    user_message: str,
    history: list[dict[str, Any]],
    node: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是石化领域多学科知识规则库系统的中文AI助手。你负责知识检索、流程核查、"
                "工艺规范解释、设备标准关联和规则推荐。回答必须以规则库和可靠公开资料为依据；"
                "不得编造标准编号、阈值或操作步骤。涉及生产安全、联锁、异常处置时，必须提示用户"
                "以企业现行规程、装置边界条件和人工审核为准。"
            ),
        },
        {
            "role": "system",
            "content": (
                f"当前选中节点：{node or '乙烯装置'}。"
                "当前关联规则包括 PROC-OP-001023、SOP-OP-001512、DMS-STD-202104。"
                "如需引用实时公开信息，可联网搜索并标注来源。"
            ),
        },
        *_assistant_api_history(history),
        {"role": "user", "content": user_message},
    ]


def call_petro_assistant_api(
    user_message: str,
    history: list[dict[str, Any]],
    node: str,
) -> str:
    config = ASSISTANT_CONFIG
    messages = _assistant_messages(user_message, history, node)
    provider = (config.assistant_provider or "qwen").strip().lower()

    from openai import OpenAI

    if provider == "deepseek":
        if not config.deepseek_api_key:
            return "DeepSeek API Key 未配置，暂时无法调用AI助手。"
        client = OpenAI(api_key=config.deepseek_api_key, base_url=config.deepseek_base_url)
        response = client.chat.completions.create(
            model=config.deepseek_model,
            messages=messages,
            temperature=0.3,
        )
        return (response.choices[0].message.content or "").strip()

    if not config.dashscope_api_key:
        return "DASHSCOPE_API_KEY 未配置，暂时无法调用Qwen联网助手。"
    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.qwen_base_url)
    try:
        response = client.responses.create(
            model=config.qwen_assistant_model,
            input=_messages_to_responses_input(messages),
            tools=[{"type": "web_search"}, {"type": "web_extractor"}],
            extra_body={"enable_thinking": True},
        )
        answer = _extract_responses_text(response).strip()
    except Exception:
        response = client.chat.completions.create(
            model=config.qwen_assistant_fallback_model,
            messages=messages,
            temperature=0.3,
            extra_body={
                "enable_search": True,
                "search_options": {"forced_search": True, "search_strategy": "max"},
            },
        )
        answer = (response.choices[0].message.content or "").strip()
    return answer or "我暂时没有生成有效回复，请补充一下您的问题。"


def stream_petro_assistant_api(
    user_message: str,
    history: list[dict[str, Any]],
    node: str,
) -> Iterator[str]:
    config = ASSISTANT_CONFIG
    messages = _assistant_messages(user_message, history, node)
    provider = (config.assistant_provider or "qwen").strip().lower()

    from openai import OpenAI

    if provider == "deepseek":
        if not config.deepseek_api_key:
            yield "DeepSeek API Key 未配置，暂时无法调用AI助手。"
            return
        client = OpenAI(api_key=config.deepseek_api_key, base_url=config.deepseek_base_url)
        response = client.chat.completions.create(
            model=config.deepseek_model,
            messages=messages,
            temperature=0.3,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta
        return

    if not config.dashscope_api_key:
        yield "DASHSCOPE_API_KEY 未配置，暂时无法调用Qwen联网助手。"
        return

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.qwen_base_url)
    received_text = False
    try:
        with client.responses.stream(
            model=config.qwen_assistant_model,
            input=_messages_to_responses_input(messages),
            tools=[{"type": "web_search"}, {"type": "web_extractor"}],
            extra_body={"enable_thinking": True},
        ) as response_stream:
            for event in response_stream:
                if getattr(event, "type", "") != "response.output_text.delta":
                    continue
                delta = str(getattr(event, "delta", "") or "")
                if delta:
                    received_text = True
                    yield delta
            if not received_text:
                final_response = response_stream.get_final_response()
                answer = _extract_responses_text(final_response).strip()
                if answer:
                    received_text = True
                    yield answer
        if received_text:
            return
    except Exception:
        if received_text:
            raise

    response = client.chat.completions.create(
        model=config.qwen_assistant_fallback_model,
        messages=messages,
        temperature=0.3,
        stream=True,
        extra_body={
            "enable_search": True,
            "search_options": {"forced_search": True, "search_strategy": "max"},
        },
    )
    for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


def assistant_begin(
    message: str,
    history: list[dict[str, Any]] | None,
    node: str,
) -> tuple[list[dict[str, Any]], Any, Any, str, dict[str, Any]]:
    text = (message or "").strip()
    prior_history = list(history or assistant_welcome())
    if not text:
        return prior_history, gr.update(), gr.update(interactive=True), "请输入问题后再发送。", {}

    timestamp = datetime.now().strftime("%H:%M")
    visible_history = prior_history + [chat_message("user", text, timestamp)]
    loading = chat_message(
        "assistant",
        '<span class="assistant-loading">正在处理查询</span>',
        timestamp,
    )
    request = {
        "message": text,
        "prior_history": prior_history,
        "visible_history": visible_history,
        "node": node or "乙烯装置",
        "timestamp": timestamp,
    }
    return (
        (visible_history + [loading])[-24:],
        gr.update(value=""),
        gr.update(),
        "正在处理查询…",
        request,
    )


def assistant_stream(request: dict[str, Any] | None) -> Iterator[tuple[Any, str, Any, Any]]:
    request = request or {}
    message = str(request.get("message") or "").strip()
    if not message:
        yield gr.update(), "", gr.update(interactive=True), gr.update(interactive=True)
        return

    prior_history = list(request.get("prior_history") or assistant_welcome())
    visible_history = list(request.get("visible_history") or prior_history)
    node = str(request.get("node") or "乙烯装置")
    timestamp = str(request.get("timestamp") or datetime.now().strftime("%H:%M"))
    answer = ""
    last_emit = 0.0
    try:
        for delta in stream_petro_assistant_api(message, prior_history, node):
            answer += delta
            now = time.monotonic()
            if last_emit == 0.0 or now - last_emit >= 0.06 or delta.endswith(("。", "！", "？", "\n")):
                live_history = (visible_history + [chat_message("assistant", answer, timestamp)])[-24:]
                yield live_history, "正在生成回复…", gr.update(), gr.update()
                last_emit = now
    except Exception as exc:
        answer = f"AI助手暂时响应失败：{exc}"

    answer = answer.strip() or "我暂时没有生成有效回复，请补充一下您的问题。"
    final_history = (visible_history + [chat_message("assistant", answer, timestamp)])[-24:]
    yield (
        final_history,
        "内容由 AI 生成，仅供参考，请人工核实。",
        gr.update(),
        gr.update(),
    )


def open_dashboard() -> tuple[str, str]:
    return "分类统计", "已切换至分类统计视图。"


def build_app() -> gr.Blocks:
    initial_rows, initial_rule_numbers, initial_page_info, initial_page = rule_table_payload()
    initial_rule = get_rule(initial_rule_numbers[0]) if initial_rule_numbers else None

    with gr.Blocks(
        title=APP_TITLE,
        fill_width=True,
        fill_height=True,
        css=CSS,
    ) as demo:
        gr.HTML(header_html())
        imported_state = gr.State(0)
        selected_node = gr.State("乙烯装置")
        assistant_request = gr.State({})
        rule_numbers_state = gr.State(initial_rule_numbers)
        page_state = gr.State(initial_page)
        selected_rule_state = gr.State(initial_rule["rule_no"] if initial_rule else "")
        form_mode_state = gr.State("edit" if initial_rule else "new")
        with gr.Row(elem_id="dashboard-grid"):
            with gr.Column(elem_id="left-rail", scale=1):
                extraction = gr.HTML(extraction_html(), elem_id="extraction-html")
                source_file = gr.File(
                    label="",
                    file_count="multiple",
                    file_types=[".pdf", ".docx", ".xlsx", ".xls", ".txt", ".png", ".jpg", ".jpeg"],
                    type="filepath",
                    elem_id="source-file",
                    show_label=False,
                )
                with gr.Column(elem_id="visual-panel", elem_classes=["panel"]):
                    gr.HTML(visual_html(), elem_id="visual-html")
                    open_btn = gr.Button("进入可视化面板", elem_id="open-dashboard")
                upload_note = gr.Textbox(value="", visible=False, elem_id="upload-note")
            with gr.Column(elem_id="center-column", scale=2):
                with gr.Column(elem_id="center-stack"):
                    view_tabs = gr.Radio(
                        ["分类统计", "规则管理", "导入记录"],
                        value="规则管理",
                        show_label=False,
                        container=False,
                        elem_id="view-tabs",
                    )
                    with gr.Column(visible=False, elem_id="database-overview") as overview_view:
                        overview_html = gr.HTML(dashboard_overview_html())
                    with gr.Column(visible=True, elem_id="rules-view") as rules_view:
                        with gr.Row(elem_id="rules-toolbar"):
                            rule_search = gr.Textbox(
                                label="搜索",
                                placeholder="编号、名称、内容或来源",
                                scale=3,
                            )
                            category_filter = gr.Dropdown(
                                CATEGORY_CHOICES,
                                value="ALL",
                                label="类别",
                                scale=2,
                            )
                            status_filter = gr.Dropdown(
                                STATUS_CHOICES,
                                value="all",
                                label="状态",
                                scale=2,
                            )
                            refresh_rules_btn = gr.Button(
                                "刷新", elem_id="refresh-rules-btn", min_width=62
                            )
                            new_rule_btn = gr.Button(
                                "＋ 新增", elem_id="new-rule-btn", min_width=72
                            )
                        rule_table = gr.Dataframe(
                            headers=RULE_TABLE_HEADERS,
                            value=initial_rows,
                            datatype=["str"] * len(RULE_TABLE_HEADERS),
                            interactive=False,
                            wrap=True,
                            show_label=False,
                            elem_id="rule-table",
                        )
                        with gr.Row(elem_id="pagination-row"):
                            previous_page_btn = gr.Button(
                                "上一页", elem_id="previous-page-btn", min_width=70
                            )
                            page_info = gr.HTML(initial_page_info)
                            next_page_btn = gr.Button(
                                "下一页", elem_id="next-page-btn", min_width=70
                            )

                        with gr.Accordion(
                            "规则详情与编辑", open=True, elem_id="rule-editor"
                        ):
                            editor_heading = gr.HTML(
                                _editor_values(initial_rule)[2]
                                if initial_rule
                                else ""
                            )
                            with gr.Row():
                                form_rule_no = gr.Textbox(
                                    label="规则编号*",
                                    value=initial_rule["rule_no"] if initial_rule else "",
                                )
                                form_rule_name = gr.Textbox(
                                    label="规则名称*",
                                    value=initial_rule["rule_name"] if initial_rule else "",
                                )
                            with gr.Row():
                                form_category = gr.Dropdown(
                                    CATEGORY_CHOICES[1:],
                                    value=initial_rule["category_code"] if initial_rule else "SOP",
                                    label="规则类别*",
                                )
                                form_status = gr.Dropdown(
                                    FORM_STATUS_CHOICES,
                                    value=initial_rule["status"] if initial_rule else "draft",
                                    label="状态*",
                                )
                            with gr.Row():
                                form_subtype = gr.Textbox(
                                    label="子类型*",
                                    value=initial_rule["subtype"] if initial_rule else "",
                                )
                                form_scope = gr.Textbox(
                                    label="适用范围*",
                                    value=initial_rule["applicable_scope"] if initial_rule else "",
                                )
                            with gr.Row():
                                form_trigger = gr.Textbox(
                                    label="触发条件",
                                    value=(initial_rule["trigger_condition"] or "") if initial_rule else "",
                                )
                                form_parameter = gr.Textbox(
                                    label="参数范围",
                                    value=(initial_rule["parameter_text"] or "") if initial_rule else "",
                                )
                            form_content = gr.Textbox(
                                label="规则内容*",
                                value=initial_rule["rule_content"] if initial_rule else "",
                                lines=3,
                            )
                            with gr.Row():
                                form_source_file = gr.Textbox(
                                    label="来源文件*",
                                    value=initial_rule["source_file"] if initial_rule else "",
                                    scale=3,
                                )
                                form_source_page = gr.Textbox(
                                    label="来源页码*",
                                    value=initial_rule["source_page"] if initial_rule else "",
                                    scale=1,
                                )
                            form_source_basis = gr.Textbox(
                                label="来源依据*",
                                value=initial_rule["source_basis"] if initial_rule else "",
                                lines=2,
                            )
                            form_notes = gr.Textbox(
                                label="备注",
                                value=(initial_rule["notes"] or "") if initial_rule else "",
                                lines=2,
                            )
                            editor_message = gr.HTML("")
                            with gr.Row(elem_id="rule-editor-actions"):
                                save_rule_btn = gr.Button(
                                    "保存规则", elem_id="save-rule-btn", variant="primary"
                                )
                                archive_rule_btn = gr.Button(
                                    "归档规则",
                                    elem_id="archive-rule-btn",
                                    interactive=bool(initial_rule),
                                )

                    with gr.Column(visible=False, elem_id="imports-view") as imports_view:
                        with gr.Row():
                            gr.HTML(
                                '<div class="db-editor-heading"><strong>Excel 导入记录</strong><span>本地数据库批次审计</span></div>'
                            )
                            refresh_imports_btn = gr.Button("刷新", min_width=70)
                        imports_table = gr.Dataframe(
                            headers=IMPORT_TABLE_HEADERS,
                            value=import_table_data(),
                            interactive=False,
                            wrap=True,
                            show_label=False,
                        )
            with gr.Column(elem_id="right-rail", scale=1):
                with gr.Column(elem_id="assistant-panel", elem_classes=["panel", "assistant-wrap"]):
                    gr.HTML('<div class="assistant-head"><span class="assistant-robot-icon"></span><span>C. AI助手</span><span class="assistant-state">● Qwen联网</span></div>')
                    assistant_chat = gr.Chatbot(
                        value=assistant_welcome(),
                        type="messages",
                        show_label=False,
                        layout="bubble",
                        height="100%",
                        min_height=280,
                        autoscroll=True,
                        feedback_options=None,
                        allow_tags=False,
                        elem_id="assistant-chatbot",
                    )
                    with gr.Row(elem_id="assistant-input-row"):
                        assistant_input = gr.Textbox(placeholder="请输入您的问题...", show_label=False, lines=1, max_lines=3, scale=1, elem_id="assistant-input")
                        send_btn = gr.Button("➤", variant="primary", min_width=58, elem_id="assistant-send-btn")
                    gr.HTML('<div class="assistant-note">内容由AI生成，仅供参考，请人工核实</div>')
                    assistant_status = gr.Textbox(value="", visible=False, elem_id="assistant-status")

        source_file.change(
            upload_status,
            inputs=[source_file],
            outputs=[extraction, upload_note, imported_state],
            show_progress="hidden",
        )
        view_tabs.change(
            switch_database_view,
            inputs=[view_tabs],
            outputs=[overview_view, rules_view, imports_view, overview_html, imports_table],
            show_progress="hidden",
        )
        open_event = open_btn.click(
            open_dashboard,
            outputs=[view_tabs, upload_note],
            show_progress="hidden",
        )
        open_event.then(
            switch_database_view,
            inputs=[view_tabs],
            outputs=[overview_view, rules_view, imports_view, overview_html, imports_table],
            show_progress="hidden",
        )

        rule_filter_inputs = [rule_search, category_filter, status_filter]
        rule_table_outputs = [rule_table, rule_numbers_state, page_info, page_state]
        for component in (rule_search, category_filter, status_filter):
            component.change(
                filter_rule_table,
                inputs=rule_filter_inputs,
                outputs=rule_table_outputs,
                show_progress="hidden",
            )
        rule_search.submit(
            filter_rule_table,
            inputs=rule_filter_inputs,
            outputs=rule_table_outputs,
            show_progress="hidden",
        )
        refresh_rules_btn.click(
            filter_rule_table,
            inputs=rule_filter_inputs,
            outputs=rule_table_outputs,
            show_progress="hidden",
        )
        previous_page_btn.click(
            previous_rule_page,
            inputs=[*rule_filter_inputs, page_state],
            outputs=rule_table_outputs,
            show_progress="hidden",
        )
        next_page_btn.click(
            next_rule_page,
            inputs=[*rule_filter_inputs, page_state],
            outputs=rule_table_outputs,
            show_progress="hidden",
        )

        editor_outputs = [
            selected_rule_state,
            form_mode_state,
            editor_heading,
            form_rule_no,
            form_rule_name,
            form_category,
            form_status,
            form_subtype,
            form_scope,
            form_trigger,
            form_content,
            form_parameter,
            form_source_file,
            form_source_page,
            form_source_basis,
            form_notes,
            archive_rule_btn,
            editor_message,
        ]
        rule_table.select(
            select_rule_from_table,
            inputs=[rule_numbers_state],
            outputs=editor_outputs,
            show_progress="hidden",
        )
        new_rule_btn.click(
            new_rule_form,
            outputs=editor_outputs,
            show_progress="hidden",
        )
        form_category.change(
            update_new_rule_number,
            inputs=[form_mode_state, form_category, form_rule_no],
            outputs=[form_rule_no],
            show_progress="hidden",
        )

        save_inputs = [
            selected_rule_state,
            form_mode_state,
            form_rule_no,
            form_rule_name,
            form_category,
            form_status,
            form_subtype,
            form_scope,
            form_trigger,
            form_content,
            form_parameter,
            form_source_file,
            form_source_page,
            form_source_basis,
            form_notes,
        ]
        save_event = save_rule_btn.click(
            save_rule_form,
            inputs=save_inputs,
            outputs=[
                selected_rule_state,
                form_mode_state,
                editor_heading,
                archive_rule_btn,
                editor_message,
                form_status,
            ],
            show_progress="minimal",
        )
        save_event.then(
            rule_table_payload,
            inputs=[*rule_filter_inputs, page_state],
            outputs=rule_table_outputs,
            show_progress="hidden",
        )
        archive_event = archive_rule_btn.click(
            toggle_rule_archive,
            inputs=[selected_rule_state],
            outputs=editor_outputs,
            show_progress="minimal",
        )
        archive_event.then(
            rule_table_payload,
            inputs=[*rule_filter_inputs, page_state],
            outputs=rule_table_outputs,
            show_progress="hidden",
        )
        refresh_imports_btn.click(
            import_table_data,
            outputs=[imports_table],
            show_progress="hidden",
        )

        assistant_inputs = [assistant_input, assistant_chat, selected_node]
        assistant_begin_outputs = [assistant_chat, assistant_input, send_btn, assistant_status, assistant_request]
        assistant_stream_outputs = [assistant_chat, assistant_status, send_btn, assistant_input]
        send_event = send_btn.click(
            assistant_begin,
            inputs=assistant_inputs,
            outputs=assistant_begin_outputs,
            show_progress="hidden",
            queue=False,
        )
        send_event.then(
            assistant_stream,
            inputs=[assistant_request],
            outputs=assistant_stream_outputs,
            show_progress="hidden",
        )
        submit_event = assistant_input.submit(
            assistant_begin,
            inputs=assistant_inputs,
            outputs=assistant_begin_outputs,
            show_progress="hidden",
            queue=False,
        )
        submit_event.then(
            assistant_stream,
            inputs=[assistant_request],
            outputs=assistant_stream_outputs,
            show_progress="hidden",
        )
    return demo


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    host = os.getenv("HOST", "127.0.0.1")
    build_app().queue().launch(
        server_name=host,
        server_port=port,
        show_error=True,
        allowed_paths=[str(Path(__file__).resolve().parent / "images")],
    )
