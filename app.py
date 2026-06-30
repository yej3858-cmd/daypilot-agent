# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import copy
import html
import calendar
import json
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import dedent

import requests
import streamlit as st
import toml
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

st.set_page_config(page_title="DayPilot Agent", page_icon="📅", layout="wide")

SECRETS_PATH = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
DATA_PATH = Path(__file__).resolve().parent / "daypilot_store.json"
FONT_PATH = Path(
    r"C:\USERS\YEJ38\APPDATA\LOCAL\MICROSOFT\WINDOWS\FONTS\DXKPGB-KSCPC-EUC-H.TTF"
)

DEFAULT_WORK = [
    {"time": "09:30", "priority": "중요", "content": "팀 스탠드업"},
    {"time": "11:00", "priority": "중요", "content": "고객사 미팅"},
    {"time": "15:00", "priority": "보통", "content": "주간 보고 공유"},
]
DEFAULT_PERSONAL = [
    {"time": "12:30", "priority": "중요", "content": "병원 예약"},
    {"time": "19:00", "priority": "보통", "content": "운동"},
]
SAMPLE_TASK_ITEMS = [
    {"priority": "중요", "content": "제안서 수정"},
    {"priority": "보통", "content": "3분기 실적 정리"},
    {"priority": "중요", "content": "메일함 중요 답변 처리"},
]
SAMPLE_DEADLINE_ITEMS = [
    {"time": "17:00", "priority": "최우선", "content": "고객사 제안서 제출"},
    {"time": "16:30", "priority": "중요", "content": "팀장님께 주간 보고 초안 전달"},
]
SAMPLE = {
    "tasks": "- 제안서 수정\n- 3분기 실적 정리\n- 메일함 중요 답변 처리",
    "deadline_tasks": "- 오늘 17시까지 고객사 제안서 제출\n- 오늘 중 팀장님께 주간 보고 초안 전달",
    "condition": "집중력은 보통이지만 오전 에너지가 더 좋고, 오후에는 쉽게 피로해집니다.",
    "concerns": "급한 일부터 하다 보면 중요한 보고서 정리가 밀립니다. 미팅 사이 공백 시간을 잘 쓰고 싶습니다.",
    "location": "Seoul",
    "target_leave_time": "18:30",
    "focus_block": 60,
}
WEATHER = {
    0: "맑음",
    1: "대체로 맑음",
    2: "부분적으로 흐림",
    3: "흐림",
    45: "안개",
    48: "서리 안개",
    51: "이슬비",
    53: "보통 비",
    55: "강한 이슬비",
    61: "약한 비",
    63: "비",
    65: "강한 비",
    71: "약한 눈",
    73: "눈",
    75: "강한 눈",
    80: "소나기",
    81: "강한 소나기",
    82: "매우 강한 소나기",
    95: "뇌우",
}
FOCUS_TIPS = [
    "오전에는 판단이 필요한 업무를 먼저 배치해 보세요.",
    "회의 전후 10분은 메모 정리와 후속 액션 확인에 쓰면 흐름이 안정됩니다.",
    "집중 블록 하나에는 한 가지 결과물만 남긴다는 기준을 잡아보세요.",
    "이동 일정이 있는 날은 긴 작업보다 짧은 마감 단위를 우선하는 편이 좋습니다.",
    "오후 피로가 예상되면 답변 처리나 검토 업무를 묶어 처리해 보세요.",
    "우선순위가 흔들릴 때는 오늘 반드시 끝낼 일 한 가지를 먼저 확정하세요.",
]


class DashboardSummary(BaseModel):
    top_task: str = Field(description="오늘 가장 우선해야 할 업무 한 줄")
    deadline_risk: str = Field(description="마감 위험도. 예: 낮음, 보통, 높음")
    focus_need: str = Field(description="집중이 가장 필요한 시간 또는 총 집중 시간")
    leave_feasibility: str = Field(description="목표 퇴근시간 기준 퇴근 가능성")


class PriorityItem(BaseModel):
    category: str = Field(description="우선순위 카테고리")
    task: str = Field(description="업무 또는 할 일")
    reason: str = Field(description="분류 이유")


class TimeBlock(BaseModel):
    time: str = Field(description="시간대")
    plan: str = Field(description="실행 계획")
    focus: str = Field(description="집중 포인트")


class DayPlan(BaseModel):
    dashboard: DashboardSummary
    summary: list[str]
    priorities: list[PriorityItem]
    execution_order: list[str]
    time_blocks: list[TimeBlock]
    checklist: list[str]
    share_message: str
    balance_advice: str


def font_css() -> str:
    if not FONT_PATH.exists():
        return ""
    encoded = base64.b64encode(FONT_PATH.read_bytes()).decode("ascii")
    return (
        "@font-face {"
        "font-family:'DayPilotKorean';"
        f"src:url(data:font/ttf;base64,{encoded}) format('truetype');"
        "}"
    )


