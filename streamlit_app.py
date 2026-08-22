"""
streamlit_app.py — 사주풀이 웹앱 (Streamlit)

계산 엔진은 saju_app.py 를 그대로 가져다 씁니다. 이 파일은 UI/UX 만 담당합니다.
실행:
    streamlit run streamlit_app.py
"""

import io
import json
import re
import threading
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

from saju_app import (
    build_chart,
    analyze,
    analyze_v2,
    score_all_daeun,
    score_all_daeun_v2,
    score_seun_range,
    render_text,
    render_text_v2,
    export_dict,
    export_json,
    export_text,
    list_cities,
    JASI_SCHOOLS,
    ILGAN_DESC,
    OHAENG_ADVICE,
    OHAENG,
    JIJANGGAN,
    GAN_H,
    _theme,
    _conclusion,
    strength_robustness,
    scan_daeun_hwaguk,
    __version__,
    DISCLAIMER,
    LOG_WEBHOOK_URL,
    LOG_INCLUDE_IP,
    LOG_TIMEOUT_SEC,
    IP_LOOKUP_URL,
    IP_LOOKUP_TIMEOUT_SEC,
)


GRADE_FRIENDLY = {
    "매우 좋음": {
        "label": "순항기",
        "desc": "흐름이 나를 밀어주는 시기",
        "tip": "기회가 왔을 때 과감하게 나아가 보세요.",
    },
    "좋음": {
        "label": "순조로운 시기",
        "desc": "무리 없이 나아가는 시기",
        "tip": "지금의 흐름을 믿고 계획을 실행해보세요.",
    },
    "보통": {
        "label": "평이한 시기",
        "desc": "특별한 순풍도 역풍도 없는 시기",
        "tip": "루틴을 지키며 다음 기회를 준비하기 좋은 때입니다.",
    },
    "어려움": {
        "label": "단련기",
        "desc": "노력이 평소보다 더 필요한 시기",
        "tip": "무리한 확장보다 기초를 다지는 데 집중해보세요.",
    },
    "매우 어려움": {
        "label": "심화 단련기",
        "desc": "마찰이 크지만, 그만큼 다져지는 시기",
        "tip": "큰 결정은 신중히, 대신 내공을 쌓는 시간으로 삼아보세요.",
    },
}


def friendly_grade_label(raw_grade):
    """'매우 어려움' → '심화 단련기 (구: 매우 어려움)'. 화면 표시 전용."""
    info = GRADE_FRIENDLY.get(raw_grade)
    if not info:
        return raw_grade
    return f"{info['label']} ({raw_grade})"


def grade_caption(raw_grade):
    info = GRADE_FRIENDLY.get(raw_grade)
    if not info:
        return ""
    return f"{info['desc']} · {info['tip']}"


GRADE_LEGEND_TEXT = (
    "○ 등급 이름 안내\n"
    "  이 리포트의 '등급'은 좋고 나쁨을 매기는 게 아니라, 그 시기에 필요한\n"
    "  태도를 알려주는 이름입니다. 전통 명리 용어도 괄호로 함께 적어둡니다.\n"
    + "\n".join(
        f"  · {info['label']} ({raw}) — {info['desc']}. {info['tip']}"
        for raw, info in GRADE_FRIENDLY.items()
    )
    + "\n"
)


_GRADE_LINE_RE = re.compile(
    r"([█░]{20} )("
    + "|".join(re.escape(g) for g in sorted(GRADE_FRIENDLY, key=len, reverse=True))
    + r")"
)


def patch_grade_lines(text):
    def _sub(m):
        return m.group(1) + friendly_grade_label(m.group(2))
    return _GRADE_LINE_RE.sub(_sub, text)


st.set_page_config(
    page_title="사주풀이",
    page_icon="🀄",
    layout="centered",
    initial_sidebar_state="collapsed",
)

FONT_PATH = "fonts/NotoSansKR-Regular.ttf"
try:
    pdfmetrics.registerFont(TTFont("NotoSansKR", FONT_PATH))
    _PDF_FONT_OK = True
except Exception:
    _PDF_FONT_OK = False


