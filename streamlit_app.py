#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
streamlit_app.py — 사주풀이 웹앱 (Streamlit)

계산 엔진은 saju_app.py 를 그대로 가져다 씁니다. 이 파일은 UI/UX 만 담당합니다.
실행:
    streamlit run streamlit_app.py
"""

import io
import json
import threading
import urllib.request
from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from saju_app import (
    __version__,
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
    DISCLAIMER,
    LOG_WEBHOOK_URL,
    LOG_INCLUDE_IP,
    LOG_TIMEOUT_SEC,
    IP_LOOKUP_URL,
    IP_LOOKUP_TIMEOUT_SEC,
)

# 등급은 "좋고 나쁨"이 아니라 그 시기에 들어오는 변화·에너지의 크기를 뜻합니다.
# 특히 "어려움"/"매우 어려움"은 불운이 아니라 변수가 많아 대비가 필요하다는
# 의미라, 사용자가 오해하지 않도록 등급마다 짧은 설명을 붙여둡니다.
GRADE_REFRAME = {
    "매우 좋음": "기운이 순조롭게 흐르는 시기",
    "좋음": "기운이 안정적으로 도와주는 시기",
    "보통": "큰 기복 없이 흘러가는 시기",
    "어려움": "변화·사건이 많아 대비가 필요한 시기 (불운을 뜻하지 않음)",
    "매우 어려움": "변화의 폭이 커서 특히 신중해야 할 시기 (불운을 뜻하지 않음)",
}

# ──────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="사주풀이",
    page_icon="🀄",
    layout="centered",
    initial_sidebar_state="collapsed",
)

FONT_PATH = "fonts/NotoSansKR-Regular.ttf"

# ──────────────────────────────────────────────────────────────
# 한지·먹빛 테마 CSS (라이트: 한지+주색, 다크: 먹지+금박)
# ──────────────────────────────────────────────────────────────
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
}
@media (prefers-color-scheme: dark) {
    :root {
        --hanji-bg: #17150F;
        --hanji-card: #241F16;
        --ink: #F1EFE8;
        --ink-soft: #C9B896;
        --seal: #FAC775;
        --seal-dark: #EF9F27;
        --seal-text: #FAC775;
    }
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
    padding: 6px 0 2px;
}
.app-header .title {
    display: inline-block;
    font-size: 25px;
    font-weight: 700;
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
        "Malgun Gothic", "Noto Sans KR", "Segoe UI", Roboto, sans-serif;
    transform: translateZ(0);
    backface-visibility: hidden;
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
@media (prefers-color-scheme: dark) {
    .chip-yong { background: #173404; color: #C0DD97; }
    .chip-gi { background: #4A1B0C; color: #F5C4B3; }
}

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
    "<div class='app-header'><span class='title'>"
    "<svg width='26' height='26' viewBox='0 0 26 26' xmlns='http://www.w3.org/2000/svg'>"
    "<rect x='1' y='1' width='24' height='24' rx='6' fill='#D85A30'/>"
    "<text x='13' y='18' font-size='13' text-anchor='middle' fill='#FBF7EE' "
    "font-family='sans-serif'>命</text></svg>"
    "사주풀이</span></div>"
    "<div class='app-sub'>생년월일시로 원국·강약·용신·대운을 풀이합니다"
    "</div>",
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────
# 입력 폼
# ──────────────────────────────────────────────────────────────
CITIES = list_cities()
DEFAULT_CITY_IDX = CITIES.index("서울") if "서울" in CITIES else 0

with st.form("birth_form"):
    c1, c2 = st.columns(2)
    with c1:
        birth_date = st.date_input(
            "생년월일", value=date(1990, 1, 1),
            min_value=date(1900, 1, 1), max_value=date.today(),
        )
        gender_label = st.radio("성별", ["남", "여"], horizontal=True)
    with c2:
        birth_time = st.time_input("태어난 시각", value=dtime(12, 0))
        place = st.selectbox("태어난 지역", CITIES, index=DEFAULT_CITY_IDX)

    with st.expander("시간 설정 — 결과가 다르게 나온다면 여기를 확인하세요"):
        st.markdown(
            "<p style='font-size:13px; color:var(--ink-soft); margin:0 0 10px;'>"
            "밤 11시~새벽 1시 사이에 태어나셨거나, 정확한 결과를 원하시면 "
            "아래 설정을 확인해주세요. 잘 모르시면 기본값 그대로 두셔도 됩니다."
            "</p>", unsafe_allow_html=True,
        )

        jasi_school = st.radio(
            "자시(밤 11시~새벽 1시) 기준", list(JASI_SCHOOLS), index=0,
            horizontal=True,
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

        apply_longitude = st.checkbox(
            "진태양시 보정 사용 (추천)", value=True,
            help="표준시계 대신, 태어난 지역의 실제 해 위치 기준 시각으로 계산합니다. "
                 "한국은 표준시가 동경 135도 기준이라 서울 등 대부분 지역은 실제 "
                 "해보다 시계가 30분 안팎 빠릅니다.",
        )
        apply_eot = st.checkbox(
            "균시차 보정 사용", value=False,
            help="지구 공전 궤도가 타원이라 생기는 최대 ±16분의 추가 오차까지 "
                 "보정합니다. 명리 실무에서는 대개 생략하는 값이라 기본은 꺼둡니다.",
        )

    submitted = st.form_submit_button("사주 풀이 보기", use_container_width=True)

def _log_usage(chart):
    """[접속일시(KST), 성별, 연도, 월, 일, 시, 장소, IP] 한 줄을 구글시트 'log'
    탭에 남깁니다. 웹 요청을 막지 않도록 별도 스레드에서 실행하고, 실패해도
    (오프라인·URL 미설정·응답 지연 등) 계산 결과 표시에는 영향을 주지 않습니다.
    """
    if not LOG_WEBHOOK_URL:
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
            pass  # 로그 실패는 조용히 무시 — 사용자 계산 흐름을 막지 않습니다.

    threading.Thread(target=_send, daemon=True).start()


if submitted:
    try:
        chart = build_chart(
            birth_date.year, birth_date.month, birth_date.day,
            birth_time.hour, birth_time.minute,
            is_male=(gender_label == "남"),
            place=place,
            jasi_school=jasi_school,
            apply_longitude=apply_longitude,
            apply_eot=apply_eot,
        )
        st.session_state["chart"] = chart
        _log_usage(chart)
    except Exception as e:
        st.error(f"계산 중 문제가 발생했습니다: {e}")
        st.session_state.pop("chart", None)

# ──────────────────────────────────────────────────────────────
# 결과 표시 — V2 상세를 텍스트 대신 정렬이 깨지지 않는 HTML로 구성
# ──────────────────────────────────────────────────────────────
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
            f"<td class='{cls}'>{r['grade']}</td>"
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


def render_daeun_section(chart, a2, scores2):
    st.caption(
        "등급은 '좋고 나쁨'이 아니라 그 시기에 들어오는 변화·에너지의 크기를 "
        "뜻합니다. '어려움'류 등급도 불운이 아니라 변수가 많아 대비가 필요하다는 "
        "의미로 봐주세요."
    )
    today_age = date.today().year - chart.birth_local.year + 1
    for s in scores2:
        age_start = s["age"]
        is_current = age_start <= today_age < age_start + 10
        reframe = GRADE_REFRAME.get(s["grade"], "")
        label = (
            f"{'▶ ' if is_current else ''}{age_start}~{age_start + 9}세 · "
            f"{s['pillar'].hanja} · {s['grade']} {s['stars']}"
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
            st.caption(reframe)
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


def make_summary_image(chart, a2):
    """공유용 요약 카드 이미지(PNG bytes)를 만듭니다."""
    W, H = 900, 720
    bg = (251, 247, 238)
    ink = (44, 44, 42)
    seal = (216, 90, 48)
    card = (250, 238, 218)

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    def font(size):
        return ImageFont.truetype(FONT_PATH, size)

    def center_text(y, text, size, color=ink):
        f = font(size)
        bbox = d.textbbox((0, 0), text, font=f)
        w = bbox[2] - bbox[0]
        d.text(((W - w) / 2, y), text, font=f, fill=color)

    def wrapped(y, text, size, color, max_width, indent=60, line_gap=10):
        f = font(size)
        words = text
        lines, cur = [], ""
        for ch in words:
            trial = cur + ch
            bbox = d.textbbox((0, 0), trial, font=f)
            if bbox[2] - bbox[0] > max_width and cur:
                lines.append(cur)
                cur = ch
            else:
                cur = trial
        if cur:
            lines.append(cur)
        for line in lines:
            d.text((indent, y), line, font=f, fill=color)
            y += size + line_gap
        return y

    d.rectangle([0, 0, W, 90], fill=seal)
    center_text(24, "사주풀이 · V2 정밀 분석", 30, (251, 247, 238))

    y = 130
    nickname = ILGAN_DESC[chart.day_gan][0]
    center_text(y, f"일간 {nickname} · {a2.strength.label}", 40, ink)
    y += 70

    pillars = [("년주", chart.year), ("월주", chart.month),
               ("일주", chart.day), ("시주", chart.hour)]
    box_w = (W - 120) // 4
    for i, (label, p) in enumerate(pillars):
        x = 60 + i * box_w
        d.rounded_rectangle([x, y, x + box_w - 16, y + 160], radius=10, fill=card)
        f1 = font(18)
        bbox = d.textbbox((0, 0), label, font=f1)
        d.text((x + (box_w - 16 - (bbox[2] - bbox[0])) / 2, y + 12),
                label, font=f1, fill=(95, 94, 90))
        f2 = font(40)
        bbox = d.textbbox((0, 0), p.hanja, font=f2)
        d.text((x + (box_w - 16 - (bbox[2] - bbox[0])) / 2, y + 60),
                p.hanja, font=f2, fill=ink)
    y += 200

    yong = ", ".join(a2.yongsin) if a2.yongsin else "-"
    gi = ", ".join(a2.gisin) if a2.gisin else "-"
    d.text((60, y), f"용신(도움되는 기운): {yong}", font=font(26), fill=(20, 100, 80))
    y += 46
    d.text((60, y), f"기신(피해야 할 기운): {gi}", font=font(26), fill=seal)
    y += 60

    if a2.special:
        d.text((60, y), f"특수격: {a2.special['name']}", font=font(24), fill=ink)
        y += 50

    y += 10
    d.line([60, y, W - 60, y], fill=(210, 200, 180), width=2)
    y += 24
    y = wrapped(
        y,
        "이 결과는 명리학이라는 전통 해석 체계를 코드로 옮긴 것으로, "
        "과학적으로 검증된 예측이 아닙니다. 자기 성찰의 참고 자료로만 사용하세요.",
        18, (95, 94, 90), W - 120,
    )

    y += 20
    center_text(y, f"saju-app v{__version__}", 16, (150, 145, 130))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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

    # ── V2 (우선 노출) ──────────────────────────────────────
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

    st.markdown("#### 대운 (10년 주기)")
    render_daeun_section(chart, a2, scores2)

    with st.expander("V1 간편 결과 함께 보기 (더 단순한 예전 방식)"):
        st.caption("V1은 억부용신만 반영한 간단 버전입니다. 기준으로는 위 V2를 참고하세요.")
        st.markdown(
            "<pre style='overflow-x:auto; white-space:pre; font-size:12px; "
            "line-height:1.6; background:var(--hanji-card); padding:10px; "
            "border-radius:8px;'>" + render_text(chart, today=date.today())
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + "</pre>",
            unsafe_allow_html=True,
        )

    # ── 내보내기 ────────────────────────────────────────────
    st.markdown("#### 결과 내보내기")
    json_str = export_json(chart, a2=a2)
    txt_str = export_text(chart, a2=a2, today=date.today())
    img_bytes = make_summary_image(chart, a2)

    fname_base = f"saju_{chart.birth_local:%Y%m%d_%H%M}"
    ec1, ec2, ec3 = st.columns(3)
    ec1.download_button("JSON", json_str, file_name=f"{fname_base}.json",
                         mime="application/json", use_container_width=True)
    ec2.download_button("TXT", txt_str, file_name=f"{fname_base}.txt",
                         mime="text/plain", use_container_width=True)
    ec3.download_button("이미지", img_bytes, file_name=f"{fname_base}.png",
                         mime="image/png", use_container_width=True)

    st.markdown(
        "<div class='ai-box'>"
        "💬 내려받은 <b>JSON</b> 또는 <b>TXT</b> 파일을 ChatGPT, Claude 같은 "
        "AI 챗봇에 올리고 <i>\"이 사주 결과를 참고해서 올해 이직 시기가 궁금해\"</i> "
        "처럼 물어보면, 이 리포트에 담긴 근거를 바탕으로 추가 질문에 답해줍니다."
        "</div>",
        unsafe_allow_html=True,
    )

    st.divider()
    st.caption(DISCLAIMER)