def inject_styles() -> None:
    st.markdown(
        f"""
<style>
{font_css()}
:root {{
  --bg:#F7F7FA;
  --header:#111318;
  --ink:#202124;
  --muted:#6B7280;
  --accent:#6D5EF6;
  --accent-soft:#F1EEFF;
  --mint:#DFF7EA;
  --border:#E5E7EB;
  --surface:#FFFFFF;
  --soft:#FAFBFD;
  --shadow:0 14px 36px rgba(17,19,24,.06);
}}

html, body, [class*="css"], .stApp, .stMarkdown, .stTextArea textarea,
.stButton button, .stDownloadButton button, .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {{
  font-family:'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif !important;
}}

.topbar-brand, .hero-title {{
  font-family:'DayPilotKorean','Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif !important;
}}

.stApp {{
  background:var(--bg);
  color:var(--ink);
}}

.main .block-container {{
  max-width:1240px;
  padding-top:1.15rem;
  padding-bottom:2.8rem;
}}

.topbar {{
  background:var(--header);
  color:#fff;
  border-radius:24px;
  padding:1.05rem 1.45rem;
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin-bottom:1rem;
  box-shadow:0 18px 40px rgba(0,0,0,.16);
}}

.topbar-brand {{
  font-size:1.5rem;
  font-weight:900;
  letter-spacing:-.03em;
}}

.topbar-menu {{
  display:flex;
  gap:1.35rem;
  font-size:.92rem;
  font-weight:700;
  color:rgba(255,255,255,.92);
}}

.hero-card, .info-card, .today-card, .planner-card, .result-shell, .panel-card,
.section-card, .suggestion-card, .dashboard-card {{
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:24px;
  box-shadow:var(--shadow);
}}

.hero-card {{
  padding:2.2rem 2.15rem;
  margin-bottom:1rem;
}}

.hero-title {{
  margin:0;
  font-size:2.8rem;
  line-height:1;
  font-weight:900;
  color:var(--ink);
  letter-spacing:-.04em;
}}

.hero-subtitle {{
  margin:.8rem 0 .35rem 0;
  color:var(--accent);
  font-size:1.08rem;
  font-weight:900;
}}

.hero-body {{
  max-width:820px;
  margin:0;
  color:var(--muted);
  line-height:1.78;
  font-size:1rem;
}}

.hero-pills {{
  display:flex;
  flex-wrap:wrap;
  gap:.55rem;
  margin-top:1.1rem;
}}

.hero-pill {{
  display:inline-flex;
  align-items:center;
  padding:.45rem .8rem;
  border-radius:999px;
  background:var(--accent-soft);
  color:var(--accent);
  font-size:.82rem;
  font-weight:900;
}}

.today-card {{
  padding:1.15rem 1.2rem;
  min-height:128px;
}}

.today-label {{
  font-size:.75rem;
  font-weight:900;
  color:var(--accent);
  letter-spacing:.05em;
  margin-bottom:.45rem;
}}

.today-main {{
  font-size:1.03rem;
  font-weight:900;
  color:var(--ink);
  margin-bottom:.35rem;
}}

.today-sub {{
  font-size:.91rem;
  line-height:1.62;
  color:var(--muted);
}}

.planner-card {{
  padding:1.2rem 1.2rem 1rem 1.2rem;
  margin-bottom:1.15rem;
}}

.result-shell {{
  padding:1.2rem;
  margin-top:1rem;
}}

.section-heading {{
  margin:0 0 .8rem 0;
  font-size:1.18rem;
  font-weight:900;
  color:var(--ink);
  letter-spacing:-.02em;
}}

.subtle-heading {{
  margin:0 0 .45rem 0;
  padding:.15rem 0 .15rem .75rem;
  font-size:1rem;
  font-weight:900;
  color:var(--ink);
  border-left:4px solid var(--accent);
  background:linear-gradient(90deg, rgba(109,94,246,.08), rgba(109,94,246,0));
  border-radius:10px;
}}

.helper-text {{
  margin:0 0 .9rem 0;
  padding:0 0 .75rem .05rem;
  color:var(--muted);
  font-size:.9rem;
  line-height:1.6;
  border-bottom:1px solid #ECEFF5;
}}

.inner-section-box {{
  background:#FFFFFF;
  border:1px solid var(--border);
  border-radius:18px;
  padding:1rem;
  box-shadow:0 8px 20px rgba(17,19,24,.04);
}}

.dashboard-grid {{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:.8rem;
}}

.dashboard-card {{
  padding:1rem;
}}

.dashboard-label {{
  font-size:.78rem;
  font-weight:900;
  color:var(--accent);
  margin-bottom:.35rem;
}}

.dashboard-value {{
  font-size:1rem;
  font-weight:900;
  color:var(--ink);
  line-height:1.45;
}}

.dashboard-sub {{
  font-size:.88rem;
  color:var(--muted);
  margin-top:.2rem;
}}

.section-card {{
  padding:1rem 1.05rem;
  margin-bottom:1rem;
}}

.page-section {{
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:22px;
  box-shadow:var(--shadow);
  padding:1.15rem 1.2rem;
  margin:1rem 0;
}}

.page-section + .page-section {{
  margin-top:1.15rem;
}}

.schedule-card {{
  background:var(--soft);
  border:1px solid var(--border);
  border-radius:18px;
  padding:.9rem 1rem;
  margin-bottom:.65rem;
}}

.schedule-top {{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:.8rem;
  margin-bottom:.35rem;
}}

.time-pill, .priority-pill, .chip {{
  display:inline-block;
  padding:.28rem .62rem;
  border-radius:999px;
  font-size:.78rem;
  font-weight:900;
}}

.time-pill, .chip {{
  background:var(--accent-soft);
  color:var(--accent);
}}

.priority-pill {{
  background:var(--mint);
  color:#19724A;
}}

.priority-pill.priority-top {{
  background:#FEE2E2;
  color:#B91C1C;
}}

.priority-pill.priority-high {{
  background:#FEF3C7;
  color:#B45309;
}}

.priority-pill.priority-normal {{
  background:#DFF7EA;
  color:#19724A;
}}

.schedule-text {{
  color:var(--ink);
  font-size:.96rem;
  line-height:1.55;
}}

.summary-grid {{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:.8rem;
}}

.summary-item {{
  background:var(--soft);
  border:1px solid var(--border);
  border-radius:18px;
  padding:1rem;
  color:var(--ink);
  line-height:1.65;
}}

.k-table {{
  width:100%;
  border-collapse:collapse;
  border:1px solid var(--border);
  border-radius:18px;
  overflow:hidden;
}}

.k-table th {{
  background:#F9FAFB;
  color:var(--ink);
  text-align:left;
  padding:.9rem .95rem;
  font-size:.92rem;
  font-weight:900;
  border-bottom:1px solid var(--border);
}}

.k-table td {{
  background:#fff;
  color:var(--ink);
  padding:.95rem;
  line-height:1.62;
  vertical-align:top;
  border-bottom:1px solid var(--border);
}}

.k-table tr:last-child td {{
  border-bottom:none;
}}

.timeline {{
  display:grid;
  gap:.7rem;
}}

.timeline-card {{
  display:grid;
  grid-template-columns:170px 1fr;
  gap:.9rem;
  align-items:start;
  background:var(--soft);
  border:1px solid var(--border);
  border-radius:18px;
  padding:.9rem 1rem;
}}

.timeline-time {{
  font-size:.92rem;
  font-weight:900;
  color:var(--accent);
}}

.timeline-plan {{
  font-size:.97rem;
  font-weight:900;
  color:var(--ink);
  margin-bottom:.22rem;
}}

.timeline-focus {{
  font-size:.9rem;
  color:var(--muted);
  line-height:1.55;
}}

.flow-grid {{
  display:grid;
  grid-template-columns:1fr;
  gap:.55rem;
}}

.flow-card {{
  background:var(--soft);
  border:1px solid var(--border);
  border-radius:16px;
  padding:.78rem .9rem;
  display:grid;
  grid-template-columns:88px 1fr;
  gap:.7rem;
  align-items:start;
}}

.flow-step {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  background:var(--accent-soft);
  color:var(--accent);
  font-size:.76rem;
  font-weight:900;
  border-radius:999px;
  min-height:30px;
  padding:0 .6rem;
}}

.flow-text {{
  color:var(--ink);
  line-height:1.5;
  font-size:.94rem;
}}

.quote-card {{
  background:var(--soft);
  border:1px solid var(--border);
  border-radius:18px;
  padding:1rem 1.05rem;
  color:var(--ink);
  line-height:1.75;
}}

.suggestion-card {{
  padding:1rem 1.05rem;
  min-height:128px;
}}

.suggestion-title {{
  font-size:.95rem;
  font-weight:900;
  color:var(--ink);
  margin:0 0 .35rem 0;
}}

.suggestion-body {{
  color:var(--muted);
  line-height:1.66;
  font-size:.92rem;
  margin:0;
}}

.stTabs [data-baseweb="tab-list"] {{
  gap:.45rem;
  margin-bottom:1rem;
}}

.stTabs [data-baseweb="tab"] {{
  background:#fff;
  border:1px solid var(--border);
  border-radius:999px;
  padding:.52rem .9rem;
  color:var(--ink);
  font-weight:800;
}}

.stTabs [aria-selected="true"] {{
  background:var(--accent-soft) !important;
  color:var(--accent) !important;
  border-color:#D9D4FF !important;
}}

.stTextArea label p, .stMarkdown p, .stMarkdown li, .stMarkdown strong,
.stInfo, .stSuccess, .stWarning, .stError, label, .stCaption {{
  color:var(--ink) !important;
}}

div[data-testid="stTextArea"] textarea,
div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
div[data-baseweb="base-input"] > div {{
  background:var(--soft) !important;
  color:var(--ink) !important;
  border:1px solid var(--border) !important;
  border-radius:16px !important;
}}

div[data-testid="stTextArea"] textarea,
div[data-baseweb="input"] input,
div[data-baseweb="base-input"] input,
input[type="text"],
input[type="time"],
input[type="number"],
.stTextInput input,
.stTimeInput input {{
  color:var(--ink) !important;
  -webkit-text-fill-color:var(--ink) !important;
  caret-color:var(--ink) !important;
}}

.stSelectbox div[data-baseweb="select"] *,
.stSelectbox [data-baseweb="select"] span,
.stSelectbox [data-baseweb="select"] input {{
  color:var(--ink) !important;
  -webkit-text-fill-color:var(--ink) !important;
}}

div[data-testid="stTextArea"] textarea {{
  padding:.95rem 1rem !important;
  line-height:1.65 !important;
}}

div[data-testid="stTextArea"] textarea::placeholder,
input::placeholder {{
  color:#8A9099 !important;
  opacity:1 !important;
  -webkit-text-fill-color:#8A9099 !important;
}}

.stButton button, .stDownloadButton button {{
  border-radius:15px;
  font-weight:900;
  min-height:3rem;
}}

.stButton button[kind="primary"] {{
  background:linear-gradient(135deg,var(--accent),#8477ff) !important;
  color:#fff !important;
  border:none !important;
  font-size:1rem;
  box-shadow:0 16px 34px rgba(109,94,246,.24);
}}

.stButton button {{
  background:#fff;
  color:var(--ink) !important;
  border:1px solid var(--border) !important;
}}

.stDownloadButton button {{
  background:var(--accent);
  color:#fff !important;
  border:none !important;
}}

[data-testid="stSidebar"] {{
  background:#20242C;
}}

[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3,
[data-testid="stSidebar"] .stMarkdown strong,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"],
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stTextInput label,
[data-testid="stSidebar"] .stDateInput label {{
  color:#F3F4F6 !important;
}}

.sidebar-card {{
  background:#323844;
  border:1px solid rgba(255,255,255,.08);
  border-radius:18px;
  padding:1rem;
  margin-bottom:.95rem;
}}

.sidebar-block {{
  margin:1.1rem 0 1.3rem 0;
  padding:.85rem 0 0 0;
  border-top:1px solid rgba(255,255,255,.10);
}}

.sidebar-card h4 {{
  margin:0 0 .45rem 0;
  color:#fff !important;
  font-size:1rem;
  font-weight:900;
}}

.sidebar-card p {{
  margin:0;
  color:#E5E7EB !important;
  line-height:1.7;
  font-size:.95rem;
}}

.sidebar-saved-wrap {{
  background:#323844;
  border:1px solid rgba(255,255,255,.08);
  border-radius:18px;
  padding:1rem;
  margin-bottom:.95rem;
}}

.sidebar-saved-wrap .sidebar-card {{
  background:transparent;
  border:none;
  box-shadow:none;
  padding:0;
  margin:0;
}}

.sidebar-saved-actions {{
  margin-top:.8rem;
}}

.sidebar-inline-editor {{
  margin-top:.8rem;
  padding-top:.1rem;
  border-top:1px solid rgba(255,255,255,.08);
}}

.sidebar-edit-card {{
  background:#F8F9FC;
  border:1px solid var(--border);
  border-radius:16px;
  padding:.45rem;
  margin:.35rem 0 .75rem 0;
}}

.sidebar-section-label {{
  display:inline-flex;
  align-items:center;
  margin:.95rem 0 .6rem 0;
  padding:.3rem .65rem;
  color:#C7D2FE !important;
  background:rgba(109,94,246,.14);
  border:1px solid rgba(199,210,254,.16);
  border-radius:999px;
  font-size:.74rem;
  font-weight:900;
  letter-spacing:.08em;
  text-transform:uppercase;
}}

.sidebar-section-gap {{
  height:.35rem;
}}

@media (max-width:960px) {{
  .dashboard-grid, .summary-grid {{
    grid-template-columns:1fr;
  }}
  .timeline-card {{
    grid-template-columns:1fr;
  }}
  .topbar {{
    display:block;
  }}
  .topbar-menu {{
    margin-top:.8rem;
    flex-wrap:wrap;
    gap:1rem;
  }}
}}
</style>
""",
        unsafe_allow_html=True,
    )