CUSTOM_CSS = """
<style>
:root {
    --hanji-bg: #FBF7EE;
    --hanji-card: #FAEEDA;
    --ink: #2C2C2A;
    --ink-soft: #5F5E5A;
    --seal: #D85A30;
    --seal-dark: #712B13;
    --seal-text: #4A1B0C;
    color-scheme: light;
}
.stApp {
    background-color: var(--hanji-bg);
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
        "Malgun Gothic", "Noto Sans KR", "Segoe UI", Roboto, sans-serif;
}
.block-container {
    max-width: 480px;
    padding-top: 1.5rem;
}
.app-header {
    text-align: center;
    margin-bottom: 4px;
    padding: 10px 0 4px;
    overflow: visible;
    line-height: normal;
}
.app-header .title {
    display: block;
    font-size: 26px;
    line-height: 1.8;
    font-weight: 700;
    letter-spacing: 1px;
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
        "Malgun Gothic", "Noto Sans KR", "Segoe UI", Roboto, sans-serif;
    overflow: visible;
}
.app-header .title svg { vertical-align: -6px; margin-right: 4px; }
.app-sub {
    text-align: center;
    color: var(--ink-soft);
    font-size: 13px;
    margin-bottom: 20px;
}
.chip-row { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; margin-bottom: 8px; }
.chip {
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 8px;
    background: var(--hanji-card);
    color: var(--ink-soft);
    border: 0.5px solid rgba(128,128,128,0.25);
}
.v2-card {
    background: var(--hanji-card);
    border-left: 3px solid var(--seal);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 14px;
}
.v2-badge {
    display: inline-block;
    font-size: 12px;
    padding: 3px 10px;
    border-radius: 8px;
    background: var(--seal);
    color: var(--hanji-bg);
    font-weight: 700;
    margin-bottom: 8px;
}
.v2-title { font-size: 18px; font-weight: 700; color: var(--seal-text); margin: 0 0 4px; }
.v2-desc { font-size: 13px; color: var(--seal-dark); line-height: 1.6; }
.ai-box {
    background: var(--hanji-card);
    border-radius: 10px;
    padding: 12px 14px;
    font-size: 13px;
    color: var(--ink-soft);
    line-height: 1.7;
}
.timeline-bar {
    display: flex;
    height: 34px;
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 4px;
    font-size: 13px;
}
.timeline-bar > div { flex: 1; display: flex; align-items: center; justify-content: center; }
h1, h2, h3 { color: var(--ink) !important; }

.pillar-table { width: 100%; border-collapse: collapse; margin-bottom: 14px; table-layout: fixed; }
.pillar-table th, .pillar-table td {
    border: 0.5px solid rgba(128,128,128,0.25);
    text-align: center;
    padding: 6px 2px;
    font-size: 12px;
    color: var(--ink);
    word-break: keep-all;
}
.pillar-table th { background: var(--hanji-card); color: var(--ink-soft); font-weight: 500; }
.pillar-table td.hanja { font-size: 22px; font-weight: 700; padding: 8px 2px; }
.pillar-table td.label { color: var(--ink-soft); font-size: 11px; }

.elem-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.elem-row .name { width: 28px; font-size: 13px; color: var(--ink-soft); flex-shrink: 0; }
.elem-row .bar-bg { display: block; flex: 1; height: 12px; border-radius: 6px; background: var(--hanji-card); overflow: hidden; }
.elem-row .bar-fill { display: block; height: 100%; background: var(--seal); border-radius: 6px; }
.elem-row .val { width: 34px; font-size: 12px; color: var(--ink-soft); text-align: right; flex-shrink: 0; }

.info-block {
    background: var(--hanji-card);
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 12px;
    font-size: 13px;
    color: var(--ink);
    line-height: 1.7;
}
.info-block .label { color: var(--ink-soft); font-size: 12px; }

.chip-yong { background: #EAF3DE; color: #27500A; }
.chip-gi { background: #FAECE7; color: #4A1B0C; }
.chip-neu { background: rgba(128,128,128,0.15); color: var(--ink-soft); }

.reason-list { font-size: 13px; color: var(--ink); line-height: 1.8; padding-left: 18px; margin: 0 0 12px; }

.daeun-bar-bg { display: block; flex: 1; height: 10px; border-radius: 5px; background: rgba(128,128,128,0.15); overflow: hidden; }
.daeun-bar-fill { display: block; height: 100%; background: var(--seal); border-radius: 5px; }

.seun-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px; }
.seun-table th, .seun-table td {
    border: 0.5px solid rgba(128,128,128,0.2);
    padding: 5px 4px;
    text-align: center;
    color: var(--ink);
}
.seun-table th { background: var(--hanji-card); color: var(--ink-soft); font-weight: 500; }
.seun-table td.current { background: var(--hanji-card); font-weight: 700; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown(
    "<div class='app-header'><span class='title'>사주풀이</span></div>"
    "<div class='app-sub'>생년월일시로 원국·강약·용신·대운을 풀이합니다"
    "</div>",
    unsafe_allow_html=True,
)


CITIES = list_cities()
DEFAULT_CITY_IDX = CITIES.index("서울") if "서울" in CITIES else 0

CUR_YEAR = date.today().year
YEARS = list(range(CUR_YEAR, 1899, -1))
DEFAULT_YEAR_IDX = YEARS.index(1980) if 1980 in YEARS else 0

st.markdown(
    "<p style='font-size:13px; color:var(--ink-soft); margin:0 0 6px;'>생년월일 (양력)</p>",
    unsafe_allow_html=True,
)
dc1, dc2, dc3 = st.columns(3)
birth_year = dc1.selectbox(
    "년", YEARS, index=DEFAULT_YEAR_IDX, format_func=lambda y: f"{y}년",
    label_visibility="collapsed",
)
birth_month = dc2.selectbox(
    "월", list(range(1, 13)), index=0, format_func=lambda m: f"{m}월",
    label_visibility="collapsed",
)
birth_day = dc3.selectbox(
    "일", list(range(1, 32)), index=0, format_func=lambda d: f"{d}일",
    label_visibility="collapsed",
)

st.markdown(
    "<p style='font-size:13px; color:var(--ink-soft); margin:10px 0 6px;'>"
    "태어난 시각 (모를 경우 12시로 선택해주세요)</p>",
    unsafe_allow_html=True,
)
tc1, tc2 = st.columns(2)
birth_hour = tc1.selectbox(
    "시", list(range(0, 24)), index=12, format_func=lambda h: f"{h}시",
    label_visibility="collapsed",
)
birth_minute = tc2.selectbox(
    "분", list(range(0, 60)), index=0, format_func=lambda m: f"{m}분",
    label_visibility="collapsed",
)

gc1, gc2 = st.columns(2)
with gc1:
    gender_label = st.radio("성별", ["남", "여"], horizontal=True)
with gc2:
    place = st.selectbox("태어난 지역", CITIES, index=DEFAULT_CITY_IDX)

st.session_state.setdefault("jasi_school", list(JASI_SCHOOLS)[0])
st.session_state.setdefault("apply_longitude", True)
st.session_state.setdefault("apply_eot", False)
jasi_school = st.session_state["jasi_school"]
apply_longitude = st.session_state["apply_longitude"]
apply_eot = st.session_state["apply_eot"]

current_input_hash = hash((
    birth_year, birth_month, birth_day, birth_hour, birth_minute,
    gender_label, place, jasi_school, apply_longitude, apply_eot,
))
already_computed = (
    "chart" in st.session_state
    and st.session_state.get("last_input_hash") == current_input_hash
)

st.markdown("<a name='top-of-form'></a>", unsafe_allow_html=True)
submitted = st.button(
    "사주 풀이 보기", use_container_width=True, disabled=already_computed,
)
if already_computed:
    st.caption("✓ 이 입력값으로 이미 계산했어요. 값을 바꾸면 다시 눌러보실 수 있어요.")

def _log_usage(chart):
    """[접속일시(KST), 성별, 연도, 월, 일, 시, 장소, IP] 한 줄을 구글시트 'log'
    탭에 남깁니다. 웹 요청을 막지 않도록 별도 스레드에서 실행하고, 실패해도
    (오프라인·URL 미설정·응답 지연 등) 계산 결과 표시에는 영향을 주지 않습니다.

    st.secrets["LOG_SECRET"]에 등록된 비밀 토큰을 함께 보내고, Apps Script
    쪽에서 이 토큰이 일치할 때만 기록하도록 해서 URL만 아는 제3자가 가짜
    로그를 대량으로 남기지 못하게 막습니다. 이 값은 서버(Python)에서만
    쓰이고 브라우저로는 전달되지 않아 개발자도구로도 볼 수 없습니다.
    """
    if not LOG_WEBHOOK_URL:
        return
    try:
        log_secret = st.secrets.get("LOG_SECRET", "")
    except Exception:
        log_secret = ""
    if not log_secret:
        return

    def _send():
        try:
            client_ip = ""
            if LOG_INCLUDE_IP:
                try:
                    with urllib.request.urlopen(
                            IP_LOOKUP_URL, timeout=IP_LOOKUP_TIMEOUT_SEC) as resp:
                        client_ip = json.loads(resp.read().decode("utf-8")).get("ip", "")
                except Exception:
                    client_ip = ""
            access_kst = datetime.now(ZoneInfo("Asia/Seoul"))
            payload = {
                "secret": log_secret,
                "access_time_kst": access_kst.strftime("%Y-%m-%d %H:%M:%S"),
                "gender": "남성" if chart.is_male else "여성",
                "birth_year": chart.birth_local.year,
                "birth_month": chart.birth_local.month,
                "birth_day": chart.birth_local.day,
                "birth_hour": chart.birth_local.hour,
                "place": chart.place.name,
                "client_ip": client_ip,
            }
            req = urllib.request.Request(
                LOG_WEBHOOK_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=LOG_TIMEOUT_SEC)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


if submitted:
    try:
        chart = build_chart(
            birth_year, birth_month, birth_day,
            birth_hour, birth_minute,
            is_male=(gender_label == "남"),
            place=place,
            jasi_school=jasi_school,
            apply_longitude=apply_longitude,
            apply_eot=apply_eot,
        )
        st.session_state["chart"] = chart
        st.session_state["last_input_hash"] = current_input_hash
        _log_usage(chart)
        st.rerun()
    except Exception as e:
        st.error(f"계산 중 문제가 발생했습니다: {e}")
        st.session_state.pop("chart", None)
        st.session_state.pop("last_input_hash", None)


def render_pillars_table_html(chart):
    """원국(년·월·일·시) 표를 HTML 테이블로."""
    labels = ["년주", "월주", "일주", "시주"]
    pillars = chart.pillars
    sip = chart.sipseong_map()
    uns = chart.unseong_map()
    sip_keys_gan = ["년간", "월간", "일간", "시간"]
    sip_keys_ji = ["년지", "월지", "일지", "시지"]
    uns_keys = ["년", "월", "일", "시"]

    def jjg_text(p):
        return "·".join(GAN_H[g] for g, _ in JIJANGGAN[p.ji])

    rows = [
        ("천간", [GAN_H[p.gan] for p in pillars], "hanja"),
        ("지지", [chart.pillars[i].hanja[1] for i in range(4)], "hanja"),
        ("십성(간)", [sip[k] for k in sip_keys_gan], "label"),
        ("십성(지)", [sip[k] for k in sip_keys_ji], "label"),
        ("지장간", [jjg_text(p) for p in pillars], "label"),
        ("십이운성", [uns[k] for k in uns_keys], "label"),
    ]

    head = "<tr><th></th>" + "".join(f"<th>{lb}</th>" for lb in labels) + "</tr>"
    body = ""
    for row_label, values, cls in rows:
        cells = "".join(f"<td class='{cls}'>{v}</td>" for v in values)
        body += f"<tr><th>{row_label}</th>{cells}</tr>"
    return f"<table class='pillar-table'>{head}{body}</table>"


def render_element_bars_html(chart):
    """오행 분포를 막대그래프 형태 HTML로."""
    counts = chart.ohaeng_count(include_jijanggan=True)
    total = sum(counts.values()) or 1
    rows = ""
    for e in OHAENG:
        pct = counts[e] / total * 100
        rows += (
            "<div class='elem-row'>"
            f"<span class='name'>{e}</span>"
            f"<span class='bar-bg'><span class='bar-fill' style='width:{pct:.0f}%;'></span></span>"
            f"<span class='val'>{pct:.0f}%</span>"
            "</div>"
        )
    return rows


def render_strength_block_html(a2):
    st_ = a2.strength
    boundary_note = (
        f"<p class='label'>※ {st_.alt_label}과의 경계 판정입니다. "
        "계수를 조금만 바꿔도 결과가 달라질 수 있어요.</p>"
        if st_.confidence == "경계" and st_.alt_label else ""
    )
    return (
        "<div class='info-block'>"
        f"<p class='label'>강약 비율</p>"
        f"<p style='font-size:16px; font-weight:700; margin:2px 0 8px;'>"
        f"{st_.label} · 아군 {st_.ally:.1f} vs 적군 {st_.enemy:.1f} ({st_.ratio:.0%})</p>"
        f"{boundary_note}"
        "</div>"
    )


def render_yongsin_chips_html(a2):
    def chips(items, cls):
        if not items:
            return "<span class='chip chip-neu'>-</span>"
        return "".join(f"<span class='chip {cls}'>{e}</span>" for e in items)
    return (
        "<div style='margin-bottom:4px;'><span class='label' style='font-size:12px; color:var(--ink-soft);'>용신 (도움되는 기운)</span><br>"
        f"<div class='chip-row' style='justify-content:flex-start; margin-top:4px;'>{chips(a2.yongsin, 'chip-yong')}</div></div>"
        "<div style='margin:10px 0 4px;'><span class='label' style='font-size:12px; color:var(--ink-soft);'>기신 (피해야 할 기운)</span><br>"
        f"<div class='chip-row' style='justify-content:flex-start; margin-top:4px;'>{chips(a2.gisin, 'chip-gi')}</div></div>"
    )


def render_reasons_html(reasons, limit=8):
    items = "".join(f"<li>{r}</li>" for r in reasons[:limit])
    return f"<ul class='reason-list'>{items}</ul>"


def short_grade_label(raw_grade):
    info = GRADE_FRIENDLY.get(raw_grade)
    return info["label"] if info else raw_grade


def render_seun_table_html(rows, current_year):
    head = "<tr><th>연도</th><th>세운</th><th>대운</th><th>등급</th><th>%</th></tr>"
    body = ""
    for r in rows:
        cls = "current" if r["year"] == current_year else ""
        daeun_txt = r["daeun"].hanja if r["daeun"] else "-"
        body += (
            f"<tr class='{cls}'><td class='{cls}'>{r['year']}</td>"
            f"<td class='{cls}'>{r['pillar'].hanja}</td>"
            f"<td class='{cls}'>{daeun_txt}</td>"
            f"<td class='{cls}'>{short_grade_label(r['grade'])}</td>"
            f"<td class='{cls}'>{r['percent']}</td></tr>"
        )
    return f"<table class='seun-table'>{head}{body}</table>"


def render_v2_detail(chart, a2, scores2):
    st.markdown("**원국(사주 네 기둥)**", unsafe_allow_html=True)
    st.markdown(render_pillars_table_html(chart), unsafe_allow_html=True)

    st.markdown("**오행 분포** (지장간 포함 실질 비중)", unsafe_allow_html=True)
    st.markdown(render_element_bars_html(chart), unsafe_allow_html=True)

    st.markdown(render_strength_block_html(a2), unsafe_allow_html=True)
    st.markdown(render_yongsin_chips_html(a2), unsafe_allow_html=True)

    if a2.special:
        st.markdown(
            "<div class='info-block'><p class='label'>특수격(종격)</p>"
            f"<p style='margin:2px 0;'>{a2.special['name']} — {a2.special['reason']}</p></div>",
            unsafe_allow_html=True,
        )
    if a2.gyeokguk:
        st.markdown(
            "<div class='info-block'><p class='label'>격국 교차검증</p>"
            f"<p style='margin:2px 0;'>{a2.gyeokguk['note']}</p></div>",
            unsafe_allow_html=True,
        )

    st.markdown("**판정 근거**", unsafe_allow_html=True)
    st.markdown(render_reasons_html(a2.reasons), unsafe_allow_html=True)


def render_v1_detail(chart, a1, scores1):
    st.markdown("**원국(사주 네 기둥) (V1)**", unsafe_allow_html=True)
    st.markdown(render_pillars_table_html(chart), unsafe_allow_html=True)

    st.markdown("**오행 분포 (V1)**", unsafe_allow_html=True)
    st.markdown(render_element_bars_html(chart), unsafe_allow_html=True)

    st_ = a1.strength
    st.markdown(
        "<div class='info-block'>"
        "<p class='label'>강약 비율</p>"
        f"<p style='font-size:16px; font-weight:700; margin:2px 0 8px;'>"
        f"{st_.label} · 아군 {st_.ally:.1f} vs 적군 {st_.enemy:.1f} ({st_.ratio:.0%})</p>"
        f"<p class='label'>{st_.description}</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(render_yongsin_chips_html(a1), unsafe_allow_html=True)

    if a1.johu_note:
        st.markdown(
            "<div class='info-block'><p class='label'>조후(계절 기운) 보정</p>"
            f"<p style='margin:2px 0;'>{a1.johu_note}</p></div>",
            unsafe_allow_html=True,
        )

    st.markdown("**판정 근거 (V1)**", unsafe_allow_html=True)
    st.markdown(render_reasons_html(a1.reasons), unsafe_allow_html=True)

    st.markdown("**V1 분석에 따른 대운 (10년 주기) 요약**", unsafe_allow_html=True)
    today_age = date.today().year - chart.birth_local.year + 1
    st.markdown(render_daeun_table_html(scores1, today_age), unsafe_allow_html=True)


def render_daeun_table_html(scores, current_age):
    head = "<tr><th>나이</th><th>대운</th><th>등급</th><th>%</th></tr>"
    body = ""
    for s in scores:
        age_start = s["age"]
        cls = "current" if age_start <= current_age < age_start + 10 else ""
        body += (
            f"<tr><td class='{cls}'>{age_start}~{age_start + 9}세</td>"
            f"<td class='{cls}'>{s['pillar'].hanja}</td>"
            f"<td class='{cls}'>{friendly_grade_label(s['grade'])} {s['stars']}</td>"
            f"<td class='{cls}'>{s['percent']}%</td></tr>"
        )
    return f"<table class='seun-table'>{head}{body}</table>"


def render_daeun_section(chart, a2, scores2):
    st.caption(
        "등급 이름은 좋고 나쁨이 아니라 그 시기에 필요한 태도를 알려줍니다. "
        "전통 명리 용어(구)도 괄호로 함께 적어뒀어요."
    )
    today_age = date.today().year - chart.birth_local.year + 1
    for s in scores2:
        age_start = s["age"]
        is_current = age_start <= today_age < age_start + 10
        label = (
            f"{'▶ ' if is_current else ''}{age_start}~{age_start + 9}세 · "
            f"{s['pillar'].hanja} · {friendly_grade_label(s['grade'])} {s['stars']}"
        )
        with st.expander(label, expanded=False):
            st.markdown(
                "<div style='display:flex; align-items:center; gap:8px; margin-bottom:8px;'>"
                f"<div class='daeun-bar-bg'><div class='daeun-bar-fill' "
                f"style='width:{s['percent']}%;'></div></div>"
                f"<span style='font-size:12px; color:var(--ink-soft); width:34px; text-align:right;'>{s['percent']}%</span>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.caption(grade_caption(s["grade"]))
            st.markdown(f"**흐름 테마**: {_theme(a2, s['pillar'])}")
            if s["notes"]:
                st.markdown(render_reasons_html(s["notes"], limit=10), unsafe_allow_html=True)

            show_seun = st.checkbox(
                "1년 단위 세운 보기", key=f"seun_toggle_{age_start}"
            )
            if show_seun:
                start_year = chart.birth_local.year + age_start - 1
                rows = score_seun_range(a2, start_year, 10)
                st.caption(
                    "세운은 대운과 다른 축입니다. 대운은 10년의 배경, 세운은 "
                    "그 해의 흐름이라 두 점수를 더하거나 평균 내지 마세요."
                )
                st.markdown(
                    render_seun_table_html(rows, date.today().year),
                    unsafe_allow_html=True,
                )


def augment_grades_in_json(chart, a2):
    """export_dict() 결과를 그대로 두되, grade가 있는 자리마다 grade_friendly·
    grade_advice 필드를 안전하게 덧붙입니다. 원래 grade 값은 그대로 남겨서
    AI 챗봇 등 다른 프로그램이 참조할 표준 용어를 보존합니다."""
    data = export_dict(chart, a2=a2)

    def _walk(node):
        if isinstance(node, dict):
            for key in ("grade", "grade_absolute"):
                val = node.get(key)
                if val in GRADE_FRIENDLY:
                    info = GRADE_FRIENDLY[val]
                    node[key + "_friendly"] = info["label"]
                    node[key + "_advice"] = f"{info['desc']}. {info['tip']}"
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(data)
    data["grade_legend"] = {
        raw: {"friendly": info["label"], "desc": info["desc"], "tip": info["tip"]}
        for raw, info in GRADE_FRIENDLY.items()
    }
    return json.dumps(data, ensure_ascii=False, indent=1, default=str)


def _pdf_font(bold=False):
    if not _PDF_FONT_OK:
        return "Helvetica-Bold" if bold else "Helvetica"
    return "NotoSansKR"


def _pdf_wrap(text, font, size, max_width):
    """실제 렌더링 폭(stringWidth)을 기준으로 줄바꿈 — 한글/영문 폭 차이와
    무관하게 항상 여백 안에 맞춰집니다."""
    lines, cur = [], ""
    for ch in text:
        trial = cur + ch
        if pdfmetrics.stringWidth(trial, font, size) > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


class PdfWriter:
    """A4 페이지에 커서(y)를 관리하며 그리는 얇은 헬퍼. 텍스트를 문자수가
    아니라 실제 폭으로 줄바꿈하고, 표·막대는 도형으로 직접 그려서
    한글/영문 폭 차이로 인한 정렬 깨짐을 원천적으로 피합니다."""

    def __init__(self):
        self.buf = io.BytesIO()
        self.c = pdfcanvas.Canvas(self.buf, pagesize=A4)
        self.W, self.H = A4
        self.margin = 42
        self.x0 = self.margin
        self.x1 = self.W - self.margin
        self.y = self.H - self.margin
        self._font, self._size = _pdf_font(), 9

    def _set_font(self, font, size):
        self._font, self._size = font, size
        self.c.setFont(font, size)

    def ensure_space(self, needed):
        if self.y - needed < self.margin:
            self.c.showPage()
            self.y = self.H - self.margin
            self.c.setFont(self._font, self._size)

    def text(self, s, size=9, bold=False, color=(0.17, 0.17, 0.16), gap=13, indent=0):
        font = _pdf_font(bold)
        self._set_font(font, size)
        self.c.setFillColorRGB(*color)
        for raw_line in s.splitlines() or [""]:
            for line in _pdf_wrap(raw_line, font, size, self.x1 - self.x0 - indent):
                self.ensure_space(gap)
                self.c.drawString(self.x0 + indent, self.y, line)
                self.y -= gap

    def spacer(self, h=6):
        self.y -= h

    def hr(self):
        self.ensure_space(10)
        self.c.setStrokeColorRGB(0.82, 0.78, 0.7)
        self.c.setLineWidth(0.6)
        self.c.line(self.x0, self.y, self.x1, self.y)
        self.y -= 12

    def section_title(self, s):
        self.ensure_space(24)
        self._set_font(_pdf_font(bold=True), 13)
        self.c.setFillColorRGB(0.85, 0.35, 0.19)
        self.c.drawString(self.x0, self.y, s)
        self.y -= 18

    def pillars_table(self, chart):
        labels = ["년주", "월주", "일주", "시주"]
        pillars = chart.pillars
        sip = chart.sipseong_map()
        uns = chart.unseong_map()
        sip_gan = ["년간", "월간", "일간", "시간"]
        sip_ji = ["년지", "월지", "일지", "시지"]
        uns_keys = ["년", "월", "일", "시"]

        def jjg(p):
            return "·".join(GAN_H[g] for g, _ in JIJANGGAN[p.ji])

        rows = [
            ("", labels),
            ("천간", [GAN_H[p.gan] for p in pillars]),
            ("지지", [p.hanja[1] for p in pillars]),
            ("십성(간)", [sip[k] for k in sip_gan]),
            ("십성(지)", [sip[k] for k in sip_ji]),
            ("지장간", [jjg(p) for p in pillars]),
            ("십이운성", [uns[k] for k in uns_keys]),
        ]
        col0_w = 60
        col_w = (self.x1 - self.x0 - col0_w) / 4
        row_h = 20
        table_h = row_h * len(rows)
        self.ensure_space(table_h + 6)
        top = self.y
        font = _pdf_font()
        for ri, (row_label, values) in enumerate(rows):
            row_y = top - ri * row_h
            if row_label:
                self._set_font(font, 8.5)
                self.c.setFillColorRGB(0.37, 0.36, 0.35)
                self.c.drawCentredString(self.x0 + col0_w / 2, row_y - row_h + 7, row_label)
            for ci, v in enumerate(values):
                cx = self.x0 + col0_w + ci * col_w + col_w / 2
                size = 13 if ri in (1, 2) else 8.5
                self._set_font(font, size)
                self.c.setFillColorRGB(0.17, 0.17, 0.16)
                self.c.drawCentredString(cx, row_y - row_h + (5 if size > 9 else 7), str(v))

        self.c.setStrokeColorRGB(0.82, 0.78, 0.7)
        self.c.setLineWidth(0.5)
        for ri in range(len(rows) + 1):
            ly = top - ri * row_h
            self.c.line(self.x0, ly, self.x1, ly)
        for ci in range(6):
            lx = self.x0 + (col0_w if ci == 0 else col0_w + (ci - 1) * col_w)
            self.c.line(lx, top, lx, top - table_h)
        self.c.line(self.x1, top, self.x1, top - table_h)
        self.y = top - table_h - 14

    def bar_row(self, label, pct, note="", bar_w=None, color=(0.85, 0.35, 0.19), label_w=34):
        self.ensure_space(16)
        font = _pdf_font()
        bar_w = bar_w or (self.x1 - self.x0 - label_w - 56)
        self._set_font(font, 8.3)
        self.c.setFillColorRGB(0.17, 0.17, 0.16)
        self.c.drawString(self.x0, self.y, label)
        bx = self.x0 + label_w
        bh = 8
        by = self.y - 1
        self.c.setFillColorRGB(0.97, 0.93, 0.85)
        self.c.roundRect(bx, by, bar_w, bh, 3, fill=1, stroke=0)
        fw = max(0, min(bar_w, bar_w * pct / 100))
        self.c.setFillColorRGB(*color)
        if fw > 0:
            self.c.roundRect(bx, by, fw, bh, 3, fill=1, stroke=0)
        self.c.setFillColorRGB(0.37, 0.36, 0.35)
        self._set_font(font, 8.3)
        self.c.drawString(bx + bar_w + 6, self.y, note or f"{round(pct)}%")
        self.y -= 15

    def info_box(self, lines, pad=8, gap=13, size=9):
        font = _pdf_font()
        wrapped = []
        for ln in lines:
            wrapped += _pdf_wrap(ln, font, size, self.x1 - self.x0 - 2 * pad)
        h = len(wrapped) * gap + 2 * pad
        self.ensure_space(h + 6)
        self.c.setFillColorRGB(0.98, 0.93, 0.85)
        self.c.roundRect(self.x0, self.y - h, self.x1 - self.x0, h, 5, fill=1, stroke=0)
        ty = self.y - pad - 8
        self._set_font(font, size)
        self.c.setFillColorRGB(0.17, 0.17, 0.16)
        for ln in wrapped:
            self.c.drawString(self.x0 + pad, ty, ln)
            ty -= gap
        self.y -= h + 10

    def save(self):
        self.c.save()
        return self.buf.getvalue()


def build_pdf_report(chart, a2, scores2, title):
    """리포트를 텍스트 덤프가 아니라 실제 표·막대 도형으로 그립니다.
    한글·영문 폭 차이 때문에 줄이 어긋나는 문제를 원천적으로 피합니다."""
    w = PdfWriter()


    w.text(title, size=15, bold=True, color=(0.17, 0.17, 0.16), gap=20)
    w.text(
        f"출생 {chart.birth_local:%Y-%m-%d %H:%M} ({'남성' if chart.is_male else '여성'}) · "
        f"{chart.place.name} · 자시기준 {chart.jasi_school}",
        size=9, color=(0.37, 0.36, 0.35),
    )
    w.spacer(10)


    w.section_title("등급 이름 안내")
    legend_lines = ["등급은 좋고 나쁨이 아니라 그 시기에 필요한 태도를 알려주는 이름입니다."]
    for raw, info in GRADE_FRIENDLY.items():
        legend_lines.append(f"· {info['label']} ({raw}) — {info['desc']}. {info['tip']}")
    w.info_box(legend_lines)


    w.section_title("V2 — 원국(사주 네 기둥)")
    w.pillars_table(chart)

    w.text("오행 분포 (지장간 포함 실질 비중)", size=9.5, bold=True, gap=16)
    counts = chart.ohaeng_count(include_jijanggan=True)
    total = sum(counts.values()) or 1
    for e in OHAENG:
        w.bar_row(e, counts[e] / total * 100)
    w.spacer(6)

    w.section_title("나는 어떤 사람인가")
    nick, desc = ILGAN_DESC[chart.day_gan]
    w.text(f"일간 {GAN_H[chart.day_gan]}({chart.day_ohaeng}) — {nick}", size=10, bold=True, gap=14)
    w.text(desc, size=9, gap=13)
    w.spacer(3)

    st_ = a2.strength
    w.text(
        f"강약: {st_.label} · 아군 {st_.ally:.1f} vs 적군 {st_.enemy:.1f} ({st_.ratio:.0%})",
        size=10, bold=True, gap=15,
    )
    w.text(st_.description, size=8.7, color=(0.37, 0.36, 0.35), gap=12)
    if st_.confidence != "확실":
        w.text(
            f"⚠ 판정 신뢰도: 경계 — '{st_.alt_label}'과의 경계 구간입니다. "
            "두 시나리오가 갈리는 구간은 다른 근거로 함께 판단하세요.",
            size=8.3, color=(0.71, 0.17, 0.07), gap=12,
        )
    if a2.special:
        w.text(f"★ {a2.special['name']} 로 판정 — 억부 결론을 반전시킵니다.", size=8.7)
    if a2.johu_note:
        w.text(a2.johu_note, size=8.7, color=(0.37, 0.36, 0.35), gap=12)
    if a2.gyeokguk:
        gk = a2.gyeokguk
        w.spacer(2)
        w.text(f"격국 교차검증: {gk['gyeok_name']} · {gk['verdict']}", size=9, bold=True, gap=13)
        w.text(gk["note"], size=8.3, color=(0.37, 0.36, 0.35), gap=11.5, indent=4)
    w.spacer(4)

    if a2.yongsin:
        w.text(f"용신(도움되는 기운): {', '.join(a2.yongsin)}", size=9, color=(0.15, 0.31, 0.04))
        d, col, thing, _o = OHAENG_ADVICE[a2.yongsin[0]]
        w.text(f"→ 방위 {d} / 색 {col} / {thing} 가까이", size=8.3, color=(0.37, 0.36, 0.35), indent=6)
    if a2.gisin:
        w.text(f"기신(피해야 할 기운): {', '.join(a2.gisin)}", size=9, color=(0.71, 0.17, 0.07))
        _d, _c, _t, organ = OHAENG_ADVICE[a2.gisin[0]]
        w.text(f"→ 건강은 {organ} 계통을 특히 살피세요", size=8.3, color=(0.37, 0.36, 0.35), indent=6)
    w.spacer(4)

    w.text("판정 근거", size=9.5, bold=True, gap=16)
    for r in a2.reasons[:6]:
        w.text(f"· {r}", size=8.5, color=(0.30, 0.30, 0.28), gap=12, indent=4)
    w.spacer(6)


    w.section_title("V2 — 10년 주기 운세")
    today_age = date.today().year - chart.birth_local.year + 1
    for s in scores2:
        age_start = s["age"]
        is_current = age_start <= today_age < age_start + 10
        w.ensure_space(46)
        mark = "▶ " if is_current else ""
        w.text(
            f"{mark}{age_start}~{age_start + 9}세 · {s['pillar'].hanja} · "
            f"{friendly_grade_label(s['grade'])} {s['stars']}",
            size=9.5, bold=True, gap=14,
        )
        w.bar_row("", s["percent"], note=f"{s['percent']}%")
        w.text(_theme(a2, s["pillar"]), size=8.3, color=(0.37, 0.36, 0.35), gap=11, indent=4)
        for n in s["notes"][:2]:
            w.text(f"· {n}", size=8, color=(0.45, 0.44, 0.42), gap=10.5, indent=6)
        w.spacer(5)


    w.spacer(6)
    w.section_title("V2 — 세운 (1년 주기, 오늘 기준)")
    w.text(
        "세운은 대운과 다른 축입니다. 10년의 배경과 그 해의 사건은 층이 달라서, "
        "두 값을 더하거나 평균 내면 근거 없는 숫자가 됩니다. 따로 읽으세요.",
        size=8.3, color=(0.45, 0.44, 0.42), gap=11,
    )
    w.spacer(3)
    seun_start_year = date.today().year
    seun_rows = score_seun_range(a2, seun_start_year, 10)
    for r in seun_rows:
        r_age = r["year"] - chart.birth_local.year + 1
        is_this_year = r["year"] == date.today().year
        w.ensure_space(38)
        mark = "▶ " if is_this_year else ""
        daeun_txt = f" · 대운 {r['daeun'].hanja}" if r["daeun"] else ""
        w.text(
            f"{mark}{r['year']}년 · {r['pillar'].hanja} · {r_age}세{daeun_txt} · "
            f"{friendly_grade_label(r['grade'])} {r['stars']}",
            size=9.5, bold=True, gap=14,
        )
        w.bar_row("", r["percent"], note=f"{r['percent']}%")
        for n in r["notes"][:2]:
            w.text(f"· {n}", size=8, color=(0.45, 0.44, 0.42), gap=10.5, indent=6)
        w.spacer(5)


    w.spacer(6)
    hwaguk_hits = scan_daeun_hwaguk(a2)
    hwaguk_meaningful = {
        k: v for k, v in hwaguk_hits.items()
        if v["yongsin_changed"] or v["label_changed"]
    }
    if hwaguk_meaningful:
        w.section_title("化局 구간 — 참고 판정")
        w.text(
            "대운이 원국과 삼합·방합을 완성시켜 특정 오행이 일시적으로 판을 "
            "지배하는 구간입니다. 위 대운 점수·등급은 원국 용신 기준의 정본이고, "
            "이 표시는 '그 10년은 잣대 자체가 흔들릴 수 있다'는 참고입니다. "
            "둘을 합산하지 마세요.",
            size=8.3, color=(0.45, 0.44, 0.42), gap=11,
        )
        w.spacer(3)
        daeun_by_age = dict(chart.daeun)
        for age_start in sorted(hwaguk_meaningful):
            h = hwaguk_meaningful[age_start]
            pillar = daeun_by_age[age_start]
            w.ensure_space(30)
            w.text(f"● {age_start}~{age_start + 9}세 · {pillar.hanja}", size=9.5, bold=True, gap=14)
            label_note = (
                "   ※ 참고 라벨 — 원국 분포 기준 밴드라 운 수치에 그대로 적용되지 않음"
                if h["label_changed"] else ""
            )
            w.text(
                f"강약 {h['base_label']}({h['base_ratio']:.0%}) → "
                f"{h['label']}({h['ratio']:.0%}){label_note}",
                size=8.3, color=(0.37, 0.36, 0.35), gap=11.5, indent=4,
            )
            if h["yongsin_changed"]:
                w.text(
                    f"용신 {'·'.join(h['base_yongsin']) or '없음'} → "
                    f"{'·'.join(h['yongsin']) or '없음'}",
                    size=8.3, color=(0.37, 0.36, 0.35), gap=11.5, indent=4,
                )
            for e in h["events"]:
                w.text(e, size=8, color=(0.45, 0.44, 0.42), gap=10.5, indent=6)
            w.spacer(4)

    w.spacer(6)
    w.section_title("종합 결론")
    today_age = date.today().year - chart.birth_local.year + 1
    for s in scores2:
        s["theme"] = _theme(a2, s["pillar"])
    for para in _conclusion(chart, a2, scores2, today_age):
        w.text(para, size=9, gap=13)
        w.spacer(4)

    if chart.warnings:
        w.spacer(4)
        w.text("⚠ 계산상 주의사항", size=9.5, bold=True, gap=14)
        for warn in chart.warnings:
            w.text(f"· {warn}", size=8.3, color=(0.55, 0.20, 0.10), gap=11.5, indent=4)

    w.spacer(10)
    w.hr()
    w.text(DISCLAIMER, size=7.5, color=(0.55, 0.53, 0.48), gap=10)
    w.spacer(4)
    meta = export_dict(
        chart, a2=a2, today=date.today(),
        include_seun=False, include_hwaguk=False, include_robustness=True,
    )["meta"]
    rb = strength_robustness(chart)
    w.text(
        f"엔진 {meta['engine_version']} / tzdata {meta['tzdata_version']} / "
        f"계수지문 {meta['coefficients']['sha256'][:12]}…",
        size=7, color=(0.6, 0.58, 0.53), gap=9.5,
    )
    w.text(
        f"자시학파 {chart.jasi_school} / "
        f"경도보정 {'켬' if chart.options.get('apply_longitude') else '끔'} / "
        f"균시차 {'켬' if chart.options.get('apply_eot') else '끔'} / 지역 {chart.place.name}",
        size=7, color=(0.6, 0.58, 0.53), gap=9.5,
    )
    w.text(
        f"강약 판정 견고성: {rb['verdict']} "
        f"(계수 ±20% 섭동 {rb['n_tested']}회 중 {rb['n_flipped']}회 변동)",
        size=7, color=(0.6, 0.58, 0.53), gap=9.5,
    )

    return w.save()


if "chart" in st.session_state:
    chart = st.session_state["chart"]

    for w in chart.warnings:
        st.warning(w)

    a2 = analyze_v2(chart)
    scores2 = score_all_daeun_v2(a2)
    a1 = analyze(chart)
    scores1 = score_all_daeun(a1)

    st.markdown(
        "<div class='chip-row'>"
        f"<span class='chip'>{chart.jasi_school}</span>"
        f"<span class='chip'>진태양시 {'켬' if chart.options.get('apply_longitude') else '끔'}</span>"
        f"<span class='chip'>균시차 {'켬' if chart.options.get('apply_eot') else '끔'}</span>"
        "</div>",
        unsafe_allow_html=True,
    )


    nickname, temperament = ILGAN_DESC[chart.day_gan]
    special_note = f" · 특수격({a2.special['name']})" if a2.special else ""
    st.markdown(
        "<div class='v2-card'>"
        "<span class='v2-badge'>V2 정밀 분석</span>"
        f"<p class='v2-title'>일간 {nickname} · {a2.strength.label}{special_note}</p>"
        f"<p class='v2-desc'>{temperament}</p>"
        f"<p class='v2-desc'>용신: {', '.join(a2.yongsin) or '-'} · "
        f"기신: {', '.join(a2.gisin) or '-'}</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    with st.expander("V2 상세 리포트 펼쳐보기 (지장간·통근·계절·종격 반영)", expanded=False):
        render_v2_detail(chart, a2, scores2)

    st.markdown("#### 10년 주기 운세")
    render_daeun_section(chart, a2, scores2)

    with st.expander("V1 간편 결과 함께 보기 (더 단순한 예전 방식)"):
        st.caption("V1은 억부용신만 반영한 간단 버전입니다. 기준으로는 위 V2를 참고하세요.")
        render_v1_detail(chart, a1, scores1)


    st.markdown("#### 결과 내보내기")
    json_str = augment_grades_in_json(chart, a2)
    txt_str = GRADE_LEGEND_TEXT + "\n" + patch_grade_lines(
        export_text(chart, a2=a2, today=date.today())
    )
    pdf_bytes = build_pdf_report(
        chart, a2, scores2,
        f"사주풀이 결과 — {chart.birth_local:%Y-%m-%d %H:%M}",
    )

    fname_base = f"saju_{chart.birth_local:%Y%m%d_%H%M}"
    ec1, ec2, ec3 = st.columns(3)
    ec1.download_button("JSON", json_str, file_name=f"{fname_base}.json",
                         mime="application/json", use_container_width=True)
    ec2.download_button("TXT", txt_str, file_name=f"{fname_base}.txt",
                         mime="text/plain", use_container_width=True)
    ec3.download_button("PDF", pdf_bytes, file_name=f"{fname_base}.pdf",
                         mime="application/pdf", use_container_width=True)

    st.markdown(
        "<div class='ai-box'>"
        "💬 내려받은 JSON 또는 TXT 파일을 ChatGPT·Claude 같은 AI 챗봇에 올리고 "
        "추가로 궁금한 점을 물어보세요.<br>"
        "👥 두 명 이상의 궁합이 궁금하면, 각자 결과를 따로 받아 파일 여러 개를 "
        "한 번에 올려서 물어보면 됩니다.<br>"
        "📄 PDF는 사람이 직접 읽거나 인쇄·보관용으로 쓰기 좋습니다."
        "</div>",
        unsafe_allow_html=True,
    )

    st.divider()
    with st.expander("🤔 결과가 예상과 다르신가요? 여기를 확인해 다시 시도해보세요"):
        st.markdown(
            "<p style='font-size:13px; color:var(--ink-soft); margin:0 0 10px;'>"
            "밤 11시~새벽 1시 사이에 태어나셨거나, 정확한 결과를 원하시면 "
            "아래 설정을 확인해주세요. 바꾼 뒤 아래 버튼을 누르면 같은 생년월일로 "
            "다시 계산합니다."
            "</p>", unsafe_allow_html=True,
        )
        st.radio(
            "자시(밤 11시~새벽 1시) 기준", list(JASI_SCHOOLS),
            horizontal=True, key="jasi_school",
        )
        st.markdown(
            "<div class='timeline-bar'>"
            "<div style='background:#F5C4B3; color:#4A1B0C;'>밤 11시~12시 오늘</div>"
            "<div style='background:#FAC775; color:#412402;'>12시~새벽1시 내일</div>"
            "</div>"
            "<p style='font-size:12px; color:var(--ink-soft); margin:0 0 12px;'>"
            "<b>야자시</b>(추천): 자정이 되는 순간 내일로 넘어가요. &nbsp;·&nbsp; "
            "<b>정자시</b>: 밤 11시가 되는 순간부터 바로 내일로 봐요."
            "</p>", unsafe_allow_html=True,
        )
        st.checkbox(
            "진태양시 보정 사용 (추천)", key="apply_longitude",
            help="표준시계 대신, 태어난 지역의 실제 해 위치 기준 시각으로 계산합니다. "
                 "한국은 표준시가 동경 135도 기준이라 서울 등 대부분 지역은 실제 "
                 "해보다 시계가 30분 안팎 빠릅니다.",
        )
        st.checkbox(
            "균시차 보정 사용", key="apply_eot",
            help="지구 공전 궤도가 타원이라 생기는 최대 ±16분의 추가 오차까지 "
                 "보정합니다. 명리 실무에서는 대개 생략하는 값이라 기본은 꺼둡니다.",
        )

        retry_hash = hash((
            chart.birth_local.year, chart.birth_local.month, chart.birth_local.day,
            chart.birth_local.hour, chart.birth_local.minute,
            "남" if chart.is_male else "여", chart.place.name,
            st.session_state["jasi_school"], st.session_state["apply_longitude"],
            st.session_state["apply_eot"],
        ))
        retry_disabled = st.session_state.get("last_input_hash") == retry_hash
        retry_clicked = st.button(
            "이 설정으로 다시 계산하기", use_container_width=True,
            disabled=retry_disabled, key="retry_button",
        )
        if retry_disabled:
            st.caption("✓ 이미 이 설정으로 계산된 결과예요.")
        else:
            st.markdown(
                "<a href='#top-of-form' style='font-size:13px;'>"
                "↑ 맨 위로 이동해서 새 결과 보기</a>", unsafe_allow_html=True,
            )

        if retry_clicked:
            try:
                new_chart = build_chart(
                    chart.birth_local.year, chart.birth_local.month, chart.birth_local.day,
                    chart.birth_local.hour, chart.birth_local.minute,
                    is_male=chart.is_male,
                    place=chart.place.name,
                    jasi_school=st.session_state["jasi_school"],
                    apply_longitude=st.session_state["apply_longitude"],
                    apply_eot=st.session_state["apply_eot"],
                )
                st.session_state["chart"] = new_chart
                st.session_state["last_input_hash"] = retry_hash
                _log_usage(new_chart)
                st.success("새 설정으로 다시 계산했어요. 위로 이동해서 확인해보세요 ↑")
                st.rerun()
            except Exception as e:
                st.error(f"계산 중 문제가 발생했습니다: {e}")

    st.caption(DISCLAIMER)