def init_state() -> None:
    today = datetime.now().date()
    st.session_state.setdefault("selected_date", today)
    st.session_state.setdefault("selected_date_picker", today)
    st.session_state.setdefault("loaded_plan_date", None)
    st.session_state.setdefault("work_schedule", [])
    st.session_state.setdefault("personal_schedule", [])
    st.session_state.setdefault("task_items", [])
    st.session_state.setdefault("deadline_items", [])
    st.session_state.setdefault("generated_plan", None)
    st.session_state.setdefault("generated_markdown", "")
    scalar_defaults = {
        "condition": "",
        "concerns": "",
        "location": "Seoul",
        "target_leave_time": "18:30",
        "focus_block": 60,
        "location_input": "Seoul",
        "target_leave_time_input": "18:30",
        "focus_block_input": 60,
    }
    for key, value in scalar_defaults.items():
        st.session_state.setdefault(key, value)
    defaults = {
        "work_schedule_new_time": "09:00",
        "work_schedule_new_priority": "보통",
        "work_schedule_new_content": "",
        "personal_schedule_new_time": "18:00",
        "personal_schedule_new_priority": "보통",
        "personal_schedule_new_content": "",
        "task_items_new_priority": "보통",
        "task_items_new_content": "",
        "deadline_items_new_time": "17:00",
        "deadline_items_new_priority": "중요",
        "deadline_items_new_content": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    sync_selected_plan()



def load_sample() -> None:
    today = datetime.now().date()
    st.session_state.selected_date = today
    st.session_state.selected_date_picker = today
    st.session_state.loaded_plan_date = None
    st.session_state.location_input = "Seoul"
    st.session_state.target_leave_time_input = "18:30"
    st.session_state.focus_block_input = 60
    st.session_state.work_schedule = copy.deepcopy(DEFAULT_WORK)
    st.session_state.personal_schedule = copy.deepcopy(DEFAULT_PERSONAL)
    st.session_state.task_items = copy.deepcopy(SAMPLE_TASK_ITEMS)
    st.session_state.deadline_items = copy.deepcopy(SAMPLE_DEADLINE_ITEMS)
    for key, value in SAMPLE.items():
        st.session_state[key] = value
    save_current_plan()


def reset_today_inputs() -> None:
    today = datetime.now().date()
    st.session_state.selected_date = today
    st.session_state.selected_date_picker = today
    st.session_state.loaded_plan_date = None
    st.session_state.location = "Seoul"
    st.session_state.target_leave_time = "18:30"
    st.session_state.focus_block = 60
    st.session_state.location_input = "Seoul"
    st.session_state.target_leave_time_input = "18:30"
    st.session_state.focus_block_input = 60
    st.session_state.work_schedule = []
    st.session_state.personal_schedule = []
    st.session_state.task_items = []
    st.session_state.deadline_items = []
    st.session_state.condition = ""
    st.session_state.concerns = ""
    st.session_state.generated_plan = None
    st.session_state.generated_markdown = ""
    save_current_plan()


def build_chain() -> PromptTemplate:
    return PromptTemplate.from_template(
        dedent(
            """
            당신은 직장인의 하루를 정리해 주는 업무 코치 AI Agent입니다.
            사용자의 입력을 바탕으로 현실적이고 실행 가능한 하루 계획을 한국어로 작성하세요.

            응답은 반드시 아래 JSON 스키마를 따르세요.
            - dashboard: top_task, deadline_risk, focus_need, leave_feasibility
            - summary: 오늘의 핵심 요약 3~5개
            - priorities: 우선순위 분류 목록(category, task, reason)
            - execution_order: 추천 실행 순서 목록
            - time_blocks: 시간대별 계획 목록(time, plan, focus)
            - checklist: 누락 방지 체크리스트 목록
            - share_message: 팀원 또는 상사에게 공유할 문구
            - balance_advice: 오늘의 균형 조언

            계획 원칙:
            1. 업무 일정과 개인 일정의 충돌을 피하세요.
            2. 마감 업무를 최우선 반영하세요.
            3. 목표 퇴근시간을 고려해 과도한 계획을 피하세요.
            4. 집중 블록 길이를 고려해 몰입 작업을 배치하세요.
            5. 고민되는 점을 해결할 수 있는 실질적 전략을 포함하세요.
            6. execution_order는 최대 8단계까지만 작성하세요.
            7. priorities의 reason은 과장 없이 실무적인 톤으로 간결하게 작성하세요.
            8. dashboard는 아래 형식으로 현실적으로 작성하세요.
               - top_task: 오늘 가장 우선할 업무 한 줄
               - deadline_risk: 낮음 / 보통 / 높음 중 하나
               - focus_need: 예: 오전 2시간, 10:00-12:00, 오후 집중 90분
               - leave_feasibility: 예: 가능, 보통, 다소 촉박

            오늘 날짜: {today}
            위치: {location}
            목표 퇴근시간: {target_leave_time}
            선호 집중 블록 길이(분): {focus_block}

            [입력 정보]
            오늘의 업무 일정:
            {work_schedule}

            오늘의 개인 일정:
            {personal_schedule}

            해야 할 업무:
            {tasks}

            마감 업무:
            {deadline_tasks}

            컨디션:
            {condition}

            고민되는 점:
            {concerns}
            """
        ).strip()
    )


def load_local_secrets() -> dict[str, str]:
    if not SECRETS_PATH.exists():
        return {}
    try:
        data = toml.loads(SECRETS_PATH.read_text(encoding="utf-8-sig"))
        return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}


def resolve_api_key() -> tuple[str | None, str | None, str]:
    if "OPENAI_API_KEY" in st.secrets and str(st.secrets["OPENAI_API_KEY"]).strip():
        return (
            str(st.secrets["OPENAI_API_KEY"]).strip(),
            "openai",
            "Streamlit secrets의 OPENAI_API_KEY를 사용 중입니다.",
        )
    if "GOOGLE_API_KEY" in st.secrets and str(st.secrets["GOOGLE_API_KEY"]).strip():
        return (
            str(st.secrets["GOOGLE_API_KEY"]).strip(),
            "google",
            "Streamlit secrets의 GOOGLE_API_KEY를 사용 중입니다.",
        )
    if "GEMINI_API_KEY" in st.secrets and str(st.secrets["GEMINI_API_KEY"]).strip():
        return (
            str(st.secrets["GEMINI_API_KEY"]).strip(),
            "google",
            "Streamlit secrets의 GEMINI_API_KEY를 사용 중입니다.",
        )

    local = load_local_secrets()
    if local.get("OPENAI_API_KEY", "").strip():
        return (
            local["OPENAI_API_KEY"].strip(),
            "openai",
            f"로컬 파일 {SECRETS_PATH}의 OPENAI_API_KEY를 사용 중입니다.",
        )
    if local.get("GOOGLE_API_KEY", "").strip():
        return (
            local["GOOGLE_API_KEY"].strip(),
            "google",
            f"로컬 파일 {SECRETS_PATH}의 GOOGLE_API_KEY를 사용 중입니다.",
        )
    if local.get("GEMINI_API_KEY", "").strip():
        return (
            local["GEMINI_API_KEY"].strip(),
            "google",
            f"로컬 파일 {SECRETS_PATH}의 GEMINI_API_KEY를 사용 중입니다.",
        )

    if SECRETS_PATH.exists():
        return (
            None,
            None,
            f"{SECRETS_PATH} 파일은 있지만 OPENAI_API_KEY, GOOGLE_API_KEY 또는 GEMINI_API_KEY 값을 읽지 못했습니다.",
        )
    return None, None, f"{SECRETS_PATH} 파일을 찾지 못했습니다."


def get_secret_status() -> tuple[bool, str]:
    key, _, message = resolve_api_key()
    return (True, message) if key else (False, message)


def generate_plan(payload: dict[str, str]) -> DayPlan:
    api_key, provider, message = resolve_api_key()
    if not api_key or not provider:
        raise ValueError(message)
    if provider != "google":
        raise ValueError("?? ?? Gemini(GOOGLE_API_KEY ?? GEMINI_API_KEY) ???? ?????.")

    prompt = build_chain().format(**payload)
    last_error = None
    for model_name in ["gemini-2.5-flash", "gemini-2.0-flash"]:
        try:
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=0.3,
            )
            structured_llm = llm.with_structured_output(DayPlan)
            return structured_llm.invoke(prompt)
        except Exception as exc:
            last_error = exc
            if "NOT_FOUND" not in str(exc):
                raise
    raise RuntimeError(f"???? Gemini ??? ?? ?????: {last_error}")


def priority_tone_class(priority: str) -> str:
    mapping = {"???": "priority-top", "??": "priority-high", "??": "priority-normal"}
    return mapping.get(priority, "priority-normal")


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_weather(location: str) -> dict[str, str] | None:
    query = location.strip()
    if not query:
        return None
    geo = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": query, "count": 1, "language": "ko", "format": "json"},
        timeout=10,
    )
    geo.raise_for_status()
    results = geo.json().get("results") or []
    if not results:
        return None

    first = results[0]
    forecast = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": first["latitude"],
            "longitude": first["longitude"],
            "current": "temperature_2m,weather_code",
            "timezone": "auto",
        },
        timeout=10,
    )
    forecast.raise_for_status()
    current = forecast.json().get("current", {})
    code = int(current.get("weather_code", -1))
    return {
        "name": first.get("name", query),
        "temperature": f"{current.get('temperature_2m', '?')}°C",
        "description": WEATHER.get(code, "날씨 정보 확인 필요"),
    }


def today_focus_tip(condition: str, concerns: str) -> str:
    seed = sum(ord(char) for char in f"{datetime.now():%Y-%m-%d}{condition}{concerns}")
    return FOCUS_TIPS[seed % len(FOCUS_TIPS)]


def schedule_text(entries: list[dict[str, str]]) -> str:
    if not entries:
        return "?? ??"
    ordered = sorted(entries, key=lambda item: item["time"])
    return "\n".join(f"- {entry['time']} | {entry['priority']} | {entry['content']}" for entry in ordered)


def task_text(entries: list[dict[str, str]]) -> str:
    if not entries:
        return "업무 없음"
    return "\n".join(f"- {entry['priority']} | {entry['content']}" for entry in entries)


def deadline_text(entries: list[dict[str, str]]) -> str:
    if not entries:
        return "마감 업무 없음"
    ordered = sorted(entries, key=lambda item: item["time"])
    return "\n".join(f"- {entry['time']} | {entry['priority']} | {entry['content']}" for entry in ordered)


def read_store() -> dict:
    if not DATA_PATH.exists():
        return {"daily": {}, "weekly": {}, "monthly": {}}
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"daily": {}, "weekly": {}, "monthly": {}}


def write_store(data: dict) -> None:
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def week_key(value) -> str:
    iso = value.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def month_key(value) -> str:
    return value.strftime("%Y-%m")


def save_current_plan() -> None:
    current_date = st.session_state.selected_date
    date_key = current_date.strftime("%Y-%m-%d") if hasattr(current_date, 'strftime') else str(current_date)
    data = read_store()
    data.setdefault("daily", {})[date_key] = {
        "work_schedule": st.session_state.work_schedule,
        "personal_schedule": st.session_state.personal_schedule,
        "task_items": st.session_state.task_items,
        "deadline_items": st.session_state.deadline_items,
        "condition": st.session_state.condition,
        "concerns": st.session_state.concerns,
        "location": st.session_state.location,
        "target_leave_time": st.session_state.target_leave_time,
        "focus_block": st.session_state.focus_block,
    }
    write_store(data)
    st.session_state.loaded_plan_date = date_key


def sync_selected_plan() -> None:
    current_date = st.session_state.selected_date
    date_key = current_date.strftime("%Y-%m-%d") if hasattr(current_date, 'strftime') else str(current_date)
    if st.session_state.get("loaded_plan_date") == date_key:
        return
    data = read_store()
    daily = data.get("daily", {}).get(date_key, {})
    st.session_state.work_schedule = daily.get("work_schedule", [])
    st.session_state.personal_schedule = daily.get("personal_schedule", [])
    st.session_state.task_items = daily.get("task_items", [])
    st.session_state.deadline_items = daily.get("deadline_items", [])
    st.session_state.condition = daily.get("condition", "")
    st.session_state.concerns = daily.get("concerns", "")
    st.session_state.location = daily.get("location", "Seoul")
    st.session_state.target_leave_time = daily.get("target_leave_time", "18:30")
    st.session_state.focus_block = daily.get("focus_block", 60)
    st.session_state.location_input = st.session_state.location
    st.session_state.target_leave_time_input = st.session_state.target_leave_time
    st.session_state.focus_block_input = st.session_state.focus_block
    st.session_state.loaded_plan_date = date_key


def recent_saved_dates(limit: int = 6) -> list[str]:
    daily_keys = sorted(read_store().get("daily", {}).keys(), reverse=True)
    return daily_keys[:limit]


def make_empty_daily_record() -> dict:
    return {
        "work_schedule": [],
        "personal_schedule": [],
        "task_items": [],
        "deadline_items": [],
        "condition": "",
        "concerns": "",
        "location": "Seoul",
        "target_leave_time": "18:30",
        "focus_block": 60,
    }


def get_daily_record(date_key: str) -> dict:
    daily = read_store().get("daily", {}).get(date_key, {})
    base = make_empty_daily_record()
    for key in base:
        base[key] = daily.get(key, base[key])
    return base


def write_daily_record(date_key: str, daily: dict) -> None:
    data = read_store()
    data.setdefault("daily", {})[date_key] = daily
    write_store(data)


def remove_daily_record(date_key: str) -> None:
    data = read_store()
    data.get("daily", {}).pop(date_key, None)
    write_store(data)


def saved_schedule_preview(date_key: str) -> str:
    daily = get_daily_record(date_key)
    items: list[str] = []

    for entry in daily.get("work_schedule", [])[:2]:
        items.append(f"업무 | {entry.get('time', '')} | {entry.get('content', '')}")
    for entry in daily.get("personal_schedule", [])[:1]:
        items.append(f"개인 | {entry.get('time', '')} | {entry.get('content', '')}")
    for entry in daily.get("deadline_items", [])[:2]:
        items.append(f"마감 | {entry.get('time', '')} | {entry.get('content', '')}")

    if not items:
        return "저장된 일정이 없습니다."

    return "<br>".join(html.escape(item) for item in items[:4])



def open_saved_date(date_key: str) -> None:
    st.session_state.sidebar_edit_date = date_key
    st.session_state.sidebar_manage_date_pending = datetime.strptime(date_key, "%Y-%m-%d").date()
    st.rerun()


def delete_saved_date(date_key: str) -> None:
    remove_daily_record(date_key)
    if st.session_state.get("sidebar_edit_date") == date_key:
        st.session_state.sidebar_edit_date = None
    st.rerun()


def load_today_from_sidebar() -> None:
    today = datetime.now().date()
    st.session_state.selected_date = today
    st.session_state.selected_date_picker = today
    st.session_state.loaded_plan_date = None
    st.session_state.sidebar_edit_date = today.strftime("%Y-%m-%d")
    st.rerun()


def render_sidebar_date_editor(date_key: str) -> None:
    daily = get_daily_record(date_key)
    priority_options = ["최우선", "중요", "보통"]
    sections = [
        ("work_schedule", "업무 일정", True),
        ("personal_schedule", "개인 일정", True),
        ("deadline_items", "마감 업무", True),
        ("task_items", "해야 할 업무", False),
    ]

    st.markdown("<div class='sidebar-inline-editor'>", unsafe_allow_html=True)
    st.caption(f"{date_key} 항목 수정")

    for bucket, label, has_time in sections:
        entries = daily.get(bucket, [])
        with st.expander(label, expanded=False):
            if not entries:
                st.caption("저장된 항목이 없습니다.")
                continue

            for index, entry in enumerate(entries):
                key_base = f"sidebar_{date_key}_{bucket}_{index}"
                st.markdown("<div class='sidebar-edit-card'>", unsafe_allow_html=True)
                if has_time:
                    c1, c2 = st.columns([1.1, 1.2])
                    with c1:
                        time_value = st.text_input("시간", value=entry.get("time", ""), key=f"{key_base}_time")
                    with c2:
                        selected = entry.get("priority", "보통")
                        priority_value = st.selectbox(
                            "중요도",
                            priority_options,
                            index=priority_options.index(selected) if selected in priority_options else 2,
                            key=f"{key_base}_priority",
                        )
                    content_value = st.text_input("내용", value=entry.get("content", ""), key=f"{key_base}_content")
                    a, b = st.columns(2)
                    with a:
                        if st.button("저장", key=f"{key_base}_save", use_container_width=True):
                            daily[bucket][index] = {
                                "time": time_value.strip(),
                                "priority": priority_value,
                                "content": content_value.strip(),
                            }
                            write_daily_record(date_key, daily)
                            st.rerun()
                    with b:
                        if st.button("삭제", key=f"{key_base}_delete", use_container_width=True):
                            daily[bucket].pop(index)
                            write_daily_record(date_key, daily)
                            st.rerun()
                else:
                    c1, c2 = st.columns([1.2, 1.8])
                    with c1:
                        selected = entry.get("priority", "보통")
                        priority_value = st.selectbox(
                            "중요도",
                            priority_options,
                            index=priority_options.index(selected) if selected in priority_options else 2,
                            key=f"{key_base}_priority",
                        )
                    with c2:
                        content_value = st.text_input("내용", value=entry.get("content", ""), key=f"{key_base}_content")
                    a, b = st.columns(2)
                    with a:
                        if st.button("저장", key=f"{key_base}_save", use_container_width=True):
                            daily[bucket][index] = {
                                "priority": priority_value,
                                "content": content_value.strip(),
                            }
                            write_daily_record(date_key, daily)
                            st.rerun()
                    with b:
                        if st.button("삭제", key=f"{key_base}_delete", use_container_width=True):
                            daily[bucket].pop(index)
                            write_daily_record(date_key, daily)
                            st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

    if st.button("수정 닫기", key=f"close_edit_{date_key}", use_container_width=True):
        st.session_state.sidebar_edit_date = None
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

def render_topbar() -> None:
    st.markdown(
        """
        <div class='topbar'>
          <div class='topbar-brand'>DAYPILOT AGENT</div>
          <div class='topbar-menu'>
            <span>TODAY</span>
            <span>PLANNER</span>
            <span>FOCUS</span>
            <span>BALANCE</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.session_state.setdefault("sidebar_manage_date", datetime.now().date())
        st.session_state.setdefault("sidebar_edit_date", None)
        if "sidebar_manage_date_pending" in st.session_state:
            st.session_state.sidebar_manage_date = st.session_state.pop("sidebar_manage_date_pending")
        st.markdown("## DayPilot Agent")
        ok, message = get_secret_status()
        sample_title = "샘플 입력"
        sample_body = "처음 실행할 때 바로 결과를 확인할 수 있도록 예시 데이터를 준비했습니다."
        sample_button = "예시 입력 불러오기"
        point_title = "서비스 포인트"
        point_body = "메인에서는 오늘 일정만 관리하고, 다른 날짜 일정은 사이드바에서 저장·수정·삭제할 수 있습니다."
        saved_title = "저장된 일정"
        saved_body = "오늘 항목 불러오기 또는 날짜별 카드 수정으로 빠르게 관리할 수 있습니다."
        open_label = "수정"
        delete_label = "삭제"

        st.markdown("<div class='sidebar-section-label'>빠른 시작</div><div class='sidebar-block'>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class='sidebar-card'>
              <h4>{sample_title}</h4>
              <p>{sample_body}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(sample_button, use_container_width=True):
            load_sample()
            st.rerun()
        if ok:
            st.success(message)
        else:
            st.warning(message)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='sidebar-section-label'>서비스 안내</div><div class='sidebar-block'>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class='sidebar-card'>
              <h4>{point_title}</h4>
              <p>{point_body}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='sidebar-section-label'>일정 관리</div><div class='sidebar-block'>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='sidebar-card'><h4>{saved_title}</h4><p>{saved_body}</p></div>",
            unsafe_allow_html=True,
        )
        if st.button("오늘 항목 불러오기", key="sidebar_load_today", use_container_width=True):
            load_today_from_sidebar()

        manage_date = st.date_input("다른 날짜 일정 추가", key="sidebar_manage_date")
        add_kind = st.selectbox("추가 항목", ["업무 일정", "개인 일정", "마감 업무", "해야 할 업무"], key="sidebar_add_kind")
        add_cols = st.columns([1.25, 1.25, 2.2, 0.9])
        with add_cols[0]:
            add_time = st.text_input("시간", key="sidebar_add_time", value="09:00")
        with add_cols[1]:
            add_priority = st.selectbox("중요도", ["최우선", "중요", "보통"], key="sidebar_add_priority")
        with add_cols[2]:
            add_content = st.text_input("일정 내용", key="sidebar_add_content", placeholder="예: 고객사 미팅")
        with add_cols[3]:
            st.write("")
            if st.button("추가", key="sidebar_add_submit", use_container_width=True):
                date_key = manage_date.strftime("%Y-%m-%d")
                daily = get_daily_record(date_key)
                if add_kind == "해야 할 업무":
                    if add_content.strip():
                        daily["task_items"].append({"priority": add_priority, "content": add_content.strip()})
                elif add_time.strip() and add_content.strip():
                    bucket = {
                        "업무 일정": "work_schedule",
                        "개인 일정": "personal_schedule",
                        "마감 업무": "deadline_items",
                    }[add_kind]
                    daily[bucket].append({"time": add_time.strip(), "priority": add_priority, "content": add_content.strip()})
                write_daily_record(date_key, daily)
                st.session_state.sidebar_edit_date = date_key
                st.rerun()

        saved_dates = recent_saved_dates()
        for date_key in saved_dates:
            with st.container():
                preview_text = saved_schedule_preview(date_key)
                st.markdown("<div class='sidebar-saved-wrap'>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='sidebar-card'><h4>{html.escape(date_key)}</h4><p>{preview_text}</p></div>",
                    unsafe_allow_html=True,
                )
                st.markdown("<div class='sidebar-saved-actions'>", unsafe_allow_html=True)
                action_left, action_right = st.columns(2)
                with action_left:
                    if st.button(open_label, key=f"open_{date_key}", use_container_width=True):
                        open_saved_date(date_key)
                with action_right:
                    if st.button(delete_label, key=f"delete_{date_key}", use_container_width=True):
                        delete_saved_date(date_key)
                st.markdown("</div>", unsafe_allow_html=True)
                if st.session_state.get("sidebar_edit_date") == date_key:
                    render_sidebar_date_editor(date_key)
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

def render_header() -> None:
    st.markdown(
        """
        <div class='hero-card'>
          <h1 class='hero-title'>DayPilot Agent</h1>
          <div class='hero-subtitle'>업무와 일상을 함께 정리하는 AI Daily Planner</div>
          <p class='hero-body'>회의, 마감 업무, 개인 일정, 컨디션을 한 번에 입력하면 오늘의 실행 계획과 누락 방지 체크리스트를 자동으로 생성합니다.</p>
          <div class='hero-pills'>
            <span class='hero-pill'>일정 통합</span>
            <span class='hero-pill'>우선순위 분석</span>
            <span class='hero-pill'>퇴근시간 고려</span>
            <span class='hero-pill'>컨디션 반영</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_today_summary() -> None:
    weather_name = st.session_state.location
    weather_text = "위치를 입력하면 날씨를 가져옵니다."
    try:
        info = fetch_weather(st.session_state.location)
        if info:
            weather_name = info["name"]
            weather_text = f"{info['description']} · {info['temperature']}"
    except Exception:
        weather_text = "날씨를 불러오지 못했습니다."

    cards = [
        ("TODAY", str(st.session_state.selected_date), datetime.now().strftime("%A")),
        ("WEATHER", weather_name, weather_text),
        ("OFF TIME", st.session_state.target_leave_time, "목표 퇴근시간"),
        ("FOCUS TIP", "업무 집중 팁", today_focus_tip(st.session_state.condition, st.session_state.concerns)),
    ]
    cols = st.columns(4)
    for col, (label, main, sub) in zip(cols, cards):
        with col:
            st.markdown(
                f"<div class='today-card'><div class='today-label'>{html.escape(label)}</div><div class='today-main'>{html.escape(str(main))}</div><div class='today-sub'>{html.escape(str(sub))}</div></div>",
                unsafe_allow_html=True,
            )


def render_schedule_manager(title: str, key_name: str, help_text: str) -> None:
    st.markdown(f"<div class='subtle-heading'>{html.escape(title)}</div>", unsafe_allow_html=True)
    st.markdown(f"<p class='helper-text'>{html.escape(help_text)}</p>", unsafe_allow_html=True)
    entries = st.session_state[key_name]

    c1, c2, c3, c4 = st.columns([1.15, 1.05, 3.25, 1.0])
    with c1:
        time_value = st.text_input("시간", key=f"{key_name}_new_time", placeholder="09:00")
    with c2:
        priority_value = st.selectbox("중요도", ["최우선", "중요", "보통"], key=f"{key_name}_new_priority")
    with c3:
        content_value = st.text_input("일정 내용", key=f"{key_name}_new_content", placeholder="예: 고객사 미팅")
    with c4:
        st.write("")
        if st.button("추가", key=f"{key_name}_add", use_container_width=True):
            if time_value.strip() and content_value.strip():
                st.session_state[key_name].append(
                    {"time": time_value.strip(), "priority": priority_value, "content": content_value.strip()}
                )
                st.rerun()
            else:
                st.warning("시간과 일정 내용을 입력해 주세요.")

    st.markdown("<div style='height:.35rem;'></div>", unsafe_allow_html=True)

    if entries:
        for index, entry in enumerate(sorted(entries, key=lambda item: item["time"])):
            left, right = st.columns([8.7, 1.3])
            with left:
                st.markdown(
                    f"<div class='schedule-card'><div class='schedule-top'><span class='time-pill'>{html.escape(entry['time'])}</span><span class='priority-pill {priority_tone_class(entry['priority'])}'>{html.escape(entry['priority'])}</span></div><div class='schedule-text'>{html.escape(entry['content'])}</div></div>",
                    unsafe_allow_html=True,
                )
            with right:
                if st.button("삭제", key=f"{key_name}_remove_{index}", use_container_width=True):
                    st.session_state[key_name].pop(index)
                    st.rerun()
    else:
        st.info(f"{title}이 아직 없습니다. 위에서 추가해 보세요.")



def render_task_manager(title: str, key_name: str, help_text: str) -> None:
    st.markdown(f"<div class='subtle-heading'>{html.escape(title)}</div>", unsafe_allow_html=True)
    st.markdown(f"<p class='helper-text'>{html.escape(help_text)}</p>", unsafe_allow_html=True)
    entries = st.session_state[key_name]

    c1, c2, c3 = st.columns([1.2, 3.8, 1.0])
    with c1:
        priority_value = st.selectbox("중요도", ["최우선", "중요", "보통"], key=f"{key_name}_new_priority")
    with c2:
        content_value = st.text_input("업무 내용", key=f"{key_name}_new_content", placeholder="예: 제안서 수정")
    with c3:
        st.write("")
        if st.button("추가", key=f"{key_name}_add", use_container_width=True):
            if content_value.strip():
                st.session_state[key_name].append({"priority": priority_value, "content": content_value.strip()})
                st.rerun()
            else:
                st.warning("업무 내용을 입력해 주세요.")

    st.markdown("<div style='height:.35rem;'></div>", unsafe_allow_html=True)

    if entries:
        for index, entry in enumerate(entries):
            left, right = st.columns([8.7, 1.3])
            with left:
                st.markdown(
                    f"<div class='schedule-card'><div class='schedule-top'><span class='priority-pill {priority_tone_class(entry['priority'])}'>{html.escape(entry['priority'])}</span></div><div class='schedule-text'>{html.escape(entry['content'])}</div></div>",
                    unsafe_allow_html=True,
                )
            with right:
                if st.button("삭제", key=f"{key_name}_remove_{index}", use_container_width=True):
                    st.session_state[key_name].pop(index)
                    st.rerun()
    else:
        st.info(f"{title}이 아직 없습니다. 위에서 추가해 보세요.")



def render_deadline_manager(title: str, key_name: str, help_text: str) -> None:
    st.markdown(f"<div class='subtle-heading'>{html.escape(title)}</div>", unsafe_allow_html=True)
    st.markdown(f"<p class='helper-text'>{html.escape(help_text)}</p>", unsafe_allow_html=True)
    entries = st.session_state[key_name]

    c1, c2, c3, c4 = st.columns([1.15, 1.05, 3.05, 1.0])
    with c1:
        time_value = st.text_input("마감 시간", key=f"{key_name}_new_time", placeholder="17:00")
    with c2:
        priority_value = st.selectbox("중요도", ["최우선", "중요", "보통"], key=f"{key_name}_new_priority")
    with c3:
        content_value = st.text_input("마감 업무 내용", key=f"{key_name}_new_content", placeholder="예: 고객사 제안서 제출")
    with c4:
        st.write("")
        if st.button("추가", key=f"{key_name}_add", use_container_width=True):
            if time_value.strip() and content_value.strip():
                st.session_state[key_name].append(
                    {"time": time_value.strip(), "priority": priority_value, "content": content_value.strip()}
                )
                st.rerun()
            else:
                st.warning("마감 시간과 업무 내용을 입력해 주세요.")

    st.markdown("<div style='height:.35rem;'></div>", unsafe_allow_html=True)

    if entries:
        for index, entry in enumerate(sorted(entries, key=lambda item: item["time"])):
            left, right = st.columns([8.7, 1.3])
            with left:
                st.markdown(
                    f"<div class='schedule-card'><div class='schedule-top'><span class='time-pill'>{html.escape(entry['time'])}</span><span class='priority-pill {priority_tone_class(entry['priority'])}'>{html.escape(entry['priority'])}</span></div><div class='schedule-text'>{html.escape(entry['content'])}</div></div>",
                    unsafe_allow_html=True,
                )
            with right:
                if st.button("삭제", key=f"{key_name}_remove_{index}", use_container_width=True):
                    st.session_state[key_name].pop(index)
                    st.rerun()
    else:
        st.info(f"{title}이 아직 없습니다. 위에서 추가해 보세요.")



def render_input_area() -> None:
    today = datetime.now().date()
    if st.session_state.selected_date != today:
        st.session_state.selected_date = today
        st.session_state.selected_date_picker = today
        st.session_state.loaded_plan_date = None

    sync_selected_plan()
    st.markdown("<div class='section-heading'>일정과 조건 입력</div>", unsafe_allow_html=True)

    top_box = st.container(border=True)
    with top_box:
        top1, top2, top3, top4 = st.columns([1.1, 1.0, 0.95, 0.95])
        with top1:
            st.text_input("기준 날짜", value=str(today), disabled=True)
        with top2:
            st.text_input("위치", key="location_input", placeholder="예: Seoul")
        with top3:
            st.text_input("목표 퇴근시간", key="target_leave_time_input", placeholder="예: 18:30")
        with top4:
            st.selectbox("집중 블록 길이", [25, 45, 60, 90], key="focus_block_input")

        st.session_state.location = st.session_state.location_input
        st.session_state.target_leave_time = st.session_state.target_leave_time_input
        st.session_state.focus_block = st.session_state.focus_block_input

        save_col, info_col = st.columns([1.1, 2.9])
        with save_col:
            if st.button("오늘 계획 저장", use_container_width=True):
                save_current_plan()
                st.success("오늘 날짜 기준 계획을 저장했습니다.")
        with info_col:
            st.caption("메인 화면에서는 오늘 일정만 바로 추가할 수 있고, 다른 날짜 일정은 사이드바에서 관리합니다.")

    schedule_box = st.container(border=True)
    with schedule_box:
        upper_left, upper_right = st.columns(2)
        with upper_left:
            with st.container(border=True):
                render_schedule_manager(
                "업무 일정",
                "work_schedule",
                "회의, 보고, 협업 일정처럼 업무와 관련된 고정 일정을 입력하세요.",
            )
        with upper_right:
            with st.container(border=True):
                render_schedule_manager(
                "개인 일정",
                "personal_schedule",
                "병원, 운동, 약속처럼 업무 외 고정 일정을 입력하세요.",
            )

    task_box = st.container(border=True)
    with task_box:
        mid_left, mid_right = st.columns(2)
        with mid_left:
            with st.container(border=True):
                render_task_manager(
                "해야 할 업무",
                "task_items",
                "오늘 처리하고 싶은 일반 업무나 정리 업무를 추가해 주세요.",
            )
        with mid_right:
            with st.container(border=True):
                render_deadline_manager(
                "마감 업무",
                "deadline_items",
                "반드시 끝내야 하는 업무와 마감 시간을 추가해 주세요.",
            )

    condition_box = st.container(border=True)
    with condition_box:
        lower_left, lower_right = st.columns(2)
        with lower_left:
            st.markdown("<div class='subtle-heading'>컨디션</div>", unsafe_allow_html=True)
            st.markdown(
                "<p class='helper-text'>오늘의 집중력, 피로도, 이동 일정 등을 적어주세요.</p>",
                unsafe_allow_html=True,
            )
            st.text_area(
                "컨디션",
                key="condition",
                height=160,
                label_visibility="collapsed",
                placeholder="예: 오전 집중도 높음, 오후 피로감 있음",
            )
        with lower_right:
            st.markdown("<div class='subtle-heading'>고민되는 점</div>", unsafe_allow_html=True)
            st.markdown(
                "<p class='helper-text'>우선순위 판단이나 시간 배분에서 고민되는 점을 적어주세요.</p>",
                unsafe_allow_html=True,
            )
            st.text_area(
                "고민되는 점",
                key="concerns",
                height=160,
                label_visibility="collapsed",
                placeholder="예: 급한 일만 처리하다가 중요한 일이 밀림",
            )

    if st.button("AI로 오늘 계획 생성하기", use_container_width=True, type="primary"):
        save_current_plan()
        payload = {
            "today": str(st.session_state.selected_date),
            "location": st.session_state.location.strip(),
            "target_leave_time": st.session_state.target_leave_time.strip(),
            "focus_block": str(st.session_state.focus_block),
            "work_schedule": schedule_text(st.session_state.work_schedule),
            "personal_schedule": schedule_text(st.session_state.personal_schedule),
            "tasks": task_text(st.session_state.task_items),
            "deadline_tasks": deadline_text(st.session_state.deadline_items),
            "condition": st.session_state.condition.strip(),
            "concerns": st.session_state.concerns.strip(),
        }
        with st.spinner("일정 충돌과 마감 업무 우선순위를 분석하는 중입니다..."):
            try:
                plan = generate_plan(payload)
                st.session_state.generated_plan = plan
                st.session_state.generated_markdown = build_markdown(plan)
            except Exception as exc:
                st.error(f"계획 생성 중 오류가 발생했습니다: {exc}")


def build_markdown(plan: DayPlan) -> str:
    lines = [
        "# DayPilot Agent ?? ??",
        "",
        "## ??? ?? ??",
    ]
    lines.extend(f"- {item}" for item in plan.summary)
    lines.extend([
        "",
        "## ???? TOP 5",
    ])
    lines.extend(
        f"- [{item.category}] {item.task}: {item.reason}"
        for item in plan.priorities[:5]
    )
    lines.extend([
        "",
        "## ?? ?? ??",
    ])
    lines.extend(f"{idx}. {item}" for idx, item in enumerate(plan.execution_order[:8], start=1))
    lines.extend([
        "",
        "## ???? ?? ??",
    ])
    lines.extend(
        f"- {block.time} | {block.plan} | {block.focus}"
        for block in plan.time_blocks
    )
    lines.extend([
        "",
        "## ?? ?? ?????",
    ])
    lines.extend(f"- [ ] {item}" for item in plan.checklist)
    lines.extend([
        "",
        "## ?? ?? ??",
        plan.share_message,
        "",
        "## ??? ?? ??",
        plan.balance_advice,
    ])
    return "\n".join(lines)


def render_html_table(headers: list[str], rows: list[list[str]]) -> None:
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    st.markdown(
        "<table class='k-table'><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>",
        unsafe_allow_html=True,
    )


def render_execution_flow(items: list[str]) -> None:
    cards = [
        f"<div class='flow-card'><div class='flow-step'>STEP {index}</div><div class='flow-text'>{html.escape(item)}</div></div>"
        for index, item in enumerate(items[:8], start=1)
    ]
    st.markdown("<div class='flow-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def render_time_blocks(blocks: list[TimeBlock]) -> None:
    rows = []
    for block in blocks:
        rows.append(
            "<div class='timeline-card'>"
            f"<div class='timeline-time'>{html.escape(block.time)}</div>"
            "<div>"
            f"<div class='timeline-plan'>{html.escape(block.plan)}</div>"
            f"<div class='timeline-focus'>{html.escape(block.focus)}</div>"
            "</div></div>"
        )
    st.markdown("<div class='timeline'>" + "".join(rows) + "</div>", unsafe_allow_html=True)


def render_dashboard(plan: DayPlan) -> None:
    cards = [
        ("최우선 업무", plan.dashboard.top_task, "오늘 가장 먼저 챙길 일"),
        ("마감 위험도", plan.dashboard.deadline_risk, "오늘 마감 기준"),
        ("집중 필요 시간", plan.dashboard.focus_need, "몰입이 필요한 구간"),
        ("퇴근 가능성", plan.dashboard.leave_feasibility, "목표 퇴근시간 기준"),
    ]
    html_cards = []
    for label, value, sub in cards:
        html_cards.append(
            "<div class='dashboard-card'>"
            f"<div class='dashboard-label'>{html.escape(label)}</div>"
            f"<div class='dashboard-value'>{html.escape(value)}</div>"
            f"<div class='dashboard-sub'>{html.escape(sub)}</div>"
            "</div>"
        )
    st.markdown("<div class='dashboard-grid'>" + "".join(html_cards) + "</div>", unsafe_allow_html=True)


def render_checklist(items: list[str]) -> None:
    for item in items:
        st.markdown(f"☐ {html.escape(item)}")


def render_suggestions() -> None:
    ideas = [
        (
            "이동·회의 전후 버퍼 자동 배치",
            "이동이나 회의 사이에 짧은 정리 시간을 자동으로 넣어 과부하를 줄일 수 있습니다.",
        ),
        (
            "목표 퇴근시간 기준 업무 재배치",
            "퇴근 목표에 맞춰 집중 작업과 마감 업무 순서를 다시 정리하도록 확장할 수 있습니다.",
        ),
        (
            "자주 쓰는 일정 세트 저장",
            "반복되는 업무 루틴을 저장해 다음 계획을 더 빠르게 작성할 수 있습니다.",
        ),
    ]
    st.markdown(
        "<div class='section-heading'>더 스마트한 하루 관리를 위한 기능</div>",
        unsafe_allow_html=True,
    )
    columns = st.columns(3)
    for column, (title, body) in zip(columns, ideas):
        with column:
            st.markdown(
                f"<div class='suggestion-card'><div class='suggestion-title'>{html.escape(title)}</div><p class='suggestion-body'>{html.escape(body)}</p></div>",
                unsafe_allow_html=True,
            )


def render_result() -> None:
    plan: DayPlan | None = st.session_state.get("generated_plan")
    if not plan:
        return

    st.markdown("<div class='result-shell'>", unsafe_allow_html=True)
    render_dashboard(plan)
    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)

    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>📌 오늘의 핵심 요약</div>", unsafe_allow_html=True)
    summary = "".join(
        f"<div class='summary-item'>{html.escape(item)}</div>" for item in plan.summary
    )
    st.markdown(f"<div class='summary-grid'>{summary}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>🚦 우선순위 TOP 5</div>", unsafe_allow_html=True)
    render_html_table(
        ["구분", "업무", "이유"],
        [
            [
                f"<span class='chip'>{html.escape(item.category)}</span>",
                html.escape(item.task),
                html.escape(item.reason),
            ]
            for item in plan.priorities[:5]
        ],
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>🧭 추천 실행 순서</div>", unsafe_allow_html=True)
    render_execution_flow(plan.execution_order)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>🕒 시간대별 하루 계획</div>", unsafe_allow_html=True)
    render_time_blocks(plan.time_blocks)
    st.markdown("</div>", unsafe_allow_html=True)

    left_col, right_col = st.columns([1.25, 1.0])
    with left_col:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown("<div class='section-heading'>✅ 누락 방지 체크리스트</div>", unsafe_allow_html=True)
        render_checklist(plan.checklist)
        st.markdown("</div>", unsafe_allow_html=True)
    with right_col:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown("<div class='section-heading'>💬 업무 공유 문구</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='message-card'>{html.escape(plan.share_message)}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>🌿 오늘의 균형 조언</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='advice-card'>{html.escape(plan.balance_advice)}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.download_button(
        "오늘 계획 Markdown으로 저장하기",
        data=st.session_state.generated_markdown,
        file_name=f"daypilot-plan-{st.session_state.selected_date}.md",
        mime="text/markdown",
        use_container_width=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

def main() -> None:
    init_state()
    inject_styles()
    render_sidebar()
    render_topbar()
    render_header()
    render_today_summary()
    render_input_area()
    render_result()
    render_suggestions()


if __name__ == "__main__":
    main()

