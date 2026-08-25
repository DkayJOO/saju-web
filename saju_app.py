"""
saju_app.py — 사주 분석기 (계산 엔진 + GUI, 단일 파일 통합본)

이 파일 하나만 있으면 됩니다. 실행:

    python3 saju_app.py

필요 조건: Python 3.9 이상 (tkinter 표준 포함, 추가 패키지 설치 불필요)

────────────────────────────────────────────────────────────────
이 파일은 원래 세 개로 나뉘어 있던
  · saju_all.py  (사주 계산 엔진 — 원국·대운 산출, v1 억부 판정)
  · saju_plus.py (강화 분석 엔진 — 지장간·통근·계절·종격 반영 v2 판정)
  · saju_gui.py  (tkinter GUI)
를 하나의 파일로 합친 것입니다. 계산 로직 자체는 전혀 바뀌지 않았습니다.

※ 이 결과는 명리학이라는 전통 해석 체계를 코드로 옮긴 것이며,
   과학적으로 검증된 예측이 아닙니다. 자기 성찰의 참고 자료로만 쓰세요.
"""

import os
import sys
import math
import json
import queue
import threading
import traceback
import contextlib
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, timezone as _tz
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, font as tkfont
    _TK_AVAILABLE = True
except ImportError:
    _TK_AVAILABLE = False

    class _TkStub:
        """tkinter 부재 시 클래스 정의만 통과시키는 껍데기."""

        def __init__(self, *a, **kw):
            raise RuntimeError(
                "tkinter 가 설치되어 있지 않아 GUI 를 실행할 수 없습니다. "
                "계산 엔진 기능은 그대로 사용할 수 있습니다.")

        def __getattr__(self, name):
            return _TkStub

    class _TkModuleStub:
        def __getattr__(self, name):
            return _TkStub

    tk = ttk = messagebox = filedialog = tkfont = _TkModuleStub()


try:
    from PIL import Image, ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

__version__ = "1.0.0"


LOG_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbz1TdB6dXgSWEzxRb7BO0E1OmtQRJB4zA18YSGvcoCRNQOY1hMyF452jFj61Fa5opG_/exec"
LOG_TIMEOUT_SEC = 4


LOG_INCLUDE_IP = True
IP_LOOKUP_URL = "https://api.ipify.org?format=json"
IP_LOOKUP_TIMEOUT_SEC = 3


"""천문 계산: 태양 황경, 절기, 율리우스일, 균시차.

VSOP87 절단급수(Meeus, Astronomical Algorithms, Appendix III)를 사용합니다.
황경 오차 < 0.001도 (시간으로 약 1.5초).
"""

import math
from datetime import datetime, timedelta


SOLAR_TERMS = ["입춘", "우수", "경칩", "춘분", "청명", "곡우",
               "입하", "소만", "망종", "하지", "소서", "대서",
               "입추", "처서", "백로", "추분", "한로", "상강",
               "입동", "소설", "대설", "동지", "소한", "대한"]


JEOL_TO_BRANCH = {0: 2, 2: 3, 4: 4, 6: 5, 8: 6, 10: 7,
                  12: 8, 14: 9, 16: 10, 18: 11, 20: 0, 22: 1}

_L0 = [(175347046,0,0),(3341656,4.6692568,6283.07585),(34894,4.6261,12566.1517),
(3497,2.7441,5753.3849),(3418,2.8289,3.5231),(3136,3.6277,77713.7715),
(2676,4.4181,7860.4194),(2343,6.1352,3930.2097),(1324,0.7425,11506.7698),
(1273,2.0371,529.691),(1199,1.1096,1577.3435),(990,5.233,5884.927),
(902,2.045,26.298),(857,3.508,398.149),(780,1.179,5223.694),
(753,2.533,5507.553),(505,4.583,18849.228),(492,4.205,775.523),
(357,2.92,0.067),(317,5.849,11790.629),(284,1.899,796.298),
(271,0.315,10977.079),(243,0.345,5486.778),(206,4.806,2544.314),
(205,1.869,5573.143),(202,2.458,6069.777),(156,0.833,213.299),
(132,3.411,2942.463),(126,1.083,20.775),(115,0.645,0.98),
(103,0.636,4694.003),(102,0.976,15720.839),(102,4.267,7.114),
(99,6.21,2146.17),(98,0.68,155.42),(86,5.98,161000.69),(85,1.3,6275.96),
(85,3.67,71430.7),(80,1.81,17260.15),(79,3.04,12036.46),(75,1.76,5088.63),
(74,3.5,3154.69),(74,4.68,801.82),(70,0.83,9437.76),(62,3.98,8827.39),
(61,1.82,7084.9),(57,2.78,6286.6),(56,4.39,14143.5),(56,3.47,6279.55),
(52,0.19,12139.55),(52,1.33,1748.02),(51,0.28,5856.48),(49,0.49,1194.45),
(41,5.37,8429.24),(41,2.4,19651.05),(39,6.17,10447.39),(37,6.04,10213.29),
(37,2.57,1059.38),(36,1.71,2352.87),(36,1.78,6812.77),(33,0.59,17789.85),
(30,0.44,83996.85),(30,2.74,1349.87),(25,3.16,4690.48)]

_L1 = [(628331966747,0,0),(206059,2.678235,6283.07585),(4303,2.6351,12566.1517),
(425,1.59,3.523),(119,5.796,26.298),(109,2.966,1577.344),(93,2.59,18849.23),
(72,1.14,529.69),(68,1.87,398.15),(67,4.41,5507.55),(59,2.89,5223.69),
(56,2.17,155.42),(45,0.4,796.3),(36,0.47,775.52),(29,2.65,7.11),
(21,5.34,0.98),(19,1.85,5486.78),(19,4.97,213.3),(17,2.99,6275.96),
(16,0.03,2544.31),(16,1.43,2146.17),(15,1.21,10977.08),(12,2.83,1748.02),
(12,3.26,5088.63),(12,5.27,1194.45),(12,2.08,4694.0),(11,0.77,553.57),
(10,1.3,6286.6),(10,4.24,1349.87),(9,2.7,242.73),(9,5.64,951.72),
(8,5.3,2352.87),(6,2.65,9437.76),(6,4.67,4690.48)]

_L2 = [(52919,0,0),(8720,1.0721,6283.0758),(309,0.867,12566.152),(27,0.05,3.52),
(16,5.19,26.3),(16,3.68,155.42),(10,0.76,18849.23),(9,2.06,77713.77),
(7,0.83,775.52),(5,4.66,1577.34),(4,1.03,7.11),(4,3.44,5573.14),
(3,5.14,796.3),(3,6.05,5507.55),(3,1.19,242.73),(3,6.12,529.69),
(3,0.31,398.15),(3,2.28,553.57),(2,4.38,5223.69),(2,3.75,0.98)]

_L3 = [(289,5.844,6283.076),(35,0,0),(17,5.49,12566.15),(3,5.2,155.42),
(1,4.72,3.52),(1,5.3,18849.23),(1,5.97,242.73)]
_L4 = [(114,3.142,0),(8,4.13,6283.08),(1,3.84,12566.15)]
_L5 = [(1,3.14,0)]

_R0 = [(100013989,0,0),(1670700,3.0984635,6283.07585),(13956,3.05525,12566.1517),
(3084,5.1985,77713.7715),(1628,1.1739,5753.3849),(1576,2.8469,7860.4194),
(925,5.453,11506.77),(542,4.564,3930.21),(472,3.661,5884.927),
(346,0.964,5507.553),(329,5.9,5223.694),(307,0.299,5573.143),
(243,4.273,11790.629),(212,5.847,1577.344),(186,5.022,10977.079),
(175,3.012,18849.228),(110,5.055,5486.778),(98,0.89,6069.78),
(86,5.69,15720.84),(86,1.27,161000.69),(65,0.27,17260.15),(63,0.92,529.69),
(57,2.01,83996.85),(56,5.24,71430.7),(49,3.25,2544.31),(47,2.58,775.52),
(45,5.54,9437.76),(43,6.01,6275.96),(39,5.36,4694.0),(38,2.39,8827.39),
(37,0.83,19651.05),(36,4.9,12139.55),(35,1.67,12036.46),(33,1.08,2942.46),
(32,1.95,7084.9),(32,0.51,5088.63),(28,2.06,10447.39),(28,4.85,398.15),
(26,3.48,571.34)]
_R1 = [(103019,1.10749,6283.07585),(1721,1.0644,12566.1517),(702,3.142,0),
(32,1.02,18849.23),(31,2.84,5507.55),(25,1.32,5223.69),(18,1.42,1577.34),
(10,5.91,10977.08),(9,1.42,6275.96),(9,0.27,5486.78)]
_R2 = [(4359,5.7846,6283.0758),(124,5.579,12566.152),(12,3.14,0),
(9,3.63,77713.77),(6,1.87,5573.14),(3,5.47,18849.23)]
_R3 = [(145,4.273,6283.076),(7,3.92,12566.15)]
_R4 = [(4,2.56,6283.08)]


def _ser(terms, tau):
    return sum(a * math.cos(b + c * tau) for a, b, c in terms)


def sun_longitude(jd_tt):
    """태양 겉보기 황경(도). VSOP87 절단급수. 오차 < 0.001도(≈1.5초)."""
    tau = (jd_tt - 2451545.0) / 365250.0
    L = (_ser(_L0, tau) + _ser(_L1, tau)*tau + _ser(_L2, tau)*tau**2
         + _ser(_L3, tau)*tau**3 + _ser(_L4, tau)*tau**4
         + _ser(_L5, tau)*tau**5) / 1e8
    R = (_ser(_R0, tau) + _ser(_R1, tau)*tau + _ser(_R2, tau)*tau**2
         + _ser(_R3, tau)*tau**3 + _ser(_R4, tau)*tau**4) / 1e8

    T = tau * 10
    theta = math.degrees(L) + 180.0 - 0.09033 / 3600.0

    om = math.radians(125.04452 - 1934.136261 * T)
    Ls = math.radians(280.4665 + 36000.7698 * T)
    Lm = math.radians(218.3165 + 481267.8813 * T)
    dpsi = (-17.20*math.sin(om) - 1.32*math.sin(2*Ls)
            - 0.23*math.sin(2*Lm) + 0.21*math.sin(2*om)) / 3600.0
    aberr = -20.4898 / R / 3600.0
    return (theta + dpsi + aberr) % 360


def julian_day(dt_utc):
    y, m = dt_utc.year, dt_utc.month
    d = (dt_utc.day + dt_utc.hour/24 + dt_utc.minute/1440
         + dt_utc.second/86400 + dt_utc.microsecond/86400e6)
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    b = 2 - a + a // 4
    return (math.floor(365.25*(y+4716)) + math.floor(30.6001*(m+1))
            + d + b - 1524.5)


def jd_to_datetime(jd):
    jd += 0.5
    z, f = math.floor(jd), jd - math.floor(jd)
    if z < 2299161:
        a = z
    else:
        al = math.floor((z - 1867216.25) / 36524.25)
        a = z + 1 + al - al // 4
    b = a + 1524
    c = math.floor((b - 122.1) / 365.25)
    d = math.floor(365.25 * c)
    e = math.floor((b - d) / 30.6001)
    day = b - d - math.floor(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    di = int(day)
    return datetime(year, month, di) + timedelta(seconds=(day - di) * 86400)


_DT_OBSERVED = {
    1972: 42.23, 1973: 43.37, 1974: 44.49, 1975: 45.48, 1976: 46.46,
    1977: 47.52, 1978: 48.53, 1979: 49.59, 1980: 50.54, 1981: 51.38,
    1982: 52.17, 1983: 52.96, 1984: 53.79, 1985: 54.34, 1986: 54.87,
    1987: 55.32, 1988: 55.82, 1989: 56.30, 1990: 56.86, 1991: 57.57,
    1992: 58.31, 1993: 59.12, 1994: 59.98, 1995: 60.78, 1996: 61.63,
    1997: 62.30, 1998: 62.97, 1999: 63.47, 2000: 63.83, 2001: 64.09,
    2002: 64.30, 2003: 64.47, 2004: 64.57, 2005: 64.69, 2006: 64.85,
    2007: 65.15, 2008: 65.46, 2009: 65.78, 2010: 66.07, 2011: 66.32,
    2012: 66.60, 2013: 66.91, 2014: 67.28, 2015: 67.64, 2016: 68.10,
    2017: 68.59, 2018: 68.97, 2019: 69.22, 2020: 69.36, 2021: 69.36,
    2022: 69.29, 2023: 69.20, 2024: 69.18,
}
_DT_OBS_MIN = min(_DT_OBSERVED)
_DT_OBS_MAX = max(_DT_OBSERVED)
_DT_TAPER_YEARS = 50.0


def _delta_t_polynomial(y):
    """Espenak & Meeus 다항식 (실측표가 없는 구간용)."""
    if y < 1600:
        u = (y - 1820) / 100.0
        return -20.0 + 32.0 * u * u
    if y < 1700:
        t = y - 1600
        return 120.0 - 0.9808*t - 0.01532*t**2 + t**3 / 7129.0
    if y < 1800:
        t = y - 1700
        return (8.83 + 0.1603*t - 0.0059285*t**2 + 0.00013336*t**3
                - t**4 / 1174000.0)
    if y < 1860:
        t = y - 1800
        return (13.72 - 0.332447*t + 0.0068612*t**2 + 0.0041116*t**3
                - 0.00037436*t**4 + 0.0000121272*t**5
                - 0.0000001699*t**6 + 0.000000000875*t**7)
    if y < 1900:
        t = y - 1860
        return (7.62 + 0.5737*t - 0.251754*t**2 + 0.01680668*t**3
                - 0.0004473624*t**4 + t**5 / 233174.0)
    if y < 1920:
        t = y - 1900
        return -2.79 + 1.494119*t - 0.0598939*t**2 + 0.0061966*t**3 - 0.000197*t**4
    if y < 1941:
        t = y - 1920
        return 21.20 + 0.84493*t - 0.076100*t**2 + 0.0020936*t**3
    if y < 1961:
        t = y - 1950
        return 29.07 + 0.407*t - t**2/233 + t**3/2547
    if y < 1986:
        t = y - 1975
        return 45.45 + 1.067*t - t**2/260 - t**3/718
    if y < 2005:
        t = y - 2000
        return (63.86 + 0.3345*t - 0.060374*t**2 + 0.0017275*t**3
                + 0.000651814*t**4 + 0.00002373599*t**5)
    if y < 2050:
        t = y - 2000
        return 62.92 + 0.32217*t + 0.005589*t**2
    if y < 2150:
        u = (y - 1820) / 100.0
        return -20.0 + 32.0 * u * u - 0.5628 * (2150.0 - y)
    u = (y - 1820) / 100.0
    return -20.0 + 32.0 * u * u


def delta_t(year):
    """ΔT = TT − UT (초). 실측표(1972~2024) 우선, 그 밖은 다항식.

    year 는 소수 연도를 받습니다(예: 1985.12). 정수만 넣으면 매년 1월 1일에
    계단형 불연속이 생기고, 그 불연속이 절기 시각을 몇 초씩 튀게 만듭니다.
    find_solar_term() 이 소수 연도를 넘기므로 구간 경계에서도 연속입니다.

    적용 범위는 1800~2150년입니다. 이 범위 밖은 Espenak & Meeus 의 장기
    포물선 근사로 떨어지며, 정확도가 크게 떨어지므로 실사용상 의미가 없습니다
    (이 앱의 대상은 근현대 한국 출생자입니다).

    ※ 이전 버전은 1900년 미만과 2050년 이상을 일괄 69.0 으로 반환해서,
       1899년은 약 72초, 2050년은 약 23초가 어긋났습니다(2049년 92.1초에서
       2050년 69.0초로 역행). ephem 교차검증에서 2040~2050년대 오차가
       급증한 원인이 이것이었습니다.
    """
    y = float(year)


    if _DT_OBS_MIN <= y <= _DT_OBS_MAX:
        lo = int(math.floor(y))
        if lo == _DT_OBS_MAX:
            return _DT_OBSERVED[lo]
        f = y - lo
        return _DT_OBSERVED[lo] * (1 - f) + _DT_OBSERVED[lo + 1] * f


    if y < _DT_OBS_MIN:
        gap = _DT_OBS_MIN - y
        if gap >= _DT_TAPER_YEARS:
            return _delta_t_polynomial(y)
        bias = _DT_OBSERVED[_DT_OBS_MIN] - _delta_t_polynomial(float(_DT_OBS_MIN))
        return _delta_t_polynomial(y) + bias * (1.0 - gap / _DT_TAPER_YEARS)


    gap = y - _DT_OBS_MAX
    if gap >= _DT_TAPER_YEARS:
        return _delta_t_polynomial(y)
    bias = _DT_OBSERVED[_DT_OBS_MAX] - _delta_t_polynomial(float(_DT_OBS_MAX))
    return _delta_t_polynomial(y) + bias * (1.0 - gap / _DT_TAPER_YEARS)


_term_cache = {}


def find_solar_term(year, index):
    """year년 index번째 절기의 UTC 시각. index 0 = 입춘(황경 315도)."""
    key = (year, index)
    if key in _term_cache:
        return _term_cache[key]
    target = (315 + index * 15) % 360
    jd = julian_day(datetime(year, 2, 4) + timedelta(days=index * 15.2))
    for _ in range(60):


        fy = 2000.0 + (jd - 2451545.0) / 365.25
        diff = (sun_longitude(jd + delta_t(fy)/86400.0) - target + 180) % 360 - 180
        if abs(diff) < 1e-9:
            break
        jd -= diff * 365.2422 / 360.0
    result = jd_to_datetime(jd)
    _term_cache[key] = result
    return result


def equation_of_time(jd_tt):
    T = (jd_tt - 2451545.0) / 36525.0
    l0 = math.radians((280.46646 + 36000.76983*T + 0.0003032*T*T) % 360)
    m = math.radians((357.52911 + 35999.05029*T - 0.0001537*T*T) % 360)
    e = 0.016708634 - 0.000042037*T - 0.0000001267*T*T
    y = math.tan(math.radians((23.439291 - 0.0130042*T) / 2)) ** 2
    eot = (y*math.sin(2*l0) - 2*e*math.sin(m) + 4*e*y*math.sin(m)*math.cos(2*l0)
           - 0.5*y*y*math.sin(4*l0) - 1.25*e*e*math.sin(2*m))
    return math.degrees(eot) * 4


"""천간·지지·오행 상수 및 관계 정의."""

GAN = "갑을병정무기경신임계"
JI = "자축인묘진사오미신유술해"
GAN_H = "甲乙丙丁戊己庚辛壬癸"
JI_H = "子丑寅卯辰巳午未申酉戌亥"


GAN_OHAENG = ["목", "목", "화", "화", "토", "토", "금", "금", "수", "수"]
JI_OHAENG = ["수", "토", "목", "목", "토", "화", "화", "토", "금", "금", "토", "수"]
OHAENG = ["목", "화", "토", "금", "수"]


GAN_YY = [i % 2 for i in range(10)]
JI_YY = [i % 2 for i in range(12)]


SAENG = {"목": "화", "화": "토", "토": "금", "금": "수", "수": "목"}
GEUK = {"목": "토", "토": "수", "수": "화", "화": "금", "금": "목"}
SAENG_BY = {v: k for k, v in SAENG.items()}
GEUK_BY = {v: k for k, v in GEUK.items()}


SIPSEONG_GROUP = {
    "비견": "비겁", "겁재": "비겁",
    "식신": "식상", "상관": "식상",
    "편재": "재성", "정재": "재성",
    "편관": "관성", "정관": "관성",
    "편인": "인성", "정인": "인성",
}


JIJANGGAN = {
    0:  [(9, 10), (9, 20)],
    1:  [(9, 9), (7, 3), (5, 18)],
    2:  [(4, 7), (2, 7), (0, 16)],
    3:  [(0, 10), (1, 20)],
    4:  [(1, 9), (8, 3), (4, 18)],
    5:  [(4, 7), (6, 7), (2, 16)],
    6:  [(2, 10), (5, 9), (3, 11)],
    7:  [(3, 9), (1, 3), (5, 18)],
    8:  [(4, 7), (8, 7), (6, 16)],
    9:  [(6, 10), (7, 20)],
    10: [(7, 9), (3, 3), (4, 18)],
    11: [(4, 7), (0, 7), (8, 16)],
}


def is_chung(a, b):
    return (a - b) % 12 == 6


YUKHAP = {
    frozenset((0, 1)): "토", frozenset((2, 11)): "목",
    frozenset((3, 10)): "화", frozenset((4, 9)): "금",
    frozenset((5, 8)): "수", frozenset((6, 7)): "토",
}


SAMHAP = {
    frozenset((8, 0, 4)): "수",
    frozenset((11, 3, 7)): "목",
    frozenset((2, 6, 10)): "화",
    frozenset((5, 9, 1)): "금",
}

BANHAP = {}
for _k, _v in SAMHAP.items():
    _m = sorted(_k)
    for _a in _m:
        for _b in _m:
            if _a < _b:
                BANHAP[frozenset((_a, _b))] = _v


BANGHAP = {
    frozenset((2, 3, 4)): "목", frozenset((5, 6, 7)): "화",
    frozenset((8, 9, 10)): "금", frozenset((11, 0, 1)): "수",
}


CHEONGAN_HAP = {
    frozenset((0, 5)): "토", frozenset((1, 6)): "금",
    frozenset((2, 7)): "수", frozenset((3, 8)): "목",
    frozenset((4, 9)): "화",
}


JI_SEASON = ["겨울", "겨울", "봄", "봄", "봄", "여름", "여름", "여름",
             "가을", "가을", "가을", "겨울"]


UNSEONG_NAMES = ["장생", "목욕", "관대", "건록", "제왕", "쇠",
                 "병", "사", "묘", "절", "태", "양"]
UNSEONG_START = [11, 6, 2, 9, 2, 9, 5, 0, 8, 3]
UNSEONG_DIR = [1, -1, 1, -1, 1, -1, 1, -1, 1, -1]


def sipseong(day_gan, target_gan):
    """일간 대비 대상 천간의 십성."""
    d, t = GAN_OHAENG[day_gan], GAN_OHAENG[target_gan]
    same = GAN_YY[day_gan] == GAN_YY[target_gan]
    if d == t:
        return "비견" if same else "겁재"
    if SAENG[d] == t:
        return "식신" if same else "상관"
    if GEUK[d] == t:
        return "편재" if same else "정재"
    if GEUK[t] == d:
        return "편관" if same else "정관"
    return "편인" if same else "정인"


def sipseong_by_ohaeng(day_gan, elem):
    """일간 대비 오행의 십성 그룹(비겁/식상/재성/관성/인성)."""
    d = GAN_OHAENG[day_gan]
    if d == elem:
        return "비겁"
    if SAENG[d] == elem:
        return "식상"
    if GEUK[d] == elem:
        return "재성"
    if GEUK[elem] == d:
        return "관성"
    return "인성"


def unseong(day_gan, ji):
    """십이운성."""
    start = UNSEONG_START[day_gan]
    direction = UNSEONG_DIR[day_gan]
    return UNSEONG_NAMES[((ji - start) * direction) % 12]


"""출생지 -> 경도 / 표준시 변환.

역대 표준시 변경과 서머타임은 파이썬 zoneinfo(IANA tzdata)에 위임합니다.
직접 하드코딩하지 않는 이유: 한국의 경우 1955~1960년은
표준시 UTC+8:30에 서머타임 1시간이 겹쳐 UTC+9:30이 되는 등
조합이 복잡해 수동 관리가 오류를 부르기 때문입니다.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Place:
    name: str
    longitude: float
    timezone: str

    @property
    def tz(self):
        return ZoneInfo(self.timezone)


_KR = "Asia/Seoul"
CITIES = {

    "서울": (126.98, _KR),
    "부산": (129.08, _KR),
    "대구": (128.60, _KR),
    "인천": (126.71, _KR),
    "광주": (126.85, _KR),
    "대전": (127.38, _KR),
    "울산": (129.31, _KR),
    "세종": (127.29, _KR),

    "경기도": (127.01, _KR),
    "강원도": (127.73, _KR),
    "충청북도": (127.49, _KR),
    "충청남도": (126.66, _KR),
    "전라북도": (127.15, _KR),
    "전라남도": (126.42, _KR),
    "경상북도": (128.69, _KR),
    "경상남도": (128.68, _KR),

    "제주도": (126.53, _KR),
    "울릉도": (130.91, _KR),
}


def list_cities():
    """등록된 지역명 목록."""
    return sorted(CITIES)


def classify_local_time(naive, tzinfo):
    """벽시계 시각의 종류를 판정합니다. -> "normal" / "ambiguous" / "imaginary"."""
    a = naive.replace(tzinfo=tzinfo, fold=0)
    b = naive.replace(tzinfo=tzinfo, fold=1)
    if a.utcoffset() == b.utcoffset():
        return "normal"
    roundtrip = a.astimezone(_tz.utc).astimezone(tzinfo).replace(tzinfo=None)
    return "ambiguous" if roundtrip == naive else "imaginary"


def resolve_place(spec, longitude=None, timezone=None):
    """
    출생지 문자열 -> Place.

    spec : 지역명 (예: "서울", "경상북도"). list_cities() 로 전체 목록 확인.
    longitude, timezone : 내부/과거 데이터 마이그레이션용으로만 남겨둔
        인자입니다. 이 버전의 UI는 버튼 선택만 제공하며 직접 입력 경로는
        없습니다 — 출생지의 정확한 경도를 아는 사용자가 거의 없어서,
        "목록에 없으면 직접 입력하라"는 예전 방식은 실사용성이 없었습니다.
    """
    lon, tzname, name = None, None, spec or "서울"

    if spec:
        key = spec.strip()
        if key in CITIES:
            lon, tzname = CITIES[key]
            name = key
        elif longitude is None or timezone is None:
            raise ValueError(
                f"'{spec}' 은(는) 등록되지 않은 지역입니다. "
                f"list_cities() 로 등록된 지역을 확인하세요: {', '.join(list_cities())}"
            )

    if longitude is not None:
        lon = float(longitude)
    if timezone is not None:
        tzname = timezone

    if lon is None or tzname is None:
        raise ValueError("경도와 타임존이 모두 필요합니다.")
    if not -180 <= lon <= 180:
        raise ValueError(f"경도 범위 오류: {lon}")
    try:
        ZoneInfo(tzname)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValueError(f"알 수 없는 타임존: {tzname}") from e

    return Place(name=name, longitude=lon, timezone=tzname)


"""사주 원국(四柱) 및 대운 구성."""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as _tz


JASI_SCHOOLS = ("야자시", "정자시")


@dataclass(frozen=True)
class Pillar:
    """간지 한 기둥."""
    gan: int
    ji: int

    @property
    def name(self):
        return GAN[self.gan] + JI[self.ji]

    @property
    def hanja(self):
        return GAN_H[self.gan] + JI_H[self.ji]

    @property
    def gapja(self):
        """육십갑자 순번 (甲子=0)."""
        return next(i for i in range(60)
                    if i % 10 == self.gan and i % 12 == self.ji)

    @classmethod
    def from_gapja(cls, n):
        n %= 60
        return cls(n % 10, n % 12)

    @property
    def jijanggan(self):
        return [g for g, _ in JIJANGGAN[self.ji]]

    def __str__(self):
        return f"{self.name}({self.hanja})"


def _jdn(d):
    """그레고리력 -> 율리우스 적일 번호."""
    y, m, dd = d.year, d.month, d.day
    a = (14 - m) // 12
    yy, mm = y + 4800 - a, m + 12 * a - 3
    return dd + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


@dataclass
class Chart:
    """계산된 사주 원국."""
    birth_local: datetime
    place: Place
    is_male: bool
    utc_offset: float
    is_dst: bool
    solar_time: datetime
    jasi_school: str
    year: Pillar
    month: Pillar
    day: Pillar
    hour: Pillar
    daeun_start: int
    daeun_forward: bool
    daeun: list
    warnings: list = field(default_factory=list)


    options: dict = field(default_factory=dict)

    @property
    def pillars(self):
        return [self.year, self.month, self.day, self.hour]

    @property
    def day_gan(self):
        return self.day.gan

    @property
    def day_ohaeng(self):
        return GAN_OHAENG[self.day_gan]

    def ohaeng_count(self, include_jijanggan=False):
        c = {k: 0 for k in "목화토금수"}
        for p in self.pillars:
            c[GAN_OHAENG[p.gan]] += 1
            c[JI_OHAENG[p.ji]] += 1
            if include_jijanggan:
                for g, days in JIJANGGAN[p.ji]:
                    c[GAN_OHAENG[g]] += days / 30.0
        return c

    def sipseong_map(self):
        d = self.day_gan
        labels = ["년", "월", "일", "시"]
        out = {}
        for lab, p in zip(labels, self.pillars):
            out[lab + "간"] = "일간(본인)" if lab == "일" else sipseong(d, p.gan)
            out[lab + "지"] = sipseong(d, JIJANGGAN[p.ji][-1][0])
        return out

    def unseong_map(self):
        return {lab: unseong(self.day_gan, p.ji)
                for lab, p in zip("년월일시", self.pillars)}

    def daeun_at(self, age):
        """해당 나이의 대운 (없으면 None)."""
        for start, p in self.daeun:
            if start <= age < start + 10:
                return start, p
        return None

    def seun(self, year):
        """해당 '세운 연도'의 간지.

        주의: 여기서 year 는 달력 연도가 아니라 '입춘으로 시작하는 해'
        입니다. 2024 는 2024-02-04 17:27 KST 부터 2025년 입춘 직전까지를
        가리킵니다. 달력 날짜로 찾으려면 seun_at(date) 를 쓰세요.

        ※ 예전 구현은 이 구분이 없어서, 2월 1일생과 2월 10일생의 그해
           세운이 같게 나왔습니다. 년주가 입춘에 바뀌는 것과 같은 원리로
           세운도 입춘에 바뀝니다.
        """
        return Pillar.from_gapja((year - 1984) % 60)

    def seun_at(self, when):
        """달력 날짜(date/datetime)가 속한 세운을 돌려줍니다.

        입춘 이전이면 전년도 세운입니다. 반환: (세운연도, Pillar)
        """
        if isinstance(when, datetime):
            d = when
        else:
            d = datetime(when.year, when.month, when.day, 12, 0)
        ipchun = find_solar_term(d.year, 0) + timedelta(hours=9)
        y = d.year if d >= ipchun else d.year - 1
        return y, self.seun(y)

    def seun_range(self, start_year, count=10):
        """연속한 세운 목록. [(세운연도, Pillar, 입춘시각KST), ...]"""
        out = []
        for y in range(start_year, start_year + count):
            out.append((y, self.seun(y),
                        find_solar_term(y, 0) + timedelta(hours=9)))
        return out


def build_chart(birth_year, birth_month, birth_day, birth_hour, birth_minute,
                is_male=True, place="서울", longitude=None, timezone=None,
                jasi_school="야자시", apply_longitude=True, apply_eot=False,
                edge_warn_minutes=30, daeun_count=9):
    """
    사주 원국과 대운을 계산합니다.

    Parameters
    ----------
    birth_* : int
        출생 연월일시분 (그 지역의 벽시계 시각 그대로)
    is_male : bool
        성별. 대운 순행/역행 판정에 사용
    place : str
        도시명. location.list_cities() 참조
    longitude, timezone : float, str
        도시 목록에 없는 경우 직접 지정
    jasi_school : {"야자시", "정자시"}
        23시대 출생자의 일주 처리 기준. 유파에 따라 갈립니다.
    apply_longitude : bool
        진태양시 보정 여부. False면 표준자오선 기준
    apply_eot : bool
        균시차 보정 여부. 명리 실무에서는 대개 생략합니다
    """
    if jasi_school not in JASI_SCHOOLS:
        raise ValueError(f"jasi_school은 {JASI_SCHOOLS} 중 하나여야 합니다.")

    loc = resolve_place(place, longitude, timezone)
    warnings = []


    naive = datetime(birth_year, birth_month, birth_day, birth_hour, birth_minute)


    kind = classify_local_time(naive, loc.tz)
    if kind == "ambiguous":
        alt = naive.replace(tzinfo=loc.tz, fold=1)
        warnings.append(
            f"서머타임 해제 시점과 겹칩니다. {naive:%Y-%m-%d %H:%M} 은(는) "
            f"이 날 벽시계에 두 번 나타난 시각이라, 출생기록만으로는 "
            f"어느 쪽인지 알 수 없습니다. 앞쪽(UTC+"
            f"{naive.replace(tzinfo=loc.tz, fold=0).utcoffset().total_seconds() / 3600:g})"
            f"으로 계산했으며, 뒤쪽(UTC+"
            f"{alt.utcoffset().total_seconds() / 3600:g})이면 결과가 달라질 수 "
            f"있습니다. 특히 23시대라면 일주(日柱)가 하루 갈립니다.")
    elif kind == "imaginary":
        warnings.append(
            f"{naive:%Y-%m-%d %H:%M} 은(는) 서머타임 시행으로 그 날 "
            f"실제로는 존재하지 않았던 시각입니다. 출생 기록이 서머타임을 "
            f"반영하지 않았을 가능성이 큽니다. 아래 결과는 참고로만 보시고, "
            f"가족·병원 기록으로 시각을 재확인하세요.")

    aware = naive.replace(tzinfo=loc.tz)
    utc = aware.astimezone(_tz.utc).replace(tzinfo=None)
    off = aware.utcoffset().total_seconds() / 3600
    dst = aware.dst().total_seconds() / 3600

    if dst:
        warnings.append(
            f"서머타임 시행 기간입니다(UTC+{off:g}). 표준시로는 "
            f"{(naive - timedelta(hours=dst)):%H:%M} 에 해당하며, "
            f"이를 반영해 계산했습니다.")


    if abs(off - dst - 8.5) < 1e-9:
        alt_hour = (naive + timedelta(minutes=30))
        warnings.append(
            f"1954~1961년은 법정 표준시가 UTC+8:30 이던 구간입니다. "
            f"이 기준으로 계산했습니다. 다만 당시 기록이 관행적으로 "
            f"UTC+9:00 으로 적힌 사례가 있어, 그 경우 실제 출생시각은 "
            f"{alt_hour:%H:%M} 에 해당합니다. 시주가 경계에 가깝다면 "
            f"양쪽을 모두 확인하세요.")


    shift = loc.longitude / 15.0 if apply_longitude else off
    solar = utc + timedelta(hours=shift)
    if apply_eot:
        solar += timedelta(minutes=equation_of_time(
            julian_day(utc) + delta_t(birth_year) / 86400.0))

    def to_solar(dt_utc):
        return dt_utc + timedelta(hours=shift)


    ref = solar + timedelta(hours=1) if (
        jasi_school == "정자시" and solar.hour == 23) else solar


    y = ref.year
    if ref < to_solar(find_solar_term(y, 0)):
        y -= 1
    yp = Pillar.from_gapja((y - 1984) % 60)


    branch, latest = 1, None
    for cy in (ref.year - 1, ref.year):
        for i in JEOL_TO_BRANCH:
            t = to_solar(find_solar_term(cy, i))
            if t <= ref and (latest is None or t > latest):
                latest, branch = t, JEOL_TO_BRANCH[i]
    inwol = ((yp.gan % 5) * 2 + 2) % 10
    mp = Pillar((inwol + (branch - 2) % 12) % 10, branch)


    di = (_jdn(ref) + 49) % 60
    dp = Pillar.from_gapja(di)


    hb = ((solar.hour + 1) // 2) % 12
    hp = Pillar(((dp.gan % 5) * 2 + hb) % 10, hb)


    if solar.hour == 23:
        other = "정자시" if jasi_school == "야자시" else "야자시"
        warnings.append(
            f"진태양시 23시대 출생입니다. '{jasi_school}설'로 계산했으며, "
            f"'{other}설'을 쓰는 만세력과는 일주가 하루 다르게 나옵니다.")

    for cy in (ref.year - 1, ref.year, ref.year + 1):
        for i in range(24):
            gap = abs((ref - to_solar(find_solar_term(cy, i))).total_seconds()) / 60
            if gap < edge_warn_minutes:
                warnings.append(
                    f"{SOLAR_TERMS[i]} 절입 시각과 {gap:.0f}분 차이입니다. "
                    f"년주·월주가 갈리는 경계이니 한국천문연구원 등 "
                    f"공식 절기 시각으로 재확인하세요.")


    forward = (yp.gan % 2 == 0) == is_male
    jeols = sorted(to_solar(find_solar_term(yy, i))
                   for yy in (ref.year - 1, ref.year, ref.year + 1)
                   for i in JEOL_TO_BRANCH)
    if forward:
        days = (min(t for t in jeols if t > ref) - ref).total_seconds() / 86400
    else:
        days = (ref - max(t for t in jeols if t <= ref)).total_seconds() / 86400
    start_age = max(1, min(10, round(days / 3)))

    step = 1 if forward else -1
    daeun = [(start_age + i * 10, Pillar.from_gapja(mp.gapja + (i + 1) * step))
             for i in range(daeun_count)]

    return Chart(
        birth_local=naive, place=loc, is_male=is_male,
        utc_offset=off, is_dst=bool(dst), solar_time=solar,
        jasi_school=jasi_school,
        year=yp, month=mp, day=dp, hour=hp,
        daeun_start=start_age, daeun_forward=forward, daeun=daeun,
        warnings=warnings,
        options={
            "apply_longitude": bool(apply_longitude),
            "apply_eot": bool(apply_eot),
            "edge_warn_minutes": edge_warn_minutes,
            "daeun_count": daeun_count,
            "longitude_override": longitude,
            "timezone_override": timezone,
            "local_time_kind": kind,
        },
    )


"""
사주 분석: 신강신약 판정, 용신 추출, 대운 길흉 채점.

╔══════════════════════════════════════════════════════════════╗
║  주의                                                        ║
║  이 모듈이 계산하는 "점수"는 억부용신(抑扶用神)이라는          ║
║  전통 명리학의 한 유파를 코드로 옮긴 것입니다.                ║
║  검증된 예측이 아니며, 다른 유파(조후·격국·병약용신 등)는     ║
║  같은 사주를 다르게 판정합니다.                               ║
║  모든 판정에는 근거(reasons)가 함께 반환되므로,               ║
║  사용자가 결론이 아니라 근거를 보고 스스로 판단하도록          ║
║  설계했습니다.                                                ║
╚══════════════════════════════════════════════════════════════╝
"""

from dataclasses import dataclass, field


POSITION_WEIGHT = {
    "년간": 0.8, "월간": 1.2, "시간": 1.0,
    "년지": 1.0, "월지": 3.0, "일지": 1.5, "시지": 1.2,
}

STRENGTH_BANDS = [
    (0.00, 0.32, "극신약", "일간이 매우 약합니다"),
    (0.32, 0.45, "신약", "일간이 약한 편입니다"),
    (0.45, 0.55, "중화", "일간이 균형에 가깝습니다"),
    (0.55, 0.68, "신강", "일간이 강한 편입니다"),
    (0.68, 1.01, "극신강", "일간이 매우 강합니다"),
]


@dataclass
class Strength:
    ratio: float
    label: str
    description: str
    ally: float
    enemy: float
    details: list = field(default_factory=list)


@dataclass
class Analysis:
    chart: object
    strength: Strength
    yongsin: list
    gisin: list
    neutral: list
    favor: dict
    reasons: list
    johu_note: str = ""


def measure_strength(chart):
    """일간의 강약을 위치 가중 합으로 측정."""
    dg = chart.day_gan
    ally = enemy = 0.0
    details = []

    slots = [
        ("년간", GAN_OHAENG[chart.year.gan]),
        ("월간", GAN_OHAENG[chart.month.gan]),
        ("시간", GAN_OHAENG[chart.hour.gan]),
        ("년지", JI_OHAENG[chart.year.ji]),
        ("월지", JI_OHAENG[chart.month.ji]),
        ("일지", JI_OHAENG[chart.day.ji]),
        ("시지", JI_OHAENG[chart.hour.ji]),
    ]

    for pos, elem in slots:
        w = POSITION_WEIGHT[pos]
        group = sipseong_by_ohaeng(dg, elem)
        if group in ("비겁", "인성"):
            ally += w
            side = "아군"
        else:
            enemy += w
            side = "적군"
        details.append((pos, elem, group, side, w))

    total = ally + enemy
    ratio = ally / total if total else 0.5

    for lo, hi, label, desc in STRENGTH_BANDS:
        if lo <= ratio < hi:
            break

    return Strength(ratio=ratio, label=label, description=desc,
                    ally=ally, enemy=enemy, details=details)


def _johu_adjust(chart, favor, reasons):
    """
    조후(調候) 보정.
    사주가 지나치게 뜨겁거나(火土 과다) 차가우면(水金 과다)
    억부 결론과 무관하게 온도를 맞추는 오행을 우선합니다.
    """
    c = chart.ohaeng_count()
    hot = c["화"] + c["토"] * 0.5
    cold = c["수"] + c["금"] * 0.5
    season = JI_SEASON[chart.month.ji]
    note = ""

    if hot >= 4.0 and c["수"] <= 1:
        favor["수"] = min(1.0, favor.get("수", 0) + 0.5)
        favor["금"] = min(1.0, favor.get("금", 0) + 0.2)
        note = (f"사주에 불·흙 기운이 몰려 있고 물이 {int(c['수'])}개뿐입니다. "
                f"열을 식히는 물 기운이 특히 귀합니다.")
        reasons.append("조후: 조열(燥熱)한 사주 → 水 가산")
    elif cold >= 4.0 and c["화"] <= 1:
        favor["화"] = min(1.0, favor.get("화", 0) + 0.5)
        favor["목"] = min(1.0, favor.get("목", 0) + 0.2)
        note = (f"사주에 물·쇠 기운이 몰려 있고 불이 {int(c['화'])}개뿐입니다. "
                f"온기를 주는 불 기운이 특히 귀합니다.")
        reasons.append("조후: 한습(寒濕)한 사주 → 火 가산")
    elif season == "겨울" and c["화"] == 0:
        favor["화"] = min(1.0, favor.get("화", 0) + 0.3)
        note = "겨울에 태어났는데 불이 없어 온기가 아쉽습니다."
        reasons.append("조후: 겨울생 무화(無火) → 火 가산")
    elif season == "여름" and c["수"] == 0:
        favor["수"] = min(1.0, favor.get("수", 0) + 0.3)
        note = "여름에 태어났는데 물이 없어 갈증이 있습니다."
        reasons.append("조후: 여름생 무수(無水) → 水 가산")

    return note


def analyze(chart):
    """사주를 분석해 용신·기신과 그 근거를 반환."""
    st = measure_strength(chart)
    dg = chart.day_gan
    reasons = []

    reasons.append(
        f"일간 {GAN_H[dg]}({GAN_OHAENG[dg]})의 아군(비겁+인성) 가중치 "
        f"{st.ally:.1f} vs 적군(식상+재성+관성) {st.enemy:.1f} "
        f"→ 비율 {st.ratio:.0%} → {st.label}")

    favor = {k: 0.0 for k in "목화토금수"}
    d_elem = GAN_OHAENG[dg]


    inseong = SAENG_BY[d_elem]
    bigyeop = d_elem
    siksang = SAENG[d_elem]
    jaeseong = GEUK[d_elem]
    gwanseong = GEUK_BY[d_elem]

    if st.label in ("극신약", "신약"):
        mag = 1.0 if st.label == "극신약" else 0.8
        favor[inseong] += mag
        favor[bigyeop] += mag * 0.9
        favor[gwanseong] -= mag
        favor[siksang] -= mag * 0.7
        favor[jaeseong] -= mag * 0.8
        reasons.append(
            f"{st.label}이므로 일간을 돕는 인성({inseong})·비겁({bigyeop})이 "
            f"희용신, 힘을 빼는 관성({gwanseong})·식상({siksang})·"
            f"재성({jaeseong})이 기구신입니다.")
    elif st.label in ("극신강", "신강"):
        mag = 1.0 if st.label == "극신강" else 0.8
        favor[siksang] += mag * 0.9
        favor[jaeseong] += mag
        favor[gwanseong] += mag * 0.8
        favor[inseong] -= mag
        favor[bigyeop] -= mag * 0.9
        reasons.append(
            f"{st.label}이므로 힘을 덜어내는 식상({siksang})·재성({jaeseong})·"
            f"관성({gwanseong})이 희용신, 더 보태는 인성({inseong})·"
            f"비겁({bigyeop})이 기구신입니다.")
    else:

        c = chart.ohaeng_count()
        lack = sorted(c, key=lambda k: c[k])[:2]
        for e in lack:
            favor[e] += 0.5
        excess = max(c, key=lambda k: c[k])
        favor[excess] -= 0.4
        reasons.append(
            f"중화 사주이므로 강한 억부 처방보다 부족한 오행"
            f"({', '.join(lack)})을 채우는 쪽으로 봅니다.")

    johu = _johu_adjust(chart, favor, reasons)


    for k in favor:
        favor[k] = max(-1.0, min(1.0, favor[k]))

    yongsin = sorted([k for k, v in favor.items() if v >= 0.3],
                     key=lambda k: -favor[k])
    gisin = sorted([k for k, v in favor.items() if v <= -0.3],
                   key=lambda k: favor[k])
    neutral = [k for k in "목화토금수" if k not in yongsin and k not in gisin]

    return Analysis(chart=chart, strength=st, yongsin=yongsin, gisin=gisin,
                    neutral=neutral, favor=favor, reasons=reasons,
                    johu_note=johu)


GAN_WEIGHT, JI_WEIGHT = 0.4, 0.6

GRADE_BANDS = [
    (0.55, "매우 좋음", "★★★★★"),
    (0.20, "좋음", "★★★★☆"),
    (-0.20, "보통", "★★★☆☆"),
    (-0.55, "어려움", "★★☆☆☆"),
    (-9.99, "매우 어려움", "★☆☆☆☆"),
]


def score_daeun(analysis, pillar, age=None):
    """
    대운 한 기둥의 길흉 점수(-1.0 ~ +1.0)와 근거를 반환.
    """
    ch = analysis.chart
    favor = analysis.favor
    notes = []

    g_elem = GAN_OHAENG[pillar.gan]
    j_elem = JI_OHAENG[pillar.ji]

    raw = favor[g_elem] * GAN_WEIGHT + favor[j_elem] * JI_WEIGHT

    def label(e):
        v = favor[e]
        return "도움" if v >= 0.3 else ("부담" if v <= -0.3 else "중립")

    notes.append(f"천간 {GAN_H[pillar.gan]}({g_elem}) {label(g_elem)}")
    notes.append(f"지지 {JI_H[pillar.ji]}({j_elem}) {label(j_elem)}")


    chung_targets = []
    for lab, p in zip("년월일시", ch.pillars):
        if is_chung(pillar.ji, p.ji):
            chung_targets.append(lab)
    if chung_targets:
        penalty = 0.12 * len(chung_targets)

        if "월" in chung_targets or "일" in chung_targets:
            penalty += 0.08
        raw -= penalty
        notes.append(
            f"{JI_H[pillar.ji]}가 원국 {'·'.join(chung_targets)}지와 충 "
            f"→ 변동·이동 요인 (-{penalty:.2f})")


    for lab, p in zip("년월일시", ch.pillars):
        key = frozenset((pillar.ji, p.ji))
        if key in BANHAP and pillar.ji != p.ji:
            elem = BANHAP[key]
            adj = favor[elem] * 0.15
            raw += adj
            if abs(adj) >= 0.03:
                notes.append(
                    f"{JI_H[pillar.ji]}+{JI_H[p.ji]} 반합 → {elem} 기운 "
                    f"({'강화' if adj > 0 else '부담'} {adj:+.2f})")


    for lab, p in zip("년월일시", ch.pillars):
        key = frozenset((pillar.ji, p.ji))
        if key in YUKHAP:
            notes.append(f"{JI_H[pillar.ji]}+{JI_H[p.ji]} 육합 → 관계·인연 변동")

    raw = max(-1.0, min(1.0, raw))

    for threshold, grade, stars in GRADE_BANDS:
        if raw >= threshold:
            break

    return {
        "age": age, "pillar": pillar, "score": raw,
        "grade": grade, "stars": stars,
        "percent": int(round((raw + 1) * 50)),
        "notes": notes,
        "theme": _theme(analysis, pillar),
    }


def _theme(analysis, pillar):
    """대운의 성격을 십성 그룹으로 요약."""
    dg = analysis.chart.day_gan
    groups = {sipseong_by_ohaeng(dg, GAN_OHAENG[pillar.gan]),
              sipseong_by_ohaeng(dg, JI_OHAENG[pillar.ji])}
    texts = {
        "비겁": "자기 주장과 인맥이 강해지는 시기. 독립·경쟁·동업 이슈",
        "식상": "표현하고 만들어내는 시기. 재능·창작·자녀 이슈",
        "재성": "재물과 실리를 좇는 시기. 사업·이성·현실 감각 이슈",
        "관성": "책임과 자리가 커지는 시기. 직장·명예·압박 이슈",
        "인성": "배우고 안정을 찾는 시기. 학습·자격·문서 이슈",
    }
    return " / ".join(texts[g] for g in
                      sorted(groups, key=lambda g: list(texts).index(g)))


def score_all_daeun(analysis):
    return [score_daeun(analysis, p, age) for age, p in analysis.chart.daeun]


"""사람이 읽을 수 있는 형태로 결과를 출력합니다."""

from datetime import date


DISCLAIMER = (
    "이 결과는 명리학(사주)이라는 동아시아 전통 해석 체계를 코드로 옮긴 것입니다.\n"
    "  과학적으로 검증된 예측이 아니며, 유파에 따라 판정이 달라집니다.\n"
    "  진로·재산·건강·인간관계의 실제 결정은 현실 조건을 근거로 내리시고,\n"
    "  이 결과는 자기 성찰의 참고 자료로만 사용하세요."
)


ILGAN_DESC = {
    0: ("큰 나무", "곧게 자라는 힘. 리더십과 명분을 중시하고, 굽히기 어려워합니다."),
    1: ("풀과 넝쿨", "유연하고 적응이 빠릅니다. 실속을 챙기되 우유부단할 수 있습니다."),
    2: ("태양", "밝고 드러내는 성향. 솔직하고 열정적이나 뒤끝 없이 급합니다."),
    3: ("촛불·등불", "따뜻하고 섬세합니다. 배려가 깊지만 기복이 있습니다."),
    4: ("큰 산", "묵직하고 신뢰감 있습니다. 포용력이 크나 변화에 느립니다."),
    5: ("논밭의 흙", "실용적이고 꼼꼼합니다. 다 받아주지만 속을 잘 안 보입니다."),
    6: ("무쇠·원석", "결단력 있고 강직합니다. 의리를 중시하나 거칠 수 있습니다."),
    7: ("보석", "예민하고 깔끔합니다. 자존심이 강하고 상처를 오래 담아둡니다."),
    8: ("큰 강물", "포용력 있고 지혜롭습니다. 흐름을 잘 타지만 종잡기 어렵습니다."),
    9: ("이슬·시냇물", "차분하고 치밀합니다. 생각이 깊으나 걱정도 많습니다."),
}

OHAENG_ADVICE = {
    "목": ("동쪽", "초록·청색", "숲·나무·성장하는 것", "간·담"),
    "화": ("남쪽", "빨강·주황", "빛·열정·표현하는 것", "심장·소장"),
    "토": ("중앙", "노랑·갈색", "땅·안정·중재하는 것", "위·비장"),
    "금": ("서쪽", "흰색·금속색", "정리·결단·다듬는 것", "폐·대장"),
    "수": ("북쪽", "검정·파랑", "물·지혜·흐르는 것", "신장·방광"),
}


def _bar(percent, width=20):
    filled = int(round(percent / 100 * width))
    return "█" * filled + "░" * (width - filled)


def render_text(chart, today=None, width=64):
    """전체 리포트(v1)를 문자열로 반환.

    ※ 이 함수는 v1 분석 스키마(theme 키 등)에 묶여 있습니다.
       v2 의 化局 참고 판정(#3)은 render_hwaguk_section() 을 따로 쓰세요.
    """
    a = analyze(chart)
    scores = score_all_daeun(a)
    today = today or date.today()
    age = today.year - chart.birth_local.year + 1

    L = []
    add = L.append
    line = "═" * width
    thin = "─" * width


    add(line)
    add("  사주 분석 결과")
    add(line)
    add(f"  출생   : {chart.birth_local:%Y년 %m월 %d일 %H시 %M분}"
        f"  ({'남성' if chart.is_male else '여성'})")
    add(f"  출생지 : {chart.place.name} (동경 {chart.place.longitude:.2f}°)")
    add(f"  표준시 : UTC{chart.utc_offset:+g}"
        + ("  ※ 서머타임 적용 기간" if chart.is_dst else ""))
    add(f"  진태양시: {chart.solar_time:%Y-%m-%d %H:%M}"
        f"   |  자시 기준: {chart.jasi_school}설")


    add("")
    add(f"{'[ 사주 원국 ]':^{width}}")
    add(thin)
    order = [chart.hour, chart.day, chart.month, chart.year]
    add("".join(f"{h:^16}" for h in ["시주", "일주", "월주", "년주"]))
    add("".join(f"{GAN_H[p.gan]:^17}" for p in order))
    add("".join(f"{JI_H[p.ji]:^17}" for p in order))
    add("".join(f"{p.name:^16}" for p in order))


    c = chart.ohaeng_count()
    add("")
    add("  오행 분포")
    for k in "목화토금수":
        n = c[k]
        mark = "●" * int(n) if n else "○ 없음"
        tag = ""
        if k in a.yongsin:
            tag = "  ← 도움이 되는 기운"
        elif k in a.gisin:
            tag = "  ← 부담이 되는 기운"
        add(f"    {k}  {mark:<10} {int(n)}개{tag}")


    nick, desc = ILGAN_DESC[chart.day_gan]
    add("")
    add(f"{'[ 나는 어떤 사람인가 ]':^{width}}")
    add(thin)
    add(f"  일간 {GAN_H[chart.day_gan]}({chart.day_ohaeng}) — {nick}")
    add(f"  {desc}")
    add("")
    add(f"  기운의 세기: {a.strength.label} ({a.strength.ratio:.0%})")
    add(f"  {a.strength.description}. "
        f"내 편 {a.strength.ally:.1f} vs 상대 {a.strength.enemy:.1f}")
    if a.johu_note:
        add(f"  {a.johu_note}")


    add("")
    add("  도움이 되는 기운: " + (", ".join(a.yongsin) or "뚜렷하지 않음"))
    add("  부담이 되는 기운: " + (", ".join(a.gisin) or "뚜렷하지 않음"))
    if a.yongsin:
        d, col, thing, organ = OHAENG_ADVICE[a.yongsin[0]]
        add(f"    → 방위 {d} / 색 {col} / {thing} 가까이")
    if a.gisin:
        _, _, _, organ = OHAENG_ADVICE[a.gisin[0]]
        add(f"    → 건강은 {organ} 계통을 특히 살피세요")


    add("")
    add(f"{'[ 10년 주기 흐름 (대운) ]':^{width}}")
    add(thin)
    add(f"  {chart.daeun_start}세부터 시작, "
        f"{'순행' if chart.daeun_forward else '역행'}")
    add("")
    for s in scores:
        cur = "▶" if s["age"] <= age < s["age"] + 10 else " "
        add(f" {cur} {s['age']:>2}~{s['age']+9:>2}세  {s['pillar'].hanja}  "
            f"{_bar(s['percent'])} {s['grade']}")
        add(f"      {s['theme']}")
        for n in s["notes"][:3]:
            add(f"        · {n}")
        add("")


    add(f"{'[ 종합 결론 ]':^{width}}")
    add(thin)
    for para in _conclusion(chart, a, scores, age):
        add(_wrap(para, width - 4, "  "))
        add("")


    if chart.warnings:
        add("  ⚠ 계산상 주의사항")
        for w in chart.warnings:
            add(_wrap("· " + w, width - 6, "    "))
        add("")

    add(thin)
    add("  ※ " + DISCLAIMER.replace("\n", "\n  "))
    add(line)
    return "\n".join(L)


def render_text_v2(chart, a2=None, today=None, width=64):
    """전체 리포트(v2)를 문자열로 반환.

    render_text() 와 같은 구조를, 지장간·통근·계절·종격을 반영하는
    v2 판정(analyze_v2, score_all_daeun_v2)으로 채웁니다.
    export_text() 의 본문은 이 함수를 사용합니다 — v1 render_text() 를
    쓰던 이전 버전은 사람이 읽는 리포트가 v1 강약/용신 기준으로 나오는
    문제가 있었습니다.
    """
    a2 = a2 or analyze_v2(chart)
    scores = score_all_daeun_v2(a2)
    for s in scores:
        s["theme"] = _theme(a2, s["pillar"])
    today = today or date.today()
    age = today.year - chart.birth_local.year + 1

    L = []
    add = L.append
    line = "═" * width
    thin = "─" * width


    add(line)
    add("  사주 분석 결과 (V2 — 지장간·통근·계절·종격 반영)")
    add(line)
    add(f"  출생   : {chart.birth_local:%Y년 %m월 %d일 %H시 %M분}"
        f"  ({'남성' if chart.is_male else '여성'})")
    add(f"  출생지 : {chart.place.name} (동경 {chart.place.longitude:.2f}°)")
    add(f"  표준시 : UTC{chart.utc_offset:+g}"
        + ("  ※ 서머타임 적용 기간" if chart.is_dst else ""))
    add(f"  진태양시: {chart.solar_time:%Y-%m-%d %H:%M}"
        f"   |  자시 기준: {chart.jasi_school}설")


    add("")
    add(f"{'[ 사주 원국 ]':^{width}}")
    add(thin)
    order = [chart.hour, chart.day, chart.month, chart.year]
    add("".join(f"{h:^16}" for h in ["시주", "일주", "월주", "년주"]))
    add("".join(f"{GAN_H[p.gan]:^17}" for p in order))
    add("".join(f"{JI_H[p.ji]:^17}" for p in order))
    add("".join(f"{p.name:^16}" for p in order))


    c = chart.ohaeng_count()
    add("")
    add("  오행 분포")
    for k in "목화토금수":
        n = c[k]
        mark = "●" * int(n) if n else "○ 없음"
        tag = ""
        if k in a2.yongsin:
            tag = "  ← 도움이 되는 기운"
        elif k in a2.gisin:
            tag = "  ← 부담이 되는 기운"
        add(f"    {k}  {mark:<10} {int(n)}개{tag}")


    nick, desc = ILGAN_DESC[chart.day_gan]
    add("")
    add(f"{'[ 나는 어떤 사람인가 ]':^{width}}")
    add(thin)
    add(f"  일간 {GAN_H[chart.day_gan]}({chart.day_ohaeng}) — {nick}")
    add(f"  {desc}")
    add("")
    add(f"  기운의 세기: {a2.strength.label} ({a2.strength.ratio:.0%})")
    add(f"  {a2.strength.description}. "
        f"내 편 {a2.strength.ally:.1f} vs 상대 {a2.strength.enemy:.1f}")
    if a2.strength.confidence != "확실":
        add(f"  ⚠ 판정 신뢰도: 경계 — '{a2.strength.alt_label}'과의 경계 구간입니다. "
            f"두 시나리오가 갈리는 구간은 다른 근거로 함께 판단하세요.")
    if a2.special:
        add(f"  ★ {a2.special['name']} 로 판정 — 억부 결론을 반전시킵니다.")
    if a2.johu_note:
        add(f"  {a2.johu_note}")


    if a2.gyeokguk:
        gk = a2.gyeokguk
        add("")
        add(f"  격국 교차검증: {gk['gyeok_name']} · {gk['verdict']}")
        add(_wrap(gk["note"], width - 4, "    "))


    add("")
    add("  도움이 되는 기운: " + (", ".join(a2.yongsin) or "뚜렷하지 않음"))
    add("  부담이 되는 기운: " + (", ".join(a2.gisin) or "뚜렷하지 않음"))
    if a2.yongsin:
        d, col, thing, organ = OHAENG_ADVICE[a2.yongsin[0]]
        add(f"    → 방위 {d} / 색 {col} / {thing} 가까이")
    if a2.gisin:
        _, _, _, organ = OHAENG_ADVICE[a2.gisin[0]]
        add(f"    → 건강은 {organ} 계통을 특히 살피세요")


    add("")
    add(f"{'[ 10년 주기 흐름 (대운) ]':^{width}}")
    add(thin)
    add(f"  {chart.daeun_start}세부터 시작, "
        f"{'순행' if chart.daeun_forward else '역행'}")
    add("")
    for s in scores:
        cur = "▶" if s["age"] <= age < s["age"] + 10 else " "
        rank_txt = f"  (본인 대운 {len(scores)}구간 중 {s['rank']}위)" if "rank" in s else ""
        add(f" {cur} {s['age']:>2}~{s['age']+9:>2}세  {s['pillar'].hanja}  "
            f"{_bar(s['percent'])} {s['grade']}{rank_txt}")
        add(f"      {s['theme']}")
        for n in s["notes"][:3]:
            add(f"        · {n}")
        add("")


    add(f"{'[ 종합 결론 ]':^{width}}")
    add(thin)
    for para in _conclusion(chart, a2, scores, age):
        add(_wrap(para, width - 4, "  "))
        add("")


    if chart.warnings:
        add("  ⚠ 계산상 주의사항")
        for w in chart.warnings:
            add(_wrap("· " + w, width - 6, "    "))
        add("")

    add(thin)
    add("  ※ " + DISCLAIMER.replace("\n", "\n  "))
    add(line)
    return "\n".join(L)


def _wrap(text, width, indent=""):
    out, cur = [], indent
    for word in text.split():
        if len(cur) + len(word) + 1 > width + len(indent):
            out.append(cur)
            cur = indent + word
        else:
            cur = (cur + " " + word) if cur.strip() else indent + word
    if cur.strip():
        out.append(cur)
    return "\n".join(out)


def _conclusion(chart, a, scores, age):
    """종합 결론 문단들을 생성."""
    paras = []
    best = max(scores, key=lambda s: s["score"])
    worst = min(scores, key=lambda s: s["score"])
    cur = next((s for s in scores if s["age"] <= age < s["age"] + 10), None)

    nick, _ = ILGAN_DESC[chart.day_gan]
    paras.append(
        f"당신을 나타내는 글자는 {GAN_H[chart.day_gan]}, "
        f"'{nick}'에 비유하는 {chart.day_ohaeng} 기운입니다. "
        f"사주 전체로 보면 {a.strength.label}이라, "
        + ("스스로를 채우고 도와주는 기운이 필요합니다."
           if a.strength.label in ("극신약", "신약")
           else "가진 힘을 밖으로 풀어내는 쪽이 맞습니다."
           if a.strength.label in ("신강", "극신강")
           else "한쪽으로 치우치지 않아 상황에 맞춰 조절하는 편이 낫습니다."))

    if cur:
        paras.append(
            f"지금은 {cur['age']}~{cur['age']+9}세 {cur['pillar'].hanja} 대운, "
            f"열 단계 중 '{cur['grade']}'에 해당하는 구간입니다. "
            f"{cur['theme']}가 이 시기의 주된 화두입니다.")

    if best["age"] <= age < best["age"] + 10:
        paras.append(
            f"주목할 점은 지금이 인생 전체에서 가장 좋게 나온 구간이라는 것입니다. "
            f"{best['age']}세부터 {best['age']+9}세까지가 흐름의 정점이니, "
            f"미루던 일이 있다면 이 시기에 꺼내는 편이 낫습니다.")
    elif best["age"] > age:
        paras.append(
            f"흐름의 정점은 {best['age']}~{best['age']+9}세 "
            f"{best['pillar'].hanja} 대운으로 나옵니다. "
            f"지금부터 그 시기를 향해 준비해두면 힘을 크게 받습니다.")
    else:
        paras.append(
            f"흐름의 정점은 {best['age']}~{best['age']+9}세 구간이었습니다. "
            f"그때 쌓은 것이 이후의 바탕이 됩니다.")

    if worst["age"] > age:
        paras.append(
            f"반대로 {worst['age']}~{worst['age']+9}세 "
            f"{worst['pillar'].hanja} 대운은 부담이 큰 구간으로 나옵니다. "
            f"이 시기에는 크게 벌이기보다 지키는 쪽이 안전합니다.")
    elif worst["age"] <= age < worst["age"] + 10:
        paras.append(
            f"가장 힘든 구간으로 나온 {worst['age']}~{worst['age']+9}세를 "
            f"지금 지나가고 있습니다. 크게 벌이기보다 지키는 쪽이 안전합니다.")
    else:
        paras.append(
            f"가장 힘든 구간으로 나온 {worst['age']}~{worst['age']+9}세는 "
            f"이미 지났습니다.")

    if a.yongsin:
        d, col, thing, _ = OHAENG_ADVICE[a.yongsin[0]]
        paras.append(
            f"생활에서 챙길 것은 {a.yongsin[0]} 기운입니다. "
            f"{d} 방향, {col} 계열, {thing}을 가까이하면 좋다고 봅니다. "
            f"다만 이런 처방은 마음가짐을 다잡는 장치에 가깝지, "
            f"실제 결과를 바꾸는 수단으로 여기지는 마세요.")

    return paras


def render_dict(chart, today=None):
    """JSON 직렬화 가능한 dict로 반환 (웹/API 용)."""
    a = analyze(chart)
    scores = score_all_daeun(a)
    today = today or date.today()
    age = today.year - chart.birth_local.year + 1

    return {
        "birth": {
            "local": chart.birth_local.isoformat(),
            "solar_time": chart.solar_time.isoformat(),
            "place": chart.place.name,
            "longitude": chart.place.longitude,
            "utc_offset": chart.utc_offset,
            "dst": chart.is_dst,
            "gender": "male" if chart.is_male else "female",
            "jasi_school": chart.jasi_school,
        },
        "pillars": {
            k: {"korean": p.name, "hanja": p.hanja,
                "gan": GAN_H[p.gan], "ji": JI_H[p.ji]}
            for k, p in zip(["year", "month", "day", "hour"], chart.pillars)
        },
        "day_master": {
            "hanja": GAN_H[chart.day_gan],
            "element": chart.day_ohaeng,
            "nickname": ILGAN_DESC[chart.day_gan][0],
            "description": ILGAN_DESC[chart.day_gan][1],
        },
        "elements": chart.ohaeng_count(),
        "strength": {
            "label": a.strength.label, "ratio": round(a.strength.ratio, 3),
            "ally": a.strength.ally, "enemy": a.strength.enemy,
        },
        "favorable": a.yongsin,
        "unfavorable": a.gisin,
        "reasoning": a.reasons,
        "daeun": [
            {"age_start": s["age"], "age_end": s["age"] + 9,
             "pillar": s["pillar"].hanja, "score": round(s["score"], 3),
             "percent": s["percent"], "grade": s["grade"],
             "theme": s["theme"], "notes": s["notes"],
             "current": s["age"] <= age < s["age"] + 10}
            for s in scores
        ],
        "warnings": chart.warnings,
        "disclaimer": DISCLAIMER,
    }


EXPORT_SCHEMA_VERSION = 2


def coefficient_fingerprint():
    """현재 계수 전체의 지문. 상수가 하나라도 바뀌면 달라집니다."""
    import hashlib
    parts = []
    for c in COEFFICIENTS:
        v = c.value
        parts.append(f"{c.key}={v!r}")
    parts.append("BANDS=" + repr([tuple(b[:2]) for b in STRENGTH_BANDS_V2]))
    parts.append("GRADE=" + repr([g[0] for g in GRADE_BANDS]))
    blob = "|".join(parts)
    return {
        "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16],
        "n_coefficients": len(COEFFICIENTS),
    }


def _tzdata_version():
    try:
        import tzdata
        return tzdata.IANA_VERSION
    except Exception:
        return "system"


def export_dict(chart, a2=None, today=None, seun_years=10,
                include_seun=True, include_hwaguk=True,
                include_robustness=True):
    """v2 분석 전체를 JSON 직렬화 가능한 dict 로 (#7).

    render_dict() 는 v1 기반이고 재현성 정보가 없어 그대로 두었습니다.
    새 코드는 이 함수를 쓰세요.

    meta 블록이 재현성의 핵심입니다. 나중에 결과가 달라졌을 때
    엔진 버전·tzdata·밴드·계수 지문을 비교하면 원인을 좁힐 수 있습니다.
    """
    a2 = a2 or analyze_v2(chart)
    today = today or date.today()
    age = today.year - chart.birth_local.year + 1
    scores = score_all_daeun_v2(a2)

    out = {
        "meta": {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "engine_version": __version__,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "tzdata_version": _tzdata_version(),
            "python": sys.version.split()[0],
            "bands_used": [list(b[:2]) + [b[2]] for b in STRENGTH_BANDS_V2],
            "grade_bands": [[g[0], g[1]] for g in GRADE_BANDS],
            "coefficients": coefficient_fingerprint(),
            "note": ("이 파일은 재현 가능성을 위해 입력·상수까지 함께 "
                     "남깁니다. 결과가 예전과 다르면 meta 를 먼저 "
                     "비교하세요."),
        },
        "input": {
            "birth_local": chart.birth_local.isoformat(),
            "place": chart.place.name,
            "longitude": chart.place.longitude,
            "gender": "male" if chart.is_male else "female",
            "jasi_school": chart.jasi_school,
            "options": dict(chart.options),
        },
        "derived": {
            "solar_time": chart.solar_time.isoformat(),
            "utc_offset": chart.utc_offset,
            "is_dst": bool(chart.is_dst),
            "age_reckoned": age,
        },
        "pillars": {
            k: {"korean": p.name, "hanja": p.hanja,
                "gan": GAN_H[p.gan], "ji": JI_H[p.ji], "gapja": p.gapja}
            for k, p in zip(["year", "month", "day", "hour"], chart.pillars)
        },
        "day_master": {
            "hanja": GAN_H[chart.day_gan],
            "element": chart.day_ohaeng,
            "nickname": ILGAN_DESC[chart.day_gan][0],
        },
        "elements": chart.ohaeng_count(),
        "strength": {
            "label": a2.strength.label,
            "ratio": a2.strength.ratio,
            "ally": a2.strength.ally,
            "enemy": a2.strength.enemy,
            "confidence": a2.strength.confidence,
            "alt_label": a2.strength.alt_label,
            "mass": dict(a2.strength.mass),
            "caveat": ("라벨은 인구 분포의 백분위입니다. 정의상 항상 약 15%가 "
                       "극신약, 30%가 중화로 나옵니다. 절대 판정이 아닙니다."),
        },
        "favor": dict(a2.favor),
        "yongsin": list(a2.yongsin),
        "gisin": list(a2.gisin),
        "neutral": list(a2.neutral),
        "special": a2.special,
        "field_events": list(a2.field.events),
        "reasoning": list(a2.reasons),
        "daeun": {
            "start_age": chart.daeun_start,
            "forward": chart.daeun_forward,
            "rank_caveat": ("rank/rel 은 이 사람의 대운 9개 안에서의 상대 "
                            "위치입니다. 1위라도 절대 등급은 '어려움'일 수 "
                            "있습니다. grade 가 절대 등급입니다."),
            "periods": [
                {"age_start": s["age"], "age_end": s["age"] + 9,
                 "pillar": s["pillar"].hanja,
                 "score_absolute": s["score"],
                 "raw_unclamped": s["raw_unclamped"],
                 "percent": s["percent"],
                 "grade_absolute": s["grade"],
                 "rank_relative": s.get("rank"),
                 "rel_relative": s.get("rel"),
                 "notes": s["notes"],
                 "current": s["age"] <= age < s["age"] + 10}
                for s in scores
            ],
        },
        "warnings": list(chart.warnings),
        "disclaimer": DISCLAIMER,
    }

    if include_robustness:
        r = strength_robustness(chart)
        out["strength"]["robustness"] = {
            "verdict": r["verdict"],
            "flip_rate": r["flip_rate"],
            "n_tested": r["n_tested"],
            "n_flipped": r["n_flipped"],
            "ratio_span": list(r["ratio_span"]),
            "labels_seen": r["labels_seen"],
            "near_band_edge": r["near_band_edge"],
            "drivers": sorted({k for k, _ in r["drivers"]}),
            "note": ("계수를 ±20% 흔들었을 때 판정이 바뀌는 비율입니다. "
                     "'취약'이면 이 판정은 모델 설정에 크게 의존합니다."),
        }

    if include_hwaguk:
        hits = scan_daeun_hwaguk(a2)
        out["hwaguk_reference"] = {
            "note": ("대운이 원국과 삼합·방합을 완성시키는 구간입니다. "
                     "참고 판정이며, 위 daeun 점수·등급은 원국 용신 기준 "
                     "정본입니다. 두 값을 합산하지 마세요."),
            "periods": [
                {"age_start": age_start,
                 "base_label": h["base_label"], "base_ratio": h["base_ratio"],
                 "transit_label": h["label"], "transit_ratio": h["ratio"],
                 "label_changed": h["label_changed"],
                 "base_yongsin": h["base_yongsin"],
                 "transit_yongsin": h["yongsin"],
                 "yongsin_changed": h["yongsin_changed"],
                 "hwa_new": h["hwa_new"],
                 "shifts": [[e, a, b] for e, a, b in h["shifts"]],
                 "events": h["events"],
                 "summary": h["note"]}
                for age_start, h in sorted(hits.items())
            ],
        }

    if include_seun:
        start = today.year
        rows = score_seun_range(a2, start, seun_years)
        out["seun"] = {
            "note": ("세운은 입춘에 바뀝니다. 세운 점수는 대운 점수와 "
                     "다른 축이므로 합산하지 마세요."),
            "rank_scope": f"{start}~{start + seun_years - 1}년",
            "years": [
                {"year": r["year"],
                 "pillar": r["pillar"].hanja,
                 "daeun": r["daeun"].hanja if r["daeun"] else None,
                 "ipchun_kst": (find_solar_term(r["year"], 0)
                                + timedelta(hours=9)).isoformat(),
                 "score_absolute": r["score"],
                 "percent": r["percent"],
                 "grade_absolute": r["grade"],
                 "rank_relative": r.get("rank"),
                 "notes": r["notes"]}
                for r in rows
            ],
        }

    return out


def export_json(chart, path=None, indent=1, **kw):
    """분석 결과를 JSON 문자열로. path 를 주면 파일로도 씁니다 (#7)."""
    data = export_dict(chart, **kw)
    text = json.dumps(data, ensure_ascii=False, indent=indent, default=str)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return text


def export_text(chart, path=None, a2=None, today=None, width=64,
                seun_years=10, **kw):
    """분석 결과를 사람이 읽는 텍스트로. path 를 주면 파일로도 씁니다 (#7).

    본문(원국·강약·용신·대운)은 v2(지장간·통근·계절·종격 반영) 판정을
    기준으로 합니다. v1 리포트가 필요하면 render_text() 를 직접 쓰세요.
    """
    a2 = a2 or analyze_v2(chart)
    L = [render_text_v2(chart, a2=a2, today=today, width=width)]
    L += ["\n".join(render_hwaguk_section(a2, width=width))]
    L += ["\n".join(render_seun_section(a2, count=seun_years, width=width))]

    meta = export_dict(chart, a2=a2, today=today,
                       include_seun=False, include_hwaguk=False,
                       include_robustness=True)["meta"]
    rb = strength_robustness(chart)
    L += ["", "─" * width,
          "  [ 재현 정보 ]",
          f"    엔진 {meta['engine_version']} / tzdata {meta['tzdata_version']}"
          f" / 계수지문 {meta['coefficients']['sha256']}",
          f"    자시학파 {chart.jasi_school}"
          f" / 경도보정 {'켬' if chart.options.get('apply_longitude') else '끔'}"
          f" / 균시차 {'켬' if chart.options.get('apply_eot') else '끔'}"
          f" / 지역 {chart.place.name}",
          f"    강약 판정 견고성: {rb['verdict']}"
          f" (계수 ±20% 섭동 {rb['n_tested']}회 중 {rb['n_flipped']}회 변동)",
          "─" * width]
    text = "\n".join(x for x in L if x is not None)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return text


ELEMS = "목화토금수"


SAMHYEONG = [
    frozenset((2, 5, 8)),
    frozenset((1, 10, 7)),
]
JAHYEONG = {4, 6, 9, 11}
SANGHYEONG = [frozenset((0, 3))]

YUKHAE = {frozenset((0, 7)), frozenset((1, 6)), frozenset((2, 5)),
          frozenset((3, 4)), frozenset((8, 11)), frozenset((9, 10))}


def _josa(word, kind):
    """받침 유무에 따른 조사 선택. kind: '이가','은는','을를'."""
    ch = word[-1]
    code = ord(ch) - 0xAC00
    has = (0 <= code <= 11171) and (code % 28 != 0)
    return {"이가": ("이", "가"), "은는": ("은", "는"),
            "을를": ("을", "를")}[kind][0 if has else 1]


def wangsang_factor(elem, month_elem):
    """왕상휴수사(旺相休囚死) 계절 계수.

    令神 = 旺, 令이 生하는 것 = 相, 令을 生하는 것 = 休,
    令을 剋하는 것 = 囚, 令이 剋하는 것 = 死.
    """
    if elem == month_elem:
        return WANGSANG_FACTORS["WANG"]
    if SAENG[month_elem] == elem:
        return WANGSANG_FACTORS["SANG"]
    if SAENG[elem] == month_elem:
        return WANGSANG_FACTORS["HYU"]
    if GEUK[elem] == month_elem:
        return WANGSANG_FACTORS["SU"]
    return WANGSANG_FACTORS["SA"]


def jeol_start_of_month(chart):
    """이 사주의 월지를 시작시킨 절(節)의 진태양시 시각."""
    shift = chart.place.longitude / 15.0
    ref = chart.solar_time
    best = None
    for cy in (ref.year - 1, ref.year):
        for i in JEOL_TO_BRANCH:
            t = find_solar_term(cy, i) + timedelta(hours=shift)
            if t <= ref and (best is None or t > best):
                best = t
    return best


def saryeong_gan(ji, days_elapsed):
    """절입 후 days_elapsed 일째에 사령(司令)하는 지장간."""
    acc = 0.0
    for g, d in JIJANGGAN[ji]:
        acc += d
        if days_elapsed < acc:
            return g
    return JIJANGGAN[ji][-1][0]


def root_strength(elem, chart, effect=None):
    """천간 오행이 지지에 통근한 정도 (0.0 ~ 대략 2.0)."""
    effect = effect or {}
    total = 0.0
    for idx, p in enumerate(chart.pillars):
        eff = effect.get(idx, 1.0)
        for g, d in JIJANGGAN[p.ji]:
            if GAN_OHAENG[g] == elem:
                total += (d / 30.0) * eff
    return total


@dataclass
class NatalField:
    effect: dict
    hwa: dict
    events: list
    broken_month: bool = False
    n_natal: int = 4
    transit_labels: tuple = ()


def natal_field(chart):
    """원국 4주만으로 계산한 합·충·형 정산 (정본)."""
    return _compute_field([p.ji for p in chart.pillars], ("년", "월", "일", "시"))


def transit_field(chart, *transit_pillars, labels=None):
    """대운·세운 지지를 5·6번째 기둥처럼 얹어 합·충·형을 다시 정산합니다 (#3).

    삼합·방합이 '완성'되는지는 참여 글자가 전부 모여야 판정됩니다.
    원국 안에 두 글자만 있으면 반합에 그치지만, 대운이 나머지 한 글자를
    들고 들어오면 그때 비로소 化局이 성립합니다. 원국만 보는
    natal_field() 로는 이 사건을 볼 수 없습니다.

    ※ 이 결과는 '참고 판정'입니다. 정본은 어디까지나 원국입니다.
       이유는 measure_strength_with_transit() 의 주석을 보세요.
    """
    labels = labels or tuple(
        f"운{i + 1}" for i in range(len(transit_pillars)))
    jis = [p.ji for p in chart.pillars] + [p.ji for p in transit_pillars]
    return _compute_field(jis, ("년", "월", "일", "시") + tuple(labels),
                          n_natal=4, transit_labels=tuple(labels))


def _compute_field(jis, labels, n_natal=4, transit_labels=()):
    """
    지지 목록 안에서 벌어지는 합·충·형을 먼저 정산해서
    각 지지가 실제로 몇 퍼센트나 제 역할을 하는지 계산합니다.

    v1 은 이 단계가 통째로 없었습니다. 월지가 이미 충으로 깨져 있어도
    가중치 3.0 을 그대로 받아서 강약 판정이 왜곡됐습니다.

    jis 의 앞 n_natal 개는 원국, 나머지는 운(대운·세운)입니다.
    운 기둥은 합·충에 '참여'하지만 자기 질량을 따로 더하지는 않습니다
    (measure_strength_v2 가 chart.pillars 만 순회하므로). 운이 만든
    화국의 힘은 hwa 를 통해서만 들어옵니다.
    """
    n = len(jis)
    effect = {i: 1.0 for i in range(n)}
    hwa = {e: 0.0 for e in ELEMS}
    events = []
    broken_month = False

    def is_transit(i):
        return i >= n_natal

    def tag(i):
        return f"{labels[i]}지" if not is_transit(i) else labels[i]

    def show(idxs):
        """참여 글자를 중복 없이 표시. 같은 글자가 두 자리에 있어도 한 번만."""
        seen, out = set(), []
        for i in idxs:
            if jis[i] not in seen:
                seen.add(jis[i])
                out.append(JI_H[jis[i]])
        return "·".join(out)


    absorbed = set()


    for combo, elem in SAMHAP.items():
        idxs = [i for i, j in enumerate(jis) if j in combo]
        found = {jis[i] for i in idxs}
        if found == combo:
            for i in idxs:
                effect[i] = max(effect[i], 1.25)
            hwa[elem] += HWA_SAMHAP
            for a in combo:
                for b in combo:
                    if a != b:
                        absorbed.add(frozenset((a, b)))
            via = [i for i in idxs if is_transit(i)]
            if via:
                events.append(
                    f"★ {'·'.join(dict.fromkeys(labels[i] for i in via))}"
                    f"(으)로 삼합 완성 — {show(idxs)} → {elem}국. "
                    f"이 기간에는 {elem} 기운이 판을 지배합니다.")
            else:
                events.append(
                    f"원국 삼합 완성 — {show(idxs)} → {elem}국. "
                    f"이 사주는 {elem} 기운이 판을 지배합니다.")


    for combo, elem in BANGHAP.items():
        idxs = [i for i, j in enumerate(jis) if j in combo]
        if {jis[i] for i in idxs} == combo:
            for i in idxs:
                effect[i] = max(effect[i], 1.2)
            hwa[elem] += HWA_BANGHAP
            for a in combo:
                for b in combo:
                    if a != b:
                        absorbed.add(frozenset((a, b)))
            via = [i for i in idxs if is_transit(i)]
            events.append(
                (f"★ {'·'.join(dict.fromkeys(labels[i] for i in via))}"
                 f"(으)로 방합 완성 — " if via else "원국 방합 완성 — ")
                + f"{show(idxs)} → {elem} 계절국")


    counted_banhap = set()
    for i in range(n):
        for k in range(i + 1, n):
            key = frozenset((jis[i], jis[k]))
            if len(key) != 2 or key not in BANHAP or key in absorbed:
                continue

            if key in counted_banhap:
                continue
            counted_banhap.add(key)
            elem = BANHAP[key]
            hwa[elem] += HWA_BANHAP
            mark = "★ " if (is_transit(i) or is_transit(k)) else "원국 "
            events.append(
                f"{mark}반합 {JI_H[jis[i]]}+{JI_H[jis[k]]} → {elem} 반국")


    for i in range(n):
        for k in range(i + 1, n):
            if is_chung(jis[i], jis[k]):


                near = (k - i == 1) and not is_transit(k)
                dmg = CHUNG_NEAR if near else CHUNG_FAR
                effect[i] *= dmg
                effect[k] *= dmg
                if 1 in (i, k):
                    broken_month = True
                events.append(
                    f"{'★ ' if (is_transit(i) or is_transit(k)) else '원국 '}"
                    f"충 {tag(i)} {JI_H[jis[i]]} ↔ {tag(k)} {JI_H[jis[k]]}"
                    f"{' (인접)' if near else ''} → 양쪽 뿌리 손상")


    for combo in SAMHYEONG:
        idxs = [i for i, j in enumerate(jis) if j in combo]
        if {jis[i] for i in idxs} == combo:
            for i in idxs:
                effect[i] *= 0.8
            mark = "★ " if any(is_transit(i) for i in idxs) else "원국 "
            events.append(
                f"{mark}삼형 {'·'.join(JI_H[jis[i]] for i in idxs)} → 불안정 요소")


    for i in range(n):
        for k in range(i + 1, n):
            key = frozenset((jis[i], jis[k]))
            if len(key) == 2 and key in YUKHAP:
                effect[i] *= 0.92
                effect[k] *= 0.92
                mark = "★ " if (is_transit(i) or is_transit(k)) else "원국 "
                events.append(
                    f"{mark}육합 {JI_H[jis[i]]}+{JI_H[jis[k]]} → 서로 묶임")

    return NatalField(effect=effect, hwa=hwa, events=events,
                      broken_month=broken_month, n_natal=n_natal,
                      transit_labels=transit_labels)


JI_POS_W = {0: 1.0, 1: 3.0, 2: 1.5, 3: 1.2}
GAN_POS_W = {0: 0.8, 1: 1.2, 2: 0.0, 3: 1.0}

SARYEONG_BONUS = 1.6
ROOT_NONE = 0.40
ROOT_WEAK = 0.70
BAND_EDGE = 0.025


COEFF_TIER = {
    "고전": "고전 문헌에 규칙과 수치가 함께 명시됨",
    "통설": "방향·순서는 고전 근거가 있으나 구체적 수치는 관행",
    "튜닝": "수치에 문헌 근거 없음. 분포를 맞추기 위해 정한 값",
    "구조": "모델 구조에서 따라 나오는 값. 자유도가 아님",
}

_TIER_ORDER = ["고전", "통설", "튜닝", "구조"]


class Coefficient:
    """조정 가능한 계수 하나에 대한 메타데이터와 접근자."""

    __slots__ = ("key", "label", "tier", "note", "_get", "_set", "tunable")

    def __init__(self, key, label, tier, note, get, set_, tunable=True):
        self.key, self.label, self.tier, self.note = key, label, tier, note
        self._get, self._set, self.tunable = get, set_, tunable

    @property
    def value(self):
        return self._get()

    def set(self, v):
        self._set(v)

    def __repr__(self):
        return f"<Coefficient {self.key}={self.value!r} [{self.tier}]>"


def _mk_global_accessor(name):
    def get():
        return globals()[name]

    def set_(v):
        globals()[name] = v
    return get, set_


def _build_coefficient_registry():
    reg = []

    def add(key, label, tier, note, get, set_, tunable=True):
        reg.append(Coefficient(key, label, tier, note, get, set_, tunable))


    for idx, pos in enumerate(("년", "월", "일", "시")):
        add(f"JI_POS_W[{pos}]", f"{pos}지 위치 가중치",
            "통설" if idx == 1 else "튜닝",
            ("월령(月令)이 강약의 으뜸이라는 것은 자평명리 이래 통설입니다. "
             "다만 '3.0배'라는 구체적 배수는 어느 고전에도 없습니다. "
             "민감도 측정에서 판정 변동률이 가장 높은 계수입니다."
             if idx == 1 else
             f"{pos}지의 상대적 비중. 월지 대비 순서(월>일>시>년)만 "
             f"통설이고 수치는 튜닝값입니다."),
            (lambda i=idx: JI_POS_W[i]),
            (lambda v, i=idx: JI_POS_W.__setitem__(i, v)))

    for idx, pos in enumerate(("년", "월", "일", "시")):
        if idx == 2:
            add("GAN_POS_W[일]", "일간 위치 가중치", "구조",
                "일간은 '나 자신'이라 질량 합산에서 제외됩니다(0.0). "
                "튜닝 대상이 아닙니다.",
                (lambda: GAN_POS_W[2]), (lambda v: None), tunable=False)
            continue
        add(f"GAN_POS_W[{pos}]", f"{pos}간 위치 가중치", "튜닝",
            "천간의 위치별 비중. 수치에 문헌 근거 없음.",
            (lambda i=idx: GAN_POS_W[i]),
            (lambda v, i=idx: GAN_POS_W.__setitem__(i, v)))


    add("SARYEONG_BONUS", "월령 사령 지장간 배수", "통설",
        "월지에서 당령(當令)한 지장간을 중히 본다는 것은 통설입니다. "
        "1.6배라는 수치는 튜닝값이며, 민감도가 두 번째로 높습니다.",
        *_mk_global_accessor("SARYEONG_BONUS"))
    add("ROOT_NONE", "무근 천간 감쇄", "튜닝",
        "지지에 뿌리가 없는 천간을 약하게 본다는 방향만 통설입니다. "
        "0.40 이라는 수치는 근거 없음. 다만 민감도가 1% 미만이라 "
        "값을 다투는 실익이 거의 없습니다.",
        *_mk_global_accessor("ROOT_NONE"))
    add("ROOT_WEAK", "약근 천간 감쇄", "튜닝",
        "여기(餘氣)에만 뿌리를 둔 천간의 감쇄. 수치는 근거 없음.",
        *_mk_global_accessor("ROOT_WEAK"))


    add("HWA_SAMHAP", "삼합 화국 가산", "튜닝",
        "삼합이 성립하면 해당 오행이 강해진다는 것은 고전 근거가 "
        "있으나, '+2.2' 라는 절대 가산량은 순수 튜닝값입니다. "
        "질량이 아니라 상수를 더하므로 원국 규모에 따라 효과가 "
        "달라진다는 구조적 약점이 있습니다. "
        "다만 원국 4주 안에서 삼합이 완성되는 경우는 약 5% 에 "
        "불과해, 강약 판정에 대한 실측 영향은 0.2% 로 거의 없습니다. "
        "이 계수가 실제로 중요해지는 것은 대운·세운이 들어와 삼합을 "
        "완성시킬 때입니다.",
        *_mk_global_accessor("HWA_SAMHAP"))
    add("HWA_BANGHAP", "방합 화국 가산", "튜닝",
        "방합은 삼합보다 약하게 본다는 순서만 통설. 수치는 튜닝값. "
        "원국 발생률 약 5%, 판정 영향 0.2%.",
        *_mk_global_accessor("HWA_BANGHAP"))
    add("HWA_BANHAP", "반합 화국 가산", "튜닝",
        "반합은 삼합의 일부이므로 더 약하게 봅니다. 수치는 튜닝값. "
        "원국에서 거의 항상(평균 1회 이상) 성립하므로, 세 화국 계수 "
        "중 판정에 실제로 영향을 주는 것은 이것뿐입니다(2.4%). "
        "'삼합 2.2 / 방합 1.8 / 반합 0.6' 의 크기 순서가 곧 영향력 "
        "순서일 것이라 짐작하기 쉽지만, 실측은 정반대입니다.",
        *_mk_global_accessor("HWA_BANHAP"))


    add("CHUNG_NEAR", "인접 충 감쇄", "튜닝",
        "충(沖)은 인접할수록 강하게 작용한다는 것이 통설. "
        "0.62 라는 감쇄율은 튜닝값입니다.",
        *_mk_global_accessor("CHUNG_NEAR"))
    add("CHUNG_FAR", "원격 충 감쇄", "튜닝",
        "떨어진 충의 감쇄율. 튜닝값.",
        *_mk_global_accessor("CHUNG_FAR"))


    for name, key in (("旺", "WANG"), ("相", "SANG"), ("休", "HYU"),
                      ("囚", "SU"), ("死", "SA")):
        add(f"WANGSANG_{key}", f"왕상휴수사 — {name}", "통설",
            "왕상휴수사의 '순서'는 고전이 명시합니다(旺>相>休>囚>死). "
            "다만 각 단계의 배수는 고전에 수치로 나오지 않습니다. "
            "실측상 이 다섯 계수가 민감도 상위 7개 중 5개를 차지하며, "
            "특히 旺(1.30)은 단일 계수로는 영향력 1위(최대 13.9%)입니다. "
            "월지 가중치보다 큽니다 — 계절 계수는 모든 오행의 질량에 "
            "곱해지는 반면 위치 가중치는 해당 자리에만 걸리기 "
            "때문입니다. 근거를 붙여야 할 우선순위가 여기 있습니다."
            if key == "WANG" else
            "왕상휴수사의 '순서'는 고전이 명시합니다(旺>相>休>囚>死). "
            "다만 각 단계의 배수는 고전에 수치로 나오지 않습니다. "
            "계절 계수는 모든 오행 질량에 곱해지므로 위치 가중치보다 "
            "영향이 큽니다(실측 4~7.5%).",
            (lambda k=key: WANGSANG_FACTORS[k]),
            (lambda v, k=key: WANGSANG_FACTORS.__setitem__(k, v)))


    add("GAN_W", "대운 천간 비중", "튜닝",
        "대운 점수에서 천간:지지 = 0.35:0.65. 지지를 무겁게 본다는 "
        "방향만 통설이고 비율은 튜닝값입니다.",
        *_mk_global_accessor("GAN_W"))
    add("JI_W", "대운 지지 비중", "구조",
        "GAN_W 와 합이 1.0 이 되도록 정해집니다. 독립 자유도가 아닙니다.",
        *_mk_global_accessor("JI_W"), tunable=False)
    add("BAND_EDGE", "경계 판정 폭", "구조",
        "판정이 밴드 경계에서 이 폭 이내면 '경계'로 표시합니다. "
        "정밀도가 아니라 표시 정책입니다.",
        *_mk_global_accessor("BAND_EDGE"), tunable=False)

    return reg


HWA_SAMHAP = 2.2
HWA_BANGHAP = 1.8
HWA_BANHAP = 0.6
CHUNG_NEAR = 0.62
CHUNG_FAR = 0.78
WANGSANG_FACTORS = {"WANG": 1.30, "SANG": 1.15, "HYU": 0.90,
                    "SU": 0.75, "SA": 0.60}

COEFFICIENTS = _build_coefficient_registry()
COEFF_BY_KEY = {c.key: c for c in COEFFICIENTS}
TUNABLE_COEFFICIENTS = [c for c in COEFFICIENTS if c.tunable]


@contextlib.contextmanager
def perturbed(**changes):
    """계수를 일시적으로 바꿉니다. 반드시 원복됩니다.

        with perturbed(SARYEONG_BONUS=1.28):
            ...
    """
    saved = {}
    try:
        for key, value in changes.items():
            c = COEFF_BY_KEY[key]
            saved[key] = c.value
            c.set(value)
        yield
    finally:
        for key, value in saved.items():
            COEFF_BY_KEY[key].set(value)


def strength_robustness(chart, rel=0.20, band_edge=None):
    """이 사주 하나의 강약 판정이 계수에 얼마나 의존하는지 측정합니다.

    조정 가능한 계수를 하나씩 ±rel 만큼 흔들어, 판정 라벨이 바뀌는지
    확인합니다. 사용자에게 "이 판정은 확실합니다" / "이 판정은 계수를
    조금만 흔들어도 바뀝니다" 를 정직하게 보여주기 위한 것입니다.

    반환:
        {
          "label": 기준 판정,
          "ratio": 기준 수치,
          "n_tested": 흔든 횟수,
          "n_flipped": 판정이 바뀐 횟수,
          "flip_rate": 비율,
          "ratio_span": (최소, 최대),      # 흔들었을 때 수치가 움직인 범위
          "labels_seen": 나타난 모든 라벨,
          "drivers": [(계수키, 바뀐라벨), ...],   # 판정을 뒤집은 계수
          "verdict": "확고" / "보통" / "취약",
        }
    """
    base = measure_strength_v2(chart)
    lo = hi = base.ratio
    flipped, seen, drivers = 0, {base.label}, []
    tested = 0

    for c in TUNABLE_COEFFICIENTS:
        v0 = c.value
        if not isinstance(v0, (int, float)) or v0 == 0:
            continue
        for factor in (1.0 - rel, 1.0 + rel):
            with perturbed(**{c.key: v0 * factor}):
                st = measure_strength_v2(chart)
            tested += 1
            lo, hi = min(lo, st.ratio), max(hi, st.ratio)
            seen.add(st.label)
            if st.label != base.label:
                flipped += 1
                drivers.append((c.key, st.label))

    rate = flipped / tested if tested else 0.0
    edge = BAND_EDGE if band_edge is None else band_edge
    near_edge = any(abs(base.ratio - b[0]) < edge or abs(base.ratio - b[1]) < edge
                    for b in [(x[0], x[1]) for x in STRENGTH_BANDS_V2])

    if rate == 0 and not near_edge:
        verdict = "확고"
    elif rate < 0.15:
        verdict = "보통"
    else:
        verdict = "취약"

    return {
        "label": base.label,
        "ratio": base.ratio,
        "n_tested": tested,
        "n_flipped": flipped,
        "flip_rate": rate,
        "ratio_span": (lo, hi),
        "labels_seen": sorted(seen),
        "drivers": drivers,
        "near_band_edge": near_edge,
        "verdict": verdict,
    }


def sensitivity_report(samples=None, rel=0.20, start=1970, end=2000,
                       step_days=97, hours=(1, 7, 13, 19), place="서울"):
    """계수별 판정 변동률을 표본 전체에 대해 측정합니다.

    "왜 이 숫자인가" 에 주석으로 답할 수 없는 대신, "이 숫자가 결과를
    얼마나 좌우하는가" 를 수치로 답합니다. 변동률이 낮은 계수는 값을
    다툴 실익이 없고, 높은 계수에만 근거를 붙이면 됩니다.

    반환: [(계수, 변동률_하한, 변동률_상한, 최대변동률), ...] 내림차순
    """
    if samples is None:
        samples = []
        d = date(start, 1, 1)
        while d < date(end, 1, 1):
            for h in hours:
                try:
                    samples.append(build_chart(d.year, d.month, d.day, h, 0,
                                               place=place))
                except Exception:
                    pass
            d += timedelta(days=step_days)

    base = [measure_strength_v2(c).label for c in samples]
    n = len(base) or 1
    rows = []
    for c in TUNABLE_COEFFICIENTS:
        v0 = c.value
        if not isinstance(v0, (int, float)) or v0 == 0:
            continue
        rates = []
        for factor in (1.0 - rel, 1.0 + rel):
            with perturbed(**{c.key: v0 * factor}):
                new = [measure_strength_v2(ch).label for ch in samples]
            rates.append(sum(1 for a, b in zip(base, new) if a != b) / n)
        rows.append((c, min(rates), max(rates), max(rates)))

    rows.sort(key=lambda r: -r[3])
    return rows


def format_sensitivity_report(rows=None, **kw):
    """sensitivity_report() 결과를 사람이 읽는 표로."""
    if rows is None:
        rows = sensitivity_report(**kw)
    out = ["계수 민감도 — ±20% 섭동 시 강약 판정 변동률",
           "=" * 68,
           f"{'계수':<24}{'값':>8}{'등급':>6}{'변동률':>12}",
           "-" * 68]
    for c, lo, hi, _ in rows:
        val = c.value
        vs = f"{val:.3f}" if isinstance(val, float) else str(val)
        out.append(f"{c.key:<24}{vs:>8}{c.tier:>6}"
                   f"{lo * 100:>6.1f}~{hi * 100:>4.1f}%")
    out += ["-" * 68,
            "변동률이 5% 를 넘는 계수에만 고전 근거를 붙이면 됩니다.",
            "1% 미만인 계수는 값이 무엇이든 결과가 거의 같습니다."]
    return "\n".join(out)


STRENGTH_BANDS_V2 = [
    (0.000, 0.136, "극신약", "일간이 매우 약합니다 (하위 15%)"),
    (0.136, 0.240, "신약",   "일간이 약한 편입니다 (하위 15~35%)"),
    (0.240, 0.515, "중화",   "일간이 균형에 가깝습니다 (중간 30%)"),
    (0.515, 0.704, "신강",   "일간이 강한 편입니다 (상위 15~35%)"),
    (0.704, 1.001, "극신강", "일간이 매우 강합니다 (상위 15%)"),
]


def calibrate_bands(start_year=1940, end_year=2010, step_days=53,
                    hours=tuple(range(0, 24, 2)), quantiles=(0.15, 0.35, 0.65, 0.85)):
    """실제 사주 분포를 샘플링해 밴드 경계를 다시 뽑습니다.

    가중치나 계수를 손본 뒤에는 반드시 이 함수를 다시 돌려서
    STRENGTH_BANDS_V2 를 갱신하세요. 그러지 않으면 밴드가
    분포와 어긋나 판정이 한쪽으로 쏠립니다.
    """
    from datetime import date, timedelta
    vals, d = [], date(start_year, 1, 1)
    while d < date(end_year, 1, 1):
        for h in hours:
            try:
                vals.append(measure_strength_v2(
                    build_chart(d.year, d.month, d.day, h, 0,
                                place="서울")).ratio)
            except Exception:
                pass
        d += timedelta(days=step_days)
    vals.sort()
    n = len(vals)
    return [vals[int(q * n)] for q in quantiles], n


@dataclass
class StrengthV2:
    ratio: float
    label: str
    description: str
    ally: float
    enemy: float
    mass: dict
    details: list
    confidence: str
    alt_label: str = ""
    saryeong: str = ""
    day_root: float = 0.0
    notes: list = field(default_factory=list)


def measure_strength_v2(chart, nf=None):
    nf = nf or natal_field(chart)
    dg = chart.day_gan
    d_elem = GAN_OHAENG[dg]
    m_elem = JI_OHAENG[chart.month.ji]
    mass = {e: 0.0 for e in ELEMS}
    details = []
    notes = []


    try:
        jeol = jeol_start_of_month(chart)
        elapsed = (chart.solar_time - jeol).total_seconds() / 86400.0
    except Exception:
        elapsed = 15.0
    sr = saryeong_gan(chart.month.ji, elapsed)
    notes.append(
        f"절입 후 {elapsed:.1f}일째 출생 → 월지 {JI_H[chart.month.ji]} 중 "
        f"{GAN_H[sr]}({GAN_OHAENG[sr]})이 사령")


    for idx, p in enumerate(chart.pillars):
        base = JI_POS_W[idx] * nf.effect[idx]
        for g, d in JIJANGGAN[p.ji]:
            share = d / 30.0
            elem = GAN_OHAENG[g]
            w = base * share * wangsang_factor(elem, m_elem)
            if idx == 1 and g == sr:
                w *= SARYEONG_BONUS
            mass[elem] += w
            details.append((f"{'년월일시'[idx]}지 {JI_H[p.ji]}장간 {GAN_H[g]}",
                            elem, sipseong_by_ohaeng(dg, elem), w))


    for idx, p in enumerate(chart.pillars):
        if idx == 2:
            continue
        elem = GAN_OHAENG[p.gan]
        r = root_strength(elem, chart, nf.effect)
        if r >= 0.5:
            rf = 1.0
        elif r > 0.0:
            rf = ROOT_WEAK
        else:
            rf = ROOT_NONE
        w = GAN_POS_W[idx] * rf * wangsang_factor(elem, m_elem)
        mass[elem] += w
        details.append((f"{'년월일시'[idx]}간 {GAN_H[p.gan]}"
                        f"{'(무근)' if rf == ROOT_NONE else ''}",
                        elem, sipseong_by_ohaeng(dg, elem), w))


    for e, extra in nf.hwa.items():
        if extra:
            mass[e] += extra * wangsang_factor(e, m_elem)


    ally = enemy = 0.0
    for e, v in mass.items():
        if sipseong_by_ohaeng(dg, e) in ("비겁", "인성"):
            ally += v
        else:
            enemy += v

    total = ally + enemy
    ratio = ally / total if total else 0.5

    label = desc = ""
    for lo, hi, lb, ds in STRENGTH_BANDS_V2:
        if lo <= ratio < hi:
            label, desc = lb, ds
            break


    conf, alt = "확실", ""
    for lo, hi, lb, _ in STRENGTH_BANDS_V2:
        for edge in (lo, hi):
            if 0.0 < edge < 1.0 and abs(ratio - edge) < BAND_EDGE:
                conf = "경계"
                for lo2, hi2, lb2, _2 in STRENGTH_BANDS_V2:
                    if lb2 != label and (lo2 <= edge <= hi2):
                        alt = lb2
    day_root = root_strength(d_elem, chart, nf.effect)

    return StrengthV2(
        ratio=ratio, label=label, description=desc, ally=ally, enemy=enemy,
        mass=mass, details=details, confidence=conf, alt_label=alt,
        saryeong=GAN_H[sr], day_root=day_root, notes=notes)


def detect_jonggyeok(chart, st, nf):
    """
    일간이 뿌리도 인성도 없이 고립되면 억부의 '약하니 도와라'가
    뒤집힙니다. 대세를 따라가는 從格으로 보는 것이 통설입니다.

    v1 은 이 분기가 없어서, 종격 사주를 극신약으로 판정하고
    정반대의 용신을 내놓습니다. 다른 곳 결과와 통째로 어긋나는
    가장 흔한 원인입니다.
    """
    dg = chart.day_gan
    d_elem = GAN_OHAENG[dg]
    ins = SAENG_BY[d_elem]


    if st.ratio >= 0.10:
        return None
    if st.day_root >= 0.20:
        return None
    if sipseong_by_ohaeng(dg, JI_OHAENG[chart.month.ji]) in ("비겁", "인성"):
        return None
    if st.mass[ins] >= st.ally * 0.55 and st.mass[ins] > 1.2:
        return None


    cand = {e: st.mass[e] for e in ELEMS
            if sipseong_by_ohaeng(dg, e) not in ("비겁", "인성")}
    winner = max(cand, key=lambda e: cand[e])
    grp = sipseong_by_ohaeng(dg, winner)
    names = {"재성": "종재격(從財格)", "관성": "종살격(從殺格)",
             "식상": "종아격(從兒格)"}
    return {
        "name": names.get(grp, "종세격"),
        "elem": winner,
        "group": grp,
        "reason": (f"일간 {GAN_H[dg]}가 지지에 사실상 뿌리가 없고"
                   f"(통근 {st.day_root:.2f}) 아군 비율 {st.ratio:.0%}로 고립 → "
                   f"{winner}({grp}) 세력에 종(從)하는 것으로 봅니다."),
    }


"""
억부용신은 명리학의 여러 유파 중 하나일 뿐입니다. 격국론(格局論)은
"일간이 강한가 약한가"가 아니라 "월지가 무슨 십성을 뽑아내는가"로
사주의 틀(格)을 먼저 정하고, 그 격을 보호·완성하는 오행(상신·相神)을
용신으로 봅니다. 두 이론은 접근 자체가 달라서 결론이 갈릴 때가 있고,
그 자체가 사용자에게 유용한 정보입니다 — "이 부분은 유파에 따라
결론이 갈리니 보수적으로 해석하라"는 신호이기 때문입니다.

여기서는 8격(정격) 판정만 다룹니다. 판단 기준은 월지 정기(正氣,
지장간의 마지막 글자, 그 달의 기운을 가장 오래 대표하는 천간)의
십성입니다. 실제 격국론은 "정기가 천간에 투출했는가", "다른 지지의
십성이 더 강한가" 등을 함께 따져 격을 바꾸는 변격(變格) 판단까지
들어가지만, 여기서는 가장 기본적인 정기 기준 판정만 제공합니다.
정밀 감정에는 변격 여부를 별도로 검토해야 합니다.
"""


_GYEOK_NAME_OVERRIDE = {"비견": "건록격", "겁재": "양인격"}


GYEOKGUK_PRINCIPLE = {
    "비겁": {"favored": ["관성", "식상"], "disfavored": ["인성", "비겁"],
            "note": "건록·양인격은 힘이 넘치므로 관성으로 억제하거나 "
                    "식상으로 힘을 흘려보내는 쪽을 반깁니다."},
    "식상": {"favored": ["재성"], "disfavored": ["인성"],
            "note": "식상격은 식상이 재성으로 이어져야 결실을 맺는다고 보고, "
                    "인성이 식상을 극하면 격이 깨진다고 봅니다."},
    "재성": {"favored": ["관성", "식상"], "disfavored": ["비겁"],
            "note": "재성격은 재를 지켜줄 관성이나 재를 만들어주는 식상을 "
                    "반기고, 비겁이 재를 겁탈하는 것을 꺼립니다."},
    "관성": {"favored": ["인성"], "disfavored": ["식상"],
            "note": "관성격(특히 정관격)은 인성으로 관의 기운을 이어받는 것을 "
                    "반기고, 식상이 관을 극하는 것(상관견관)을 꺼립니다."},
    "인성": {"favored": ["관성"], "disfavored": ["재성"],
            "note": "인성격은 관성이 인성을 생해주는 것을 반기고, "
                    "재성이 인성을 극하는 것(재극인)을 꺼립니다."},
}


def _group_to_elem(dg):
    """일간 기준 십성 그룹 -> 오행 (그룹과 오행은 1:1 대응)."""
    d = GAN_OHAENG[dg]
    return {
        "비겁": d, "식상": SAENG[d], "재성": GEUK[d],
        "관성": GEUK_BY[d], "인성": SAENG_BY[d],
    }


def detect_gyeokguk(chart, favor):
    """
    월지 정기 기준으로 격을 정하고, 그 격이 반기는/꺼리는 오행을
    이미 계산된 억부 용신(favor)과 비교합니다.

    반환값은 판정 결과이자 "억부와 격국이 얼마나 같은 곳을 가리키는가"에
    대한 근거이며, 대운 채점에 직접 반영하지는 않습니다. 대운 점수까지
    두 이론으로 이중 계산하면 사용자가 결론 하나를 고르기 더 어려워지므로,
    여기서는 "참고 의견"으로만 제공합니다.
    """
    dg = chart.day_gan
    month_ji = chart.month.ji
    jeonggi_gan = JIJANGGAN[month_ji][-1][0]
    specific = sipseong(dg, jeonggi_gan)
    group = SIPSEONG_GROUP[specific]
    gyeok_name = _GYEOK_NAME_OVERRIDE.get(specific, specific + "격")

    principle = GYEOKGUK_PRINCIPLE[group]
    g2e = _group_to_elem(dg)
    favored_elems = sorted({g2e[g] for g in principle["favored"]})
    disfavored_elems = sorted({g2e[g] for g in principle["disfavored"]})

    eokbu_yong = {k for k, v in favor.items() if v >= 0.3}
    eokbu_gi = {k for k, v in favor.items() if v <= -0.3}

    agree = eokbu_yong & set(favored_elems)
    clash = (eokbu_yong & set(disfavored_elems)) | (eokbu_gi & set(favored_elems))

    if agree and not clash:
        verdict = "일치"
        verdict_text = (f"억부 용신({'·'.join(sorted(eokbu_yong)) or '뚜렷하지 않음'})과 "
                        f"격국이 반기는 오행({'·'.join(favored_elems)})이 겹칩니다. "
                        f"두 유파가 같은 결론을 내는 구간이라 신뢰도가 높은 편입니다.")
    elif clash and not agree:
        verdict = "상충"
        verdict_text = (f"억부 용신({'·'.join(sorted(eokbu_yong)) or '뚜렷하지 않음'})이 "
                        f"오히려 격국에서 꺼리는 오행({'·'.join(disfavored_elems)})과 "
                        f"겹칩니다. 억부와 격국이 반대 처방을 내는 구간이므로, "
                        f"이 사주는 유파에 따라 조언이 달라질 수 있어 보수적으로 "
                        f"해석하는 것이 좋습니다.")
    elif agree and clash:
        verdict = "부분일치"
        verdict_text = "억부와 격국이 부분적으로만 같은 방향을 가리킵니다."
    else:
        verdict = "무관"
        verdict_text = (f"이번 용신은 격국이 특별히 반기거나 꺼리는 오행과 "
                        f"직접 겹치지 않습니다. 격국 관점에서는 중립적인 구간입니다.")

    return {
        "gyeok_name": gyeok_name,
        "specific": specific,
        "group": group,
        "favored_elems": favored_elems,
        "disfavored_elems": disfavored_elems,
        "verdict": verdict,
        "note": (f"월지 {JI_H[month_ji]}의 정기는 {GAN_H[jeonggi_gan]}"
                f"({specific})이므로 격국론으로는 '{gyeok_name}'입니다. "
                f"{principle['note']} {verdict_text}"),
    }


JOHU_TABLE = {

    (0, 2): ("화", "수"), (0, 3): ("금", "화"), (0, 4): ("금", "화"),
    (0, 5): ("수", "화"), (0, 6): ("수", "화"), (0, 7): ("수", "화"),
    (0, 8): ("금", "화"), (0, 9): ("금", "화"), (0, 10): ("금", "수"),
    (0, 11): ("금", "화"), (0, 0): ("화", "금"), (0, 1): ("화", "금"),

    (1, 2): ("화", "수"), (1, 3): ("화", "수"), (1, 4): ("수", "화"),
    (1, 5): ("수", "금"), (1, 6): ("수", "화"), (1, 7): ("수", "화"),
    (1, 8): ("화", "수"), (1, 9): ("수", "화"), (1, 10): ("수", "금"),
    (1, 11): ("화", "토"), (1, 0): ("화", "화"), (1, 1): ("화", "화"),

    (2, 2): ("수", "금"), (2, 3): ("수", "목"), (2, 4): ("수", "목"),
    (2, 5): ("수", "금"), (2, 6): ("수", "금"), (2, 7): ("수", "금"),
    (2, 8): ("수", "토"), (2, 9): ("수", "수"), (2, 10): ("목", "수"),
    (2, 11): ("목", "토"), (2, 0): ("수", "토"), (2, 1): ("수", "목"),

    (3, 2): ("목", "금"), (3, 3): ("금", "목"), (3, 4): ("목", "금"),
    (3, 5): ("목", "금"), (3, 6): ("수", "금"), (3, 7): ("목", "수"),
    (3, 8): ("목", "금"), (3, 9): ("목", "금"), (3, 10): ("목", "금"),
    (3, 11): ("목", "금"), (3, 0): ("목", "금"), (3, 1): ("목", "금"),

    (4, 2): ("화", "목"), (4, 3): ("화", "목"), (4, 4): ("목", "화"),
    (4, 5): ("목", "화"), (4, 6): ("수", "목"), (4, 7): ("수", "목"),
    (4, 8): ("화", "목"), (4, 9): ("화", "수"), (4, 10): ("목", "화"),
    (4, 11): ("목", "화"), (4, 0): ("화", "목"), (4, 1): ("화", "목"),

    (5, 2): ("화", "수"), (5, 3): ("목", "화"), (5, 4): ("화", "목"),
    (5, 5): ("수", "화"), (5, 6): ("수", "화"), (5, 7): ("수", "화"),
    (5, 8): ("화", "수"), (5, 9): ("화", "수"), (5, 10): ("목", "화"),
    (5, 11): ("화", "목"), (5, 0): ("화", "목"), (5, 1): ("화", "목"),

    (6, 2): ("토", "목"), (6, 3): ("화", "목"), (6, 4): ("목", "화"),
    (6, 5): ("수", "토"), (6, 6): ("수", "수"), (6, 7): ("화", "목"),
    (6, 8): ("화", "목"), (6, 9): ("화", "목"), (6, 10): ("목", "수"),
    (6, 11): ("화", "화"), (6, 0): ("화", "목"), (6, 1): ("화", "목"),

    (7, 2): ("토", "수"), (7, 3): ("수", "목"), (7, 4): ("수", "목"),
    (7, 5): ("수", "목"), (7, 6): ("수", "토"), (7, 7): ("수", "금"),
    (7, 8): ("수", "목"), (7, 9): ("수", "목"), (7, 10): ("수", "화"),
    (7, 11): ("수", "화"), (7, 0): ("화", "토"), (7, 1): ("화", "수"),

    (8, 2): ("금", "화"), (8, 3): ("토", "금"), (8, 4): ("목", "금"),
    (8, 5): ("수", "금"), (8, 6): ("수", "금"), (8, 7): ("금", "목"),
    (8, 8): ("토", "화"), (8, 9): ("목", "금"), (8, 10): ("목", "화"),
    (8, 11): ("토", "화"), (8, 0): ("토", "화"), (8, 1): ("화", "목"),

    (9, 2): ("금", "화"), (9, 3): ("금", "금"), (9, 4): ("화", "금"),
    (9, 5): ("금", "금"), (9, 6): ("금", "수"), (9, 7): ("금", "수"),
    (9, 8): ("화", "목"), (9, 9): ("금", "화"), (9, 10): ("금", "목"),
    (9, 11): ("금", "토"), (9, 0): ("화", "금"), (9, 1): ("화", "화"),
}


def johu_v2(chart, favor, reasons):
    key = (chart.day_gan, chart.month.ji)
    if key in JOHU_TABLE:
        first, second = JOHU_TABLE[key]
        favor[first] = min(1.0, favor.get(first, 0) + 0.45)
        favor[second] = min(1.0, favor.get(second, 0) + 0.20)
        reasons.append(
            f"조후표: {GAN_H[chart.day_gan]}일간 {JI_H[chart.month.ji]}월 → "
            f"{first} 1순위, {second} 2순위")
        return (f"{JI_SEASON[chart.month.ji]}에 태어난 "
                f"{GAN_H[chart.day_gan]}({GAN_OHAENG[chart.day_gan]}) 일간이라 "
                f"{first} 기운으로 온도를 맞추는 것이 급선무로 봅니다.")

    c = chart.ohaeng_count()
    hot = c["화"] + c["토"] * 0.5
    cold = c["수"] + c["금"] * 0.5
    if hot >= 4.0 and c["수"] <= 1:
        favor["수"] = min(1.0, favor.get("수", 0) + 0.4)
        reasons.append("조후(폴백): 조열 → 水 가산")
        return "불·흙이 몰려 조열하니 물이 귀합니다."
    if cold >= 4.0 and c["화"] <= 1:
        favor["화"] = min(1.0, favor.get("화", 0) + 0.4)
        reasons.append("조후(폴백): 한습 → 火 가산")
        return "물·쇠가 몰려 한습하니 불이 귀합니다."
    return ""


@dataclass
class AnalysisV2:
    chart: object
    strength: StrengthV2
    field: NatalField
    special: object
    yongsin: list
    gisin: list
    neutral: list
    favor: dict
    favor_alt: dict
    reasons: list
    johu_note: str = ""
    gyeokguk: object = None


def _eokbu_favor(dg, label):
    d = GAN_OHAENG[dg]
    ins, big = SAENG_BY[d], d
    sik, jae, gwan = SAENG[d], GEUK[d], GEUK_BY[d]
    f = {e: 0.0 for e in ELEMS}
    if label in ("극신약", "신약"):
        m = 1.0 if label == "극신약" else 0.8
        f[ins] += m; f[big] += m * 0.9
        f[gwan] -= m; f[sik] -= m * 0.7; f[jae] -= m * 0.8
    elif label in ("극신강", "신강"):
        m = 1.0 if label == "극신강" else 0.8
        f[sik] += m * 0.9; f[jae] += m; f[gwan] += m * 0.8
        f[ins] -= m; f[big] -= m * 0.9
    return f


def analyze_v2(chart):
    nf = natal_field(chart)
    st = measure_strength_v2(chart, nf)
    dg = chart.day_gan
    reasons = list(st.notes)

    for ev in nf.events:
        reasons.append(ev)

    reasons.append(
        f"지장간·계절·통근을 반영한 실질 질량 — 아군 {st.ally:.2f} vs "
        f"적군 {st.enemy:.2f} → {st.ratio:.0%} → {st.label}"
        + (f"  (※ {st.alt_label} 과의 경계. 아래 대안 시나리오 참고)"
           if st.confidence == "경계" else ""))

    special = detect_jonggyeok(chart, st, nf)
    favor_alt = {}

    if special:
        reasons.append(f"특수격 판정 — {special['name']}: {special['reason']}")
        w = special["elem"]
        favor = {e: 0.0 for e in ELEMS}
        favor[w] += 1.0
        favor[SAENG_BY[w]] += 0.6
        favor[SAENG[w]] += 0.3
        d = GAN_OHAENG[dg]
        favor[d] -= 0.9
        favor[SAENG_BY[d]] -= 1.0
    else:
        favor = _eokbu_favor(dg, st.label)
        if st.label == "중화":
            lack = sorted(st.mass, key=lambda k: st.mass[k])[:2]
            for e in lack:
                favor[e] += 0.5
            excess = max(st.mass, key=lambda k: st.mass[k])
            favor[excess] -= 0.4
            reasons.append(
                f"중화 사주 — 실질 질량이 얇은 {', '.join(lack)}를 보완, "
                f"두터운 {excess}{_josa(excess,'은는')} 덜어냅니다.")
        if st.confidence == "경계" and st.alt_label:
            favor_alt = _eokbu_favor(dg, st.alt_label)

    johu = johu_v2(chart, favor, reasons)
    if favor_alt:
        johu_v2(chart, favor_alt, [])

    for k in favor:
        favor[k] = max(-1.0, min(1.0, favor[k]))
    for k in favor_alt:
        favor_alt[k] = max(-1.0, min(1.0, favor_alt[k]))

    yong = sorted([k for k, v in favor.items() if v >= 0.3], key=lambda k: -favor[k])
    gi = sorted([k for k, v in favor.items() if v <= -0.3], key=lambda k: favor[k])
    neu = [k for k in ELEMS if k not in yong and k not in gi]

    gyeokguk = detect_gyeokguk(chart, favor)
    reasons.append(f"[격국 교차검증] {gyeokguk['note']}")

    return AnalysisV2(chart=chart, strength=st, field=nf, special=special,
                      yongsin=yong, gisin=gi, neutral=neu, favor=favor,
                      favor_alt=favor_alt, reasons=reasons, johu_note=johu,
                      gyeokguk=gyeokguk)


def measure_strength_with_transit(a2, *transit_pillars, labels=None):
    """대운·세운을 얹어 원국 오행 질량을 재계산합니다 (#3) — '참고 판정'.

    ────────────────────────────────────────────────────────────
    왜 정본이 아니라 참고인가
    ────────────────────────────────────────────────────────────
    질량을 갱신하면 세 가지가 연쇄로 무너지기 때문입니다.

    1) 밴드 무효화
       STRENGTH_BANDS_V2 는 '원국' 분포의 분위수입니다. 운을 반영한
       질량은 다른 분포를 가지므로, 같은 밴드를 적용하면 "하위 15%"
       같은 설명이 거짓이 됩니다. 그래서 라벨은 참고로만 씁니다.

    2) 대운 간 비교 불가
       용신이 대운마다 바뀌면 favor[] 가 달라지고, 9개 대운 점수를
       같은 축에서 비교할 수 없게 됩니다. score_all_daeun_v2 의
       순위·상대값이 의미를 잃습니다.

    3) 이중 계상
       score_daeun_v2 의 hwa_adj 가 이미 화국을 점수에 반영하고
       있습니다. 질량에도 반영하고 점수 계산까지 바꾸면 같은 화국을
       두 번 세게 됩니다. 그래서 이 함수는 '점수를 만들지 않고'
       판정만 되돌려 줍니다. 점수 경로는 손대지 않았습니다.

    반환 dict 의 주요 키는 아래 코드와 tests/test_transit.py 참고.
    """
    chart = a2.chart
    base_st = a2.strength
    tf = transit_field(chart, *transit_pillars, labels=labels)
    st = measure_strength_v2(chart, tf)

    dg = chart.day_gan
    favor = _eokbu_favor(dg, st.label)
    if st.label == "중화":
        lack = sorted(st.mass, key=lambda k: st.mass[k])[:2]
        for e in lack:
            favor[e] += 0.5
        favor[max(st.mass, key=lambda k: st.mass[k])] -= 0.4
    johu_v2(chart, favor, [])
    for k in favor:
        favor[k] = max(-1.0, min(1.0, favor[k]))

    yong = sorted([k for k, v in favor.items() if v >= 0.3],
                  key=lambda k: -favor[k])
    base_yong = list(a2.yongsin)

    base_hwa = a2.field.hwa
    hwa_new = {e: round(tf.hwa[e] - base_hwa.get(e, 0.0), 6)
               for e in ELEMS if tf.hwa[e] - base_hwa.get(e, 0.0) > 1e-9}

    shifts = [(e, a2.favor[e], favor[e]) for e in ELEMS
              if abs(favor[e] - a2.favor[e]) >= 0.3]

    changed_label = st.label != base_st.label
    changed_yong = set(yong) != set(base_yong)

    if not hwa_new and not changed_label and not changed_yong:
        note = "이 기간에 새로 성립하는 화국이 없습니다. 원국 판정 그대로입니다."
    elif changed_yong:
        note = (f"화국 완성으로 용신이 일시적으로 "
                f"{'·'.join(base_yong) or '없음'} → {'·'.join(yong) or '없음'} "
                f"(으)로 이동할 수 있습니다. 원국 정본은 그대로입니다.")
    elif changed_label:
        note = (f"화국 완성으로 강약이 {base_st.label} → {st.label} 로 "
                f"기울지만, 용신은 유지됩니다.")
    else:
        note = "화국이 성립하지만 용신·강약을 뒤집을 만큼은 아닙니다."

    return {
        "label": st.label, "ratio": st.ratio, "mass": st.mass,
        "base_label": base_st.label, "base_ratio": base_st.ratio,
        "label_changed": changed_label,
        "favor": favor, "base_favor": dict(a2.favor),
        "yongsin": yong, "base_yongsin": base_yong,
        "yongsin_changed": changed_yong,
        "shifts": shifts,
        "hwa_new": hwa_new,
        "events": [e for e in tf.events if e.startswith("★")],
        "note": note,
        "strength": st, "field": tf,
    }


def scan_daeun_hwaguk(a2):
    """9개 대운 전 구간을 훑어 화국이 성립하는 구간을 찾습니다 (#3).

    UI 에서 "이 구간은 용신이 바뀔 수 있음" 배지를 붙이기 위한 것입니다.
    반환: {대운 시작나이: 참고판정 dict} — 변화가 있는 구간만.
    """
    out = {}
    for age, pillar in a2.chart.daeun:
        r = measure_strength_with_transit(a2, pillar, labels=("대운",))
        if r["hwa_new"] or r["label_changed"] or r["yongsin_changed"]:
            out[age] = r
    return out


def render_seun_section(a2, start_year=None, count=10, width=64):
    """세운 표를 사람이 읽는 텍스트로 (#6).

    대운 점수와 나란히 두되 '합산하지 말라'는 안내를 함께 넣습니다.
    두 값은 서로 다른 층(10년 배경 vs 그 해 사건)이고, 어느 비율로
    섞어야 하는지에 대한 근거가 없습니다.
    """
    if start_year is None:
        start_year = date.today().year
    rows = score_seun_range(a2, start_year, count)
    ch = a2.chart
    birth = ch.birth_local.year

    L = ["", f"{'[ 1년 주기 흐름 (세운) ]':^{width}}", "─" * width,
         _wrap("세운은 입춘에 바뀝니다. 1월~2월 초 생일은 전년도 세운에 "
               "속합니다. 아래 점수는 대운 점수와 '다른 축'입니다 — "
               "10년의 배경과 그 해의 사건은 층이 달라서, 두 값을 더하거나 "
               "평균 내면 근거 없는 숫자가 됩니다. 따로 읽으세요.",
               width - 4, "  "),
         ""]
    scope = f"{start_year}~{start_year + count - 1}년"
    prev_daeun = object()
    for r in rows:
        age = r["year"] - birth + 1
        if r["daeun"] is not None and r["daeun"].gapja != prev_daeun:
            du = ch.daeun_at(age)
            L.append(f"  ┌ 대운 {r['daeun'].hanja}"
                     f"{f' ({du[0]}~{du[0] + 9}세)' if du else ''}")
            prev_daeun = r["daeun"].gapja
        ipchun = find_solar_term(r["year"], 0) + timedelta(hours=9)
        L.append(f"  │ {r['year']} {r['pillar'].hanja} {age:>3}세  "
                 f"{_bar(r['percent'])} {r['grade']}"
                 f"   (입춘 {ipchun:%m/%d %H:%M}~)")
        L.append(f"  │     상대순위 {r['rank']}/{len(rows)} "
                 f"— {scope} 안에서의 위치일 뿐 절대 등급이 아닙니다")
        for n in r["notes"][:3]:
            L.append(_wrap("· " + n, width - 10, "  │     "))
        L.append("  │")
    L.append("")
    return L


def render_hwaguk_section(a2, width=64, today=None):
    """化局 참고 판정을 사람이 읽는 텍스트로 (#3).

    render_text() 와 분리해 둔 이유: v1 리포트는 v1 분석 스키마에 묶여
    있고, 이 기능은 v2 전용입니다. GUI v2 탭과 JSON 내보내기(#7)가
    이 함수를 공유합니다.

    반환값은 줄 리스트입니다. 화국이 하나도 없으면 빈 리스트입니다.
    """
    hits = scan_daeun_hwaguk(a2)
    meaningful = {k: v for k, v in hits.items()
                  if v["yongsin_changed"] or v["label_changed"]}
    if not meaningful:
        return []

    L = ["", f"{'[ 化局 구간 — 참고 판정 ]':^{width}}", "─" * width,
         _wrap("아래는 대운이 원국과 삼합·방합을 완성시켜 특정 오행이 "
               "일시적으로 판을 지배하는 구간입니다. 위 대운 점수·등급은 "
               "원국 용신을 기준으로 매긴 정본이고, 이 구간 표시는 "
               "'그 10년 동안은 잣대 자체가 흔들릴 수 있다'는 참고입니다. "
               "둘을 합산하지 마세요.", width - 4, "  "),
         ""]
    for age in sorted(meaningful):
        h = meaningful[age]
        pillar = dict(a2.chart.daeun)[age]
        L.append(f"  ● {age}~{age + 9}세  {pillar.hanja}")
        L.append(f"      강약  {h['base_label']}({h['base_ratio']:.0%})"
                 f" → {h['label']}({h['ratio']:.0%})"
                 + ("   ※ 참고 라벨입니다. 강약 밴드는 원국 분포 기준이라 "
                    "운 반영 수치에는 그대로 적용되지 않습니다."
                    if h["label_changed"] else ""))
        if h["yongsin_changed"]:
            L.append(f"      용신  {'·'.join(h['base_yongsin']) or '없음'}"
                     f" → {'·'.join(h['yongsin']) or '없음'}")
        for e in h["events"]:
            L.append(_wrap(e, width - 8, "        "))
        if h["shifts"]:
            L.append("      오행별 길흉 변동  " + ", ".join(
                f"{e} {a:+.2f}→{b:+.2f}" for e, a, b in h["shifts"]))
        L.append("")
    return L


GAN_W, JI_W = 0.35, 0.65


def _gaedu_jeolgak(g_elem, j_elem):
    """
    개두(蓋頭): 천간이 지지를 극함 → 지지의 작용이 눌림
    절각(截脚): 지지가 천간을 극함 → 천간의 작용이 잘림
    상생이면 서로 힘을 실어줍니다.

    같은 오행 대운이라도 이 관계에 따라 실제 체감이 크게 갈립니다.
    v1 에 이 항목이 없어서 인접 두 대운의 우열이 뒤집히곤 합니다.
    """
    gm, jm, note = 1.0, 1.0, None
    if GEUK[g_elem] == j_elem:
        jm, note = 0.55, (f"개두 — 천간 {g_elem}{_josa(g_elem,'이가')} 지지 "
                          f"{j_elem}{_josa(j_elem,'을를')} 극해 지지 작용 반감")
    elif GEUK[j_elem] == g_elem:
        gm, note = 0.50, (f"절각 — 지지 {j_elem}{_josa(j_elem,'이가')} 천간 "
                          f"{g_elem}{_josa(g_elem,'을를')} 극해 천간 작용 반감")
    elif SAENG[j_elem] == g_elem:
        gm, note = 1.25, (f"지지 {j_elem}{_josa(j_elem,'이가')} 천간 "
                          f"{g_elem}{_josa(g_elem,'을를')} 생 → 천간에 힘이 실림")
    elif SAENG[g_elem] == j_elem:
        jm, note = 1.15, (f"천간 {g_elem}{_josa(g_elem,'이가')} 지지 "
                          f"{j_elem}{_josa(j_elem,'을를')} 생 → 지지가 두터워짐")
    return gm, jm, note


def score_daeun_v2(a2, pillar, age=None):
    ch = a2.chart
    favor = a2.favor
    notes = []
    jis = [p.ji for p in ch.pillars]
    labels = "년월일시"

    g_elem = GAN_OHAENG[pillar.gan]
    j_elem = JI_OHAENG[pillar.ji]

    gm, jm, gj_note = _gaedu_jeolgak(g_elem, j_elem)
    if gj_note:
        notes.append(gj_note)


    r = root_strength(g_elem, ch, a2.field.effect)
    if g_elem in [GAN_OHAENG[g] for g, _ in JIJANGGAN[pillar.ji]]:
        r += 0.5
    if r < 0.15:
        gm *= 0.55
        notes.append(f"대운 천간 {GAN_H[pillar.gan]} 무근 → 영향력 약함")

    gan_score = favor[g_elem] * gm
    ji_score = favor[j_elem] * jm

    def lab(e):
        v = favor[e]
        return "도움" if v >= 0.3 else ("부담" if v <= -0.3 else "중립")

    notes.insert(0, f"지지 {JI_H[pillar.ji]}({j_elem}) {lab(j_elem)} "
                    f"[후반 5년] {ji_score:+.2f}")
    notes.insert(0, f"천간 {GAN_H[pillar.gan]}({g_elem}) {lab(g_elem)} "
                    f"[전반 5년] {gan_score:+.2f}")


    hwa_adj = 0.0
    for combo, elem in list(SAMHAP.items()) + list(BANGHAP.items()):
        if pillar.ji not in combo:
            continue
        need = combo - {pillar.ji}
        if need <= set(jis):
            weight = 0.45 if combo in SAMHAP else 0.38
            hwa_adj += favor[elem] * weight
            notes.append(
                f"★ 대운 {JI_H[pillar.ji]} + 원국 "
                f"{'·'.join(JI_H[x] for x in sorted(need))} → "
                f"{elem}국 완성. {elem} 기운이 이 10년을 지배 "
                f"({favor[elem] * weight:+.2f})")
        elif len(need & set(jis)) == 1:
            pair = frozenset({pillar.ji} | (need & set(jis)))
            if pair in BANHAP:
                hwa_adj += favor[elem] * 0.16
                notes.append(
                    f"대운 {JI_H[pillar.ji]} 반합 → {elem} 기운 "
                    f"({favor[elem] * 0.16:+.2f})")


    chung_pen = 0.0
    for i, j in enumerate(jis):
        if is_chung(pillar.ji, j):
            w = {0: 0.10, 1: 0.22, 2: 0.20, 3: 0.10}[i]

            tgt = JI_OHAENG[j]
            if favor[tgt] <= -0.3:
                chung_pen -= w * 0.5
                notes.append(
                    f"{JI_H[pillar.ji]}가 원국 {labels[i]}지 {JI_H[j]}"
                    f"(기신)를 충 → 묵은 것을 걷어내는 충 (+{w * 0.5:.2f})")
            else:
                chung_pen += w
                notes.append(
                    f"{JI_H[pillar.ji]}가 원국 {labels[i]}지 {JI_H[j]}를 충 "
                    f"→ 변동·이동 (-{w:.2f})")


    for i, j in enumerate(jis):
        key = frozenset((pillar.ji, j))
        if any(pillar.ji in c and j in c for c in SAMHYEONG) and pillar.ji != j:
            chung_pen += 0.07
            notes.append(f"{JI_H[pillar.ji]}·{JI_H[j]} 형 → 마찰·구설 (-0.07)")
        if key in YUKHAE:
            chung_pen += 0.04


    for i, p in enumerate(ch.pillars):
        key = frozenset((pillar.gan, p.gan))
        if len(key) == 2 and key in CHEONGAN_HAP:
            notes.append(
                f"대운 천간 {GAN_H[pillar.gan]}이 원국 {labels[i]}간 "
                f"{GAN_H[p.gan]}과 합 → {CHEONGAN_HAP[key]}로 기운이 묶임")
            gan_score *= 0.8

    raw = gan_score * GAN_W + ji_score * JI_W + hwa_adj - chung_pen
    raw_clamped = max(-1.0, min(1.0, raw))

    grade = stars = ""
    for th, gr, stz in GRADE_BANDS:
        if raw_clamped >= th:
            grade, stars = gr, stz
            break

    return {
        "age": age, "pillar": pillar,
        "score": raw_clamped, "raw_unclamped": raw,
        "gan_score": gan_score, "ji_score": ji_score,
        "grade": grade, "stars": stars,
        "percent": int(round((raw_clamped + 1) * 50)),
        "notes": notes,
    }


def score_all_daeun_v2(a2, normalize=True):
    """
    9개 대운을 채점하고, 절대점수가 한쪽으로 포화되면
    상대 순위를 함께 제공합니다.

    v1 은 용신이 한쪽으로 쏠리면 인생 전 구간이 '매우 어려움'으로
    나와서 구간 간 비교 자체가 불가능해집니다.
    """
    out = [score_daeun_v2(a2, p, age) for age, p in a2.chart.daeun]
    if not normalize or not out:
        return out
    vals = [s["raw_unclamped"] for s in out]
    lo, hi = min(vals), max(vals)
    span = hi - lo
    order = sorted(range(len(out)), key=lambda i: -vals[i])
    saturated = sum(1 for s in out if abs(s["score"]) >= 1.0 - 1e-9)
    for rank, i in enumerate(order, 1):
        out[i]["rank"] = rank
        out[i]["rel"] = 0.5 if span < 1e-9 else (vals[i] - lo) / span

        out[i]["rank_scope"] = f"본인 대운 {len(out)}구간"
        out[i]["rank_is_relative"] = True


        out[i]["score_saturated"] = abs(out[i]["score"]) >= 1.0 - 1e-9
        out[i]["n_saturated"] = saturated
    return out


SEUN_CHUNG_W = {"대운": 0.20, "년": 0.08, "월": 0.18, "일": 0.16, "시": 0.08}
SEUN_HWA_SAMHAP = 0.40
SEUN_HWA_BANGHAP = 0.32
SEUN_HWA_BANHAP = 0.12


def score_seun_v2(a2, seun_pillar, daeun_pillar=None, year=None):
    """세운 한 해를 채점합니다 (#6).

    daeun_pillar 를 주면 대운을 함께 얹어 3자 관계를 봅니다.
    반환 dict 의 score 는 대운 점수와 별개 축입니다. 합산 금지.
    """
    ch = a2.chart
    favor = a2.favor
    jis = [p.ji for p in ch.pillars]
    labels = "년월일시"
    notes = []

    g_elem = GAN_OHAENG[seun_pillar.gan]
    j_elem = JI_OHAENG[seun_pillar.ji]

    gm, jm, gj_note = _gaedu_jeolgak(g_elem, j_elem)
    if gj_note:
        notes.append(gj_note)

    r = root_strength(g_elem, ch, a2.field.effect)
    if g_elem in [GAN_OHAENG[g] for g, _ in JIJANGGAN[seun_pillar.ji]]:
        r += 0.5
    if r < 0.15:
        gm *= 0.55
        notes.append(f"세운 천간 {GAN_H[seun_pillar.gan]} 무근 → 영향력 약함")

    gan_score = favor[g_elem] * gm
    ji_score = favor[j_elem] * jm

    def lab(e):
        v = favor[e]
        return "도움" if v >= 0.3 else ("부담" if v <= -0.3 else "중립")

    notes.insert(0, f"지지 {JI_H[seun_pillar.ji]}({j_elem}) {lab(j_elem)} "
                    f"{ji_score:+.2f}")
    notes.insert(0, f"천간 {GAN_H[seun_pillar.gan]}({g_elem}) {lab(g_elem)} "
                    f"{gan_score:+.2f}")


    pool = list(jis)
    if daeun_pillar is not None:
        pool.append(daeun_pillar.ji)
    hwa_adj = 0.0
    for combo, elem in list(SAMHAP.items()) + list(BANGHAP.items()):
        if seun_pillar.ji not in combo:
            continue
        need = combo - {seun_pillar.ji}
        if need <= set(pool):
            via_daeun = (daeun_pillar is not None
                         and daeun_pillar.ji in need
                         and daeun_pillar.ji not in set(jis))
            w = SEUN_HWA_SAMHAP if combo in SAMHAP else SEUN_HWA_BANGHAP
            hwa_adj += favor[elem] * w
            notes.append(
                f"★ 세운 {JI_H[seun_pillar.ji]}"
                + ("+대운 " + JI_H[daeun_pillar.ji] if via_daeun else "")
                + f" + 원국 → {elem}국 완성 ({favor[elem] * w:+.2f})"
                + ("  ※ 대운이 있어야 성립하는 조합입니다. "
                   "이 대운이 끝나면 사라집니다." if via_daeun else ""))
        elif len(need & set(pool)) == 1:
            pair = frozenset({seun_pillar.ji} | (need & set(pool)))
            if pair in BANHAP:
                hwa_adj += favor[elem] * SEUN_HWA_BANHAP
                notes.append(f"세운 반합 → {elem} 기운 "
                             f"({favor[elem] * SEUN_HWA_BANHAP:+.2f})")


    chung_pen = 0.0
    targets = [(labels[i], j) for i, j in enumerate(jis)]
    if daeun_pillar is not None:
        targets.append(("대운", daeun_pillar.ji))
    for name, j in targets:
        if not is_chung(seun_pillar.ji, j):
            continue
        w = SEUN_CHUNG_W[name]
        tgt = JI_OHAENG[j]
        if favor[tgt] <= -0.3:
            chung_pen -= w * 0.5
            notes.append(f"{JI_H[seun_pillar.ji]}가 {name}"
                         f"{'지' if name in labels else ''} {JI_H[j]}"
                         f"(기신)를 충 → 걷어내는 충 (+{w * 0.5:.2f})")
        else:
            chung_pen += w
            notes.append(f"{JI_H[seun_pillar.ji]}가 {name}"
                         f"{'지' if name in labels else ''} {JI_H[j]}를 충 "
                         f"→ 변동 (-{w:.2f})")


    for i, p in enumerate(ch.pillars):
        key = frozenset((seun_pillar.gan, p.gan))
        if len(key) == 2 and key in CHEONGAN_HAP:
            notes.append(f"세운 천간 {GAN_H[seun_pillar.gan]}이 원국 "
                         f"{labels[i]}간 {GAN_H[p.gan]}과 합 → 기운이 묶임")
            gan_score *= 0.8

    raw = gan_score * GAN_W + ji_score * JI_W + hwa_adj - chung_pen
    score = max(-1.0, min(1.0, raw))
    percent = int(round((score + 1) * 50))
    grade = stars = None
    for threshold, g, s in GRADE_BANDS:
        if score >= threshold:
            grade, stars = g, s
            break
    if grade is None:
        grade, stars = GRADE_BANDS[-1][1], GRADE_BANDS[-1][2]

    return {
        "year": year,
        "pillar": seun_pillar,
        "daeun": daeun_pillar,
        "score": score,
        "raw_unclamped": raw,
        "percent": percent,
        "grade": grade,
        "stars": stars,
        "gan_score": gan_score,
        "ji_score": ji_score,
        "hwa_adj": hwa_adj,
        "chung_pen": chung_pen,
        "notes": notes,
    }


def score_seun_range(a2, start_year, count=10, normalize=True):
    """연속한 세운을 채점합니다. 각 해에 해당하는 대운을 자동으로 붙입니다.

    normalize=True 면 rank/rel 이 붙습니다. 이 값은 '요청한 이 구간
    안에서의' 상대 위치일 뿐 절대 등급이 아닙니다 (#5 와 같은 주의).
    """
    ch = a2.chart
    birth_year = ch.birth_local.year
    out = []
    for y in range(start_year, start_year + count):
        age = y - birth_year + 1
        du = ch.daeun_at(age)
        out.append(score_seun_v2(a2, ch.seun(y),
                                 du[1] if du else None, year=y))
    if not normalize or not out:
        return out
    vals = [s["raw_unclamped"] for s in out]
    lo, hi = min(vals), max(vals)
    span = hi - lo
    for rank, i in enumerate(sorted(range(len(out)), key=lambda i: -vals[i]), 1):
        out[i]["rank"] = rank
        out[i]["rel"] = 0.5 if span < 1e-9 else (vals[i] - lo) / span
        out[i]["rank_scope"] = f"{start_year}~{start_year + count - 1}년"
    return out


ILUN_DAMPING = 0.5
"""오늘(하루) 단위 채점에 곱하는 감쇠 계수.

세운 채점 엔진(score_seun_v2)을 그대로 재사용하되, 하루의 영향력은
1년보다 작게 잡아야 한다는 상식적 가정을 반영한 값입니다. 명리학에서
'일운(하루 단위 운세)'을 정량화하는 확립된 표준 공식은 없고 유파차가
큰 영역이라, 이 계수는 임의의 근사치입니다. 참고용으로만 쓰세요.
"""


def score_ilun_v2(a2, target_date=None, damping=ILUN_DAMPING):
    """오늘(하루) 운세를 채점합니다.

    세운 채점 엔진(score_seun_v2)의 천간·지지 유불리, 합·충 판정을 그대로
    가져다 쓰되, 원(raw) 점수에 damping 을 곱해 하루라는 짧은 단위의 영향력을
    깎습니다. target_date 를 생략하면 한국 시간 기준 오늘 날짜를 씁니다.

    ※ 세운·대운과는 완전히 다른(더 가벼운) 축입니다. 세 값을 더하거나
      평균 내지 마세요.
    """
    ch = a2.chart
    if target_date is None:
        target_date = datetime.now(ZoneInfo("Asia/Seoul")).date()

    di = (_jdn(target_date) + 49) % 60
    day_pillar = Pillar.from_gapja(di)

    age = target_date.year - ch.birth_local.year + 1
    du = ch.daeun_at(age)
    daeun_pillar = du[1] if du else None

    base = score_seun_v2(a2, day_pillar, daeun_pillar, year=None)

    raw = base["raw_unclamped"] * damping
    score = max(-1.0, min(1.0, raw))
    percent = int(round((score + 1) * 50))
    grade = stars = None
    for threshold, g, s in GRADE_BANDS:
        if score >= threshold:
            grade, stars = g, s
            break
    if grade is None:
        grade, stars = GRADE_BANDS[-1][1], GRADE_BANDS[-1][2]

    notes = [n.replace("세운", "오늘") for n in base["notes"]]

    return {
        "date": target_date,
        "pillar": day_pillar,
        "daeun": daeun_pillar,
        "score": score,
        "raw_unclamped": raw,
        "percent": percent,
        "grade": grade,
        "stars": stars,
        "notes": notes,
    }


"""
신살은 억부·격국과는 또 다른 갈래의 명리 도구입니다. "이 사주가 강한가
약한가"를 묻지 않고, 특정 글자 조합 자체에 전통적으로 붙어온 상징을
읽습니다. 용신 판정만큼 이론적 정합성이 탄탄하지는 않고 유파차가
특히 큰 영역이라, 여기서는 원국(연·월·일·시 네 기둥)에 한정해서
가장 널리 쓰이는 8가지만 규칙 기반으로 판정합니다. 대운·세운이
신살을 건드리는 것까지는 다루지 않습니다(범위를 넓히면 오히려
'맞다/틀리다'를 검증하기 어려운 주장이 늘어나기 때문입니다).

같은 신살이라도 기준을 년지로 잡느냐 일지로 잡느냐에 따라 결과가
달라질 수 있는 것들(도화·역마·화개)은 두 기준을 모두 계산해서
보여줍니다. 어느 기준이 '맞다'고 단정하지 않는 것 자체가 근거입니다.
"""


_SAMHAP_GROUPS = {
    "인오술": frozenset((2, 6, 10)),
    "사유축": frozenset((5, 9, 1)),
    "신자진": frozenset((8, 0, 4)),
    "해묘미": frozenset((11, 3, 7)),
}

_DOHWA_TARGET = {"인오술": 3, "사유축": 6, "신자진": 9, "해묘미": 0}
_YEOKMA_TARGET = {"인오술": 8, "사유축": 11, "신자진": 2, "해묘미": 5}
_HWAGAE_TARGET = {"인오술": 10, "사유축": 1, "신자진": 4, "해묘미": 7}


_CHEONEUL = {
    0: {1, 7}, 4: {1, 7}, 6: {1, 7},
    1: {0, 8}, 5: {0, 8},
    2: {11, 9}, 3: {11, 9},
    8: {3, 5}, 9: {3, 5},
    7: {6, 2},
}


_YANGIN = {0: 3, 2: 6, 4: 6, 6: 9, 8: 0}


_GOEGANG_PAIRS = {(6, 4), (6, 10), (8, 4), (4, 10)}


_BAEKHO_PAIRS = {(0, 4), (1, 7), (2, 10), (3, 1), (4, 4), (8, 10), (9, 1)}


_GONGMANG_TABLE = [(10, 11), (8, 9), (6, 7), (4, 5), (2, 3), (0, 1)]


def _samhap_group_of(ji):
    for name, ids in _SAMHAP_GROUPS.items():
        if ji in ids:
            return name
    return None


def detect_sinsal(chart):
    """원국 기준 8종 신살을 판정해 리스트로 반환.
    각 항목: {"name", "basis", "hit"(기둥 라벨 리스트), "note"}
    """
    out = []
    pillars = list(zip("년월일시", chart.pillars))


    triples = [
        ("도화살", _DOHWA_TARGET,
         "인기·매력, 주목받는 자리와 연결짓는 것이 전통적 해석입니다."),
        ("역마살", _YEOKMA_TARGET,
         "이동·변동, 이사·출장·해외 인연과 연결짓는 것이 전통적 해석입니다."),
        ("화개살", _HWAGAE_TARGET,
         "예술·종교·학문, 반복보다 몰입·마무리를 선호하는 기질과 "
         "연결짓는 것이 전통적 해석입니다."),
    ]
    for basis_lab, basis_ji in (("년지", chart.year.ji), ("일지", chart.day.ji)):
        grp = _samhap_group_of(basis_ji)
        if not grp:
            continue
        for name, table, desc in triples:
            target = table[grp]
            hits = [lab for lab, p in pillars if p.ji == target]
            if hits:
                out.append({
                    "name": name, "basis": f"{basis_lab} 기준",
                    "hit": hits,
                    "note": (f"{basis_lab} {JI_H[basis_ji]}가 속한 {grp} 삼합국의 "
                             f"{name.replace('살','')} 자리인 {JI_H[target]}가 "
                             f"{'·'.join(hits)}에 있습니다. {desc}"),
                })


    dg = chart.day_gan
    targets = _CHEONEUL.get(dg)
    if targets:
        hits = [lab for lab, p in pillars if p.ji in targets]
        if hits:
            out.append({
                "name": "천을귀인", "basis": "일간 기준",
                "hit": hits,
                "note": (f"일간 {GAN_H[dg]}의 천을귀인 지지가 {'·'.join(hits)}에 "
                         f"있습니다. 명리학에서 가장 대표적인 길신(吉神)으로, "
                         f"어려운 상황에서 도움을 받는 힘과 연결짓는 것이 통설입니다."),
            })


    target = _YANGIN.get(dg)
    if target is not None:
        hits = [lab for lab, p in pillars if p.ji == target]
        if hits:
            out.append({
                "name": "양인살", "basis": "일간 기준",
                "hit": hits,
                "note": (f"일간 {GAN_H[dg]}의 양인 지지 {JI_H[target]}가 "
                         f"{'·'.join(hits)}에 있습니다. 힘이 과도하게 몰릴 때 "
                         f"생기는 극단성과 연결짓는 것이 통설이며, 잘 다스리면 "
                         f"강한 추진력으로도 해석합니다."),
            })


    if (chart.day.gan, chart.day.ji) in _GOEGANG_PAIRS:
        out.append({
            "name": "괴강살", "basis": "일주",
            "hit": ["일"],
            "note": (f"일주 {chart.day.hanja}가 괴강 일주입니다. 극단적으로 "
                     f"강한 기운으로 보아, 크게 되거나 크게 무너지는 양극단과 "
                     f"연결짓는 것이 통설입니다."),
        })


    hits = [lab for lab, p in pillars if (p.gan, p.ji) in _BAEKHO_PAIRS]
    if hits:
        out.append({
            "name": "백호대살", "basis": "간지 조합",
            "hit": hits,
            "note": (f"{'·'.join(hits)}주가 백호대살에 해당하는 간지입니다. "
                     f"해당 기둥이 상징하는 육친·시기에 갑작스러운 사건과 "
                     f"연결짓는 것이 통설입니다."),
        })


    soon_idx = chart.day.gapja // 10
    gm_targets = _GONGMANG_TABLE[soon_idx]
    hits = [lab for lab, p in pillars if p.ji in gm_targets and lab != "일"]
    if hits:
        out.append({
            "name": "공망", "basis": "일주 순중 기준",
            "hit": hits,
            "note": (f"일주 {chart.day.hanja}가 속한 순(旬)의 공망 지지"
                     f"({JI_H[gm_targets[0]]}·{JI_H[gm_targets[1]]})가 "
                     f"{'·'.join(hits)}에 있습니다. 해당 자리의 기운이 "
                     f"헛헛하거나 결과로 잘 잡히지 않는다고 보는 것이 통설이며, "
                     f"반대로 얽매임 없는 자유로움으로 해석하기도 합니다."),
        })

    return out


def _ratio_bar(v, width=18):
    """0.0~1.0 비율용 막대.

    ※ 예전에는 이 함수 이름이 _bar 였습니다. 1300행의
       _bar(percent, width=20) — 0~100 스케일 — 를 통째로 덮어써서,
       대운 막대가 25%든 100%든 전부 꽉 찬 채로 출력되고 있었습니다.
       (0~100 값이 min(1.0, v) 에 걸려 항상 1.0 이 됨)
       이름을 나눠 충돌을 없앴습니다.
    """
    n = int(round(max(0.0, min(1.0, v)) * width))
    return "█" * n + "░" * (width - n)


def render_compare(chart):
    L = []
    a1 = analyze(chart)
    s1 = score_all_daeun(a1)
    a2 = analyze_v2(chart)
    s2 = score_all_daeun_v2(a2)

    L.append("═" * 70)
    L.append(f"  {chart.birth_local:%Y-%m-%d %H:%M}  "
             f"{'남' if chart.is_male else '여'}  {chart.place.name}")
    L.append(f"  원국  {chart.year.hanja} {chart.month.hanja} "
             f"{chart.day.hanja} {chart.hour.hanja}   "
             f"(일간 {GAN_H[chart.day_gan]})")
    L.append("═" * 70)

    L.append("\n[ 강약 판정 ]")
    L.append(f"  v1  {a1.strength.ratio:6.1%}  {a1.strength.label:6s} "
             f"용신 {'·'.join(a1.yongsin) or '-'}")
    tag = "" if a2.strength.confidence == "확실" else\
        f"  ⚠ {a2.strength.alt_label} 과의 경계"
    L.append(f"  v2  {a2.strength.ratio:6.1%}  {a2.strength.label:6s} "
             f"용신 {'·'.join(a2.yongsin) or '-'}{tag}")
    if a2.special:
        L.append(f"      ★ {a2.special['name']} 로 판정 — 억부 결론을 반전시킴")

    L.append("\n[ v2 판단 근거 ]")
    for r in a2.reasons:
        L.append(f"  · {r}")
    if a2.johu_note:
        L.append(f"  · {a2.johu_note}")

    L.append("\n[ 실질 오행 질량 (지장간·계절·통근 반영) ]")
    tot = sum(a2.strength.mass.values()) or 1
    for e in ELEMS:
        m = a2.strength.mass[e]
        grp = sipseong_by_ohaeng(chart.day_gan, e)
        L.append(f"  {e}  {m:5.2f}  {m / tot:5.1%}  {grp}  "
                 f"{_ratio_bar(m / tot * 2.5, 14)}")

    L.append("\n[ 대운 비교 ]")
    L.append(f"  {'구간':>10}  {'간지':^5}  {'v1':^12}     {'v2':^12}   상대순위")
    L.append("  " + "─" * 66)
    for x, y in zip(s1, s2):
        flip = "  ← 판정 뒤집힘" if (x["score"] > 0.2) != (y["score"] > 0.2)\
            and abs(x["score"] - y["score"]) > 0.3 else ""
        L.append(
            f"  {x['age']:>3}~{x['age'] + 9:<3}세  {x['pillar'].hanja}  "
            f"{x['score']:+.2f} {x['grade']:<6s}  →  "
            f"{y['score']:+.2f} {y['grade']:<6s} "
            f"#{y['rank']}{flip}")

    L.append("\n[ v2 대운 상세 ]")
    for y in s2:
        L.append(f"\n  {y['age']}~{y['age'] + 9}세  {y['pillar'].hanja}  "
                 f"{y['grade']}(절대등급)  "
                 f"[본인 대운 {len(s2)}구간 중 {y['rank']}위 — 상대 위치일 뿐]")
        L.append(f"     전반5년 {y['gan_score']:+.2f} │ "
                 f"후반5년 {y['ji_score']:+.2f}")
        for n in y["notes"]:
            L.append(f"     · {n}")

    if a2.favor_alt:
        L.append("\n" + "─" * 70)
        L.append(f"  ⚠ 강약이 경계 구간입니다. '{a2.strength.alt_label}'으로 볼 경우:")
        alt = AnalysisV2(**{**a2.__dict__, "favor": a2.favor_alt})
        s3 = score_all_daeun_v2(alt)
        for y in s3:
            L.append(f"     {y['age']:>3}~{y['age'] + 9:<3}세 "
                     f"{y['pillar'].hanja}  {y['score']:+.2f} {y['grade']}")
        L.append("  두 시나리오가 갈리는 구간은 다른 근거(격국·직업·실제 경험)로"
                 " 판단하세요.")

    L.append("\n" + "─" * 70)
    L.append("  이 결과는 전통 해석 체계를 코드로 옮긴 것이며 검증된 예측이 아닙니다.")
    return "\n".join(L)


ELEM_COLOR = {
    "목": "#3C8C5C",
    "화": "#D1495B",
    "토": "#D9A441",
    "금": "#8E8779",
    "수": "#2B3A67",
}
ELEM_COLOR_SOFT = {
    "목": "#DDEEE1", "화": "#F6D9DC", "토": "#F5E7C7",
    "금": "#E6E3DC", "수": "#DCE0EC",
}

BG_ROOT = "#EFE9DA"
BG_SIDEBAR = "#1C2033"
BG_SIDEBAR2 = "#262B45"
BG_CARD = "#FFFFFF"
BG_CARD_ALT = "#F7F2E7"
FG_SIDEBAR = "#EDE9DD"
FG_SIDEBAR_MUTE = "#9AA0C0"
ACCENT = "#C9A227"
ACCENT_DARK = "#A6821C"
TEXT_MAIN = "#2B2924"
TEXT_MUTE = "#7C7666"
GOOD = "#2E7D5B"
BAD = "#C0392B"
WARN_BG = "#FBEFD1"
WARN_FG = "#8A6415"
TOOLTIP_BG = "#2B2924"
TOOLTIP_FG = "#F5F0E6"


def _pick_font(candidates, default="TkDefaultFont"):
    fams = set(tkfont.families())
    for c in candidates:
        if c in fams:
            return c
    return default


KOR_CANDIDATES = ["Malgun Gothic", "AppleGothic", "NanumGothic",
                  "Noto Sans CJK KR", "Noto Sans KR", "맑은 고딕", "Apple SD Gothic Neo"]


KOR_FONT = "TkDefaultFont"


def rounded_rect(canvas, x1, y1, x2, y2, r=14, **kw):
    r = min(r, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kw)


def draw_taegeuk(canvas, cx, cy, r, c1="#C0392B", c2="#2B3A67"):
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=c1, outline="")
    canvas.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=180,
                      fill=c2, outline="", style=tk.PIESLICE)
    canvas.create_oval(cx - r / 2, cy - r, cx + r / 2, cy, fill=c2, outline="")
    canvas.create_oval(cx - r / 2, cy, cx + r / 2, cy + r, fill=c1, outline="")
    canvas.create_oval(cx - r / 6, cy - r / 2 - r / 6, cx + r / 6, cy - r / 2 + r / 6,
                       fill=c1, outline="")
    canvas.create_oval(cx - r / 6, cy + r / 2 - r / 6, cx + r / 6, cy + r / 2 + r / 6,
                       fill=c2, outline="")
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=TEXT_MAIN, width=1.4)


def draw_donut(canvas, cx, cy, r_out, r_in, data, color_map, bg=BG_CARD):
    total = sum(data.values()) or 1
    start = 90.0
    for k, v in data.items():
        if v <= 0:
            continue
        extent = -360.0 * (v / total)
        canvas.create_arc(cx - r_out, cy - r_out, cx + r_out, cy + r_out,
                          start=start, extent=extent, fill=color_map[k],
                          outline=bg, width=2, style=tk.PIESLICE)
        start += extent
    canvas.create_oval(cx - r_in, cy - r_in, cx + r_in, cy + r_in,
                       fill=bg, outline=bg)


def draw_gauge(canvas, x, y, w, h, ratio, color, bg="#EDE4CF", track_r=None):
    """0~1 사이 ratio 를 가로 게이지로. 중앙(0.5) 위치에 기준선 표시."""
    r = track_r if track_r is not None else h / 2
    rounded_rect(canvas, x, y, x + w, y + h, r=r, fill=bg, outline="")
    ratio = max(0.0, min(1.0, ratio))
    fw = max(h, w * ratio)
    rounded_rect(canvas, x, y, x + fw, y + h, r=r, fill=color, outline="")
    mid = x + w / 2
    canvas.create_line(mid, y - 3, mid, y + h + 3, fill=TEXT_MUTE, width=1, dash=(2, 2))


class ToolTip:
    """위젯에 마우스를 올리면 부연 설명을 보여주는 말풍선."""

    def __init__(self, widget, text, delay=350, wraplength=260):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, event=None):
        self._unschedule()
        self._after_id = self.widget.after(self.delay, self._show)

    def _unschedule(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 6
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            tw.wm_attributes("-topmost", True)
        except Exception:
            pass
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, justify="left", bg=TOOLTIP_BG, fg=TOOLTIP_FG,
                 font=(KOR_FONT, 9), wraplength=self.wraplength, padx=10, pady=7)\
            .pack()

    def _hide(self, event=None):
        self._unschedule()
        if self._tip:
            self._tip.destroy()
            self._tip = None


class StatBar(tk.Frame):
    """오행 하나를 나타내는 '능력치' 스타일 가로 막대."""

    def __init__(self, master, elem, value, max_value, suffix="", tag="", **kw):
        super().__init__(master, bg=kw.pop("bg", BG_CARD))
        color = ELEM_COLOR[elem]
        row = tk.Frame(self, bg=self["bg"])
        row.pack(fill="x")
        chip = tk.Label(row, text=elem, bg=color, fg="white", width=2,
                        font=(KOR_FONT, 11, "bold"))
        chip.pack(side="left", padx=(0, 8), ipady=2)
        tk.Label(row, text=f"{value:.2f}{suffix}", bg=self["bg"], fg=TEXT_MAIN,
                 font=(KOR_FONT, 10, "bold"), width=8, anchor="w").pack(side="left")
        if tag:
            tk.Label(row, text=tag, bg=ELEM_COLOR_SOFT[elem], fg=color,
                     font=(KOR_FONT, 8, "bold"), padx=5).pack(side="right")
        cv = tk.Canvas(self, height=14, bg=self["bg"], highlightthickness=0)
        cv.pack(fill="x", pady=(3, 6))
        self._cv, self._elem, self._value, self._max = cv, elem, value, max_value
        cv.bind("<Configure>", self._redraw)

    def _redraw(self, event=None):
        cv = self._cv
        cv.delete("all")
        w = cv.winfo_width() or 260
        ratio = 0 if self._max <= 0 else self._value / self._max
        draw_gauge(cv, 2, 1, w - 4, 12, ratio, ELEM_COLOR[self._elem], bg=BG_CARD_ALT)


class ScrollFrame(tk.Frame):
    """세로 스크롤이 되는 컨테이너. .body 에 위젯을 채우면 됩니다."""

    def __init__(self, master, bg=BG_ROOT, **kw):
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.body.bind("<Configure>",
                       lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self._win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()


def card(master, bg=BG_CARD, pad=16):
    f = tk.Frame(master, bg=bg, highlightbackground="#E4DCC8", highlightthickness=1)
    inner = tk.Frame(f, bg=bg)
    inner.pack(fill="both", expand=True, padx=pad, pady=pad)
    return f, inner


def h3(master, text, bg=BG_CARD, fg=TEXT_MAIN):
    return tk.Label(master, text=text, bg=bg, fg=fg, font=(KOR_FONT, 12, "bold"))


OPT_HELP = {
    "야자시": ("23시~24시(자시) 출생자의 일주를 그날(당일)의 일주로 봅니다.\n"
              "실무에서 가장 널리 쓰이는 방식입니다."),
    "정자시": ("23시~24시(자시) 출생자의 일주를 다음날 일주로 봅니다.\n"
              "야자시설과 반대되는 유파로, 일부 만세력이 이 방식을 씁니다."),
    "진태양시": ("출생지의 경도를 반영해 실제 태양이 남중하는 시각(진태양시)을 사용합니다.\n"
               "표준시와 최대 30분 이상 차이가 나며, 시주(태어난 시각의 간지) 판정에\n"
               "직접 영향을 줍니다. 끄면 표준 시간대 기준으로만 계산합니다.\n"
               "(권장: 켜짐)"),
    "균시차": ("지구 공전 궤도가 완전한 원이 아니고 자전축이 기울어져 있어 생기는\n"
              "시차(균시차, 최대 ±16분)를 추가로 보정합니다.\n"
              "명리 실무에서는 대개 생략합니다. (권장: 꺼짐)"),
}


class SajuApp(tk.Tk):
    def __init__(self):
        super().__init__()
        global KOR_FONT
        KOR_FONT = _pick_font(KOR_CANDIDATES, default=self._safe_default_font())

        self.title("사주+ · 명리 분석기")
        self.geometry("1360x860")
        self.minsize(1080, 680)
        self.configure(bg=BG_ROOT)

        self.chart = self.a1 = self.s1 = self.a2 = self.s2 = None
        self.today_age = None
        self._queue = queue.Queue()

        self._setup_style()
        self._build_layout()
        self._poll_queue()

    def _safe_default_font(self):
        try:
            return tkfont.nametofont("TkDefaultFont").actual("family")
        except Exception:
            return "TkDefaultFont"


    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TNotebook", background=BG_ROOT, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_CARD_ALT, foreground=TEXT_MUTE,
                        padding=(18, 10), font=(KOR_FONT, 10, "bold"), borderwidth=0)
        style.map("TNotebook.Tab",
                 background=[("selected", BG_CARD)],
                 foreground=[("selected", TEXT_MAIN)])

        style.configure("Side.TCombobox", fieldbackground=BG_SIDEBAR2,
                        background=BG_SIDEBAR2, foreground=FG_SIDEBAR,
                        arrowcolor=FG_SIDEBAR, borderwidth=0)
        style.map("Side.TCombobox", fieldbackground=[("readonly", BG_SIDEBAR2)])

        style.configure("Side.TSpinbox", fieldbackground=BG_SIDEBAR2,
                        background=BG_SIDEBAR2, foreground=FG_SIDEBAR,
                        arrowcolor=FG_SIDEBAR, borderwidth=0, insertcolor=FG_SIDEBAR)

        style.configure("Side.TCheckbutton", background=BG_SIDEBAR,
                        foreground=FG_SIDEBAR_MUTE, font=(KOR_FONT, 9))
        style.map("Side.TCheckbutton", background=[("active", BG_SIDEBAR)])

        style.configure("Vertical.TScrollbar", background=BG_CARD_ALT,
                        troughcolor=BG_ROOT, borderwidth=0, arrowsize=12)

        style.configure("Saju.Treeview", background=BG_CARD, fieldbackground=BG_CARD,
                        foreground=TEXT_MAIN, rowheight=30, borderwidth=0,
                        font=(KOR_FONT, 10))
        style.configure("Saju.Treeview.Heading", background=BG_CARD_ALT,
                        foreground=TEXT_MAIN, font=(KOR_FONT, 10, "bold"),
                        borderwidth=0, relief="flat")
        style.map("Saju.Treeview", background=[("selected", "#EBDFAE")],
                 foreground=[("selected", TEXT_MAIN)])
        style.layout("Saju.Treeview", [('Saju.Treeview.treearea', {'sticky': 'nswe'})])


    def _build_layout(self):
        self._build_header()

        body = tk.Frame(self, bg=BG_ROOT)
        body.pack(fill="both", expand=True)

        self._build_sidebar(body)

        right = tk.Frame(body, bg=BG_ROOT)
        right.pack(side="left", fill="both", expand=True)

        self.notebook = ttk.Notebook(right, style="TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=(14, 16), pady=(12, 0))

        page_v1 = self.page_v1 = tk.Frame(self.notebook, bg=BG_ROOT)
        page_v2 = self.page_v2 = tk.Frame(self.notebook, bg=BG_ROOT)

        self._build_capture_bar(page_v1, "v1")
        self._build_capture_bar(page_v2, "v2")

        self.tab_v1 = ScrollFrame(page_v1)
        self.tab_v2 = ScrollFrame(page_v2)
        self.tab_v1.pack(fill="both", expand=True)
        self.tab_v2.pack(fill="both", expand=True)

        self.notebook.add(page_v1, text="🀄  V1 사주")
        self.notebook.add(page_v2, text="📈  V2 사주")

        self._build_placeholder(self.tab_v1.body, "왼쪽에서 정보를 입력하고\n"
                                "'사주 계산하기'를 눌러주세요.")
        self._build_placeholder(self.tab_v2.body, "왼쪽에서 정보를 입력하고\n"
                                "'사주 계산하기'를 눌러주세요.")

        self._build_footer(right)

    def _build_capture_bar(self, parent, version):
        """탭 상단에 고정으로 붙는, 스크롤되지 않는 캡쳐 버튼 바.
        버튼 자체는 스크린샷 범위(캔버스 영역)에 포함되지 않습니다."""
        bar = tk.Frame(parent, bg=BG_ROOT)
        bar.pack(fill="x", padx=(14, 16), pady=(12, 0))
        btn = tk.Button(
            bar, text="🖼  이미지로 내보내기", font=(KOR_FONT, 9, "bold"),
            bg=BG_CARD_ALT, fg=TEXT_MAIN, activebackground=BG_CARD,
            relief="flat", padx=12, pady=6, cursor="hand2",
            command=lambda v=version: self._capture_tab_image(v),
        )
        btn.pack(side="right")
        ToolTip(btn, "ChatGPT · Gemini · Claude 같은 AI 챗봇에 첨부해서\n"
                    "이 결과에 대해 추가로 질문할 때 사용하세요.\n"
                    f"({version.upper()} 사주 탭 전체 내용을 이미지로 저장합니다)")


        btn_json = tk.Button(
            bar, text="{ }  JSON", font=(KOR_FONT, 9, "bold"),
            bg=BG_CARD_ALT, fg=TEXT_MAIN, activebackground=BG_CARD,
            relief="flat", padx=12, pady=6, cursor="hand2",
            command=lambda: self._export_file("json"),
        )
        btn_json.pack(side="right", padx=(0, 8))
        ToolTip(btn_json, "분석 결과 전체를 JSON 으로 저장합니다.\n"
                          "입력 옵션·밴드·계수 지문까지 함께 남으므로\n"
                          "나중에 '왜 결과가 달라졌지?'를 추적할 수 있습니다.")

        btn_txt = tk.Button(
            bar, text="📄  텍스트", font=(KOR_FONT, 9, "bold"),
            bg=BG_CARD_ALT, fg=TEXT_MAIN, activebackground=BG_CARD,
            relief="flat", padx=12, pady=6, cursor="hand2",
            command=lambda: self._export_file("txt"),
        )
        btn_txt.pack(side="right", padx=(0, 8))
        ToolTip(btn_txt, "사람이 읽는 리포트를 텍스트로 저장합니다.\n"
                         "대운·세운·化局 구간과 재현 정보가 포함됩니다.")

    def _export_file(self, kind):
        """현재 사주를 텍스트/JSON 으로 저장합니다 (#7)."""
        chart = getattr(self, "chart", None)
        if chart is None:
            messagebox.showinfo("내보내기", "먼저 사주를 계산해 주세요.")
            return
        a2 = getattr(self, "a2", None)
        stamp = chart.birth_local.strftime("%Y%m%d_%H%M")
        default = f"saju_{stamp}.{kind}"
        path = filedialog.asksaveasfilename(
            defaultextension=f".{kind}",
            initialfile=default,
            filetypes=([("JSON 파일", "*.json")] if kind == "json"
                       else [("텍스트 파일", "*.txt")]) + [("모든 파일", "*.*")])
        if not path:
            return
        try:
            if kind == "json":
                export_json(chart, path=path, a2=a2)
            else:
                export_text(chart, path=path, a2=a2)
        except Exception as e:
            messagebox.showerror("내보내기 실패", f"{type(e).__name__}: {e}")
            return
        self._show_export_done_dialog(path)

    def _show_export_done_dialog(self, path):
        """저장 완료 안내 + '바로 실행' 버튼이 있는 작은 모달."""
        dlg = tk.Toplevel(self)
        dlg.title("내보내기 완료")
        dlg.configure(bg=BG_CARD)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        pad = tk.Frame(dlg, bg=BG_CARD)
        pad.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(pad, text="저장이 완료됐습니다.", bg=BG_CARD, fg=TEXT_MAIN,
                 font=(KOR_FONT, 11, "bold")).pack(anchor="w")
        tk.Label(pad, text=path, bg=BG_CARD, fg=TEXT_MUTE,
                 font=(KOR_FONT, 9), wraplength=420, justify="left")\
            .pack(anchor="w", pady=(6, 16))

        btn_row = tk.Frame(pad, bg=BG_CARD)
        btn_row.pack(fill="x")

        def _run_and_close():
            dlg.destroy()
            self._open_file_external(path)

        tk.Button(btn_row, text="닫기", font=(KOR_FONT, 9),
                  bg=BG_CARD_ALT, fg=TEXT_MAIN, activebackground=BG_CARD_ALT,
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  command=dlg.destroy).pack(side="right")
        tk.Button(btn_row, text="바로 실행", font=(KOR_FONT, 9, "bold"),
                  bg=ACCENT, fg="#2A2306", activebackground=ACCENT_DARK,
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  command=_run_and_close).pack(side="right", padx=(0, 8))

        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _open_file_external(self, path):
        """저장된 파일을 OS 기본 프로그램으로 엽니다."""
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("실행 실패",
                                 f"파일을 여는 데 실패했습니다:\n{type(e).__name__}: {e}\n\n"
                                 f"경로: {path}")

    def _build_placeholder(self, parent, text):
        tk.Label(parent, text=text, bg=BG_ROOT, fg=TEXT_MUTE,
                 font=(KOR_FONT, 12), justify="center").pack(expand=True, pady=80)

    def _build_header(self):
        head = tk.Frame(self, bg=BG_SIDEBAR, height=64)
        head.pack(fill="x")
        head.pack_propagate(False)
        cv = tk.Canvas(head, width=44, height=44, bg=BG_SIDEBAR, highlightthickness=0)
        cv.pack(side="left", padx=(18, 8), pady=10)
        draw_taegeuk(cv, 22, 22, 18)
        title_box = tk.Frame(head, bg=BG_SIDEBAR)
        title_box.pack(side="left", pady=8)
        tk.Label(title_box, text="사주+  명리 분석기", bg=BG_SIDEBAR, fg=FG_SIDEBAR,
                 font=(KOR_FONT, 15, "bold")).pack(anchor="w")
        tk.Label(title_box, text="사주 원국 · 오행 · 용신 · 대운 흐름",
                 bg=BG_SIDEBAR, fg=FG_SIDEBAR_MUTE, font=(KOR_FONT, 9)).pack(anchor="w")

    def _build_footer(self, parent):
        foot = tk.Label(parent, text=DISCLAIMER.replace("\n", " "), bg=BG_ROOT,
                        fg=TEXT_MUTE, font=(KOR_FONT, 8), wraplength=1100, justify="left")
        foot.pack(fill="x", padx=18, pady=(6, 10))


    def _build_sidebar(self, parent):
        side = tk.Frame(parent, bg=BG_SIDEBAR, width=330)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        sf = ScrollFrame(side, bg=BG_SIDEBAR)
        sf.pack(fill="both", expand=True)
        f = sf.body
        f.configure(bg=BG_SIDEBAR)
        PAD = dict(padx=20, pady=(14, 4))

        def label(text):
            tk.Label(f, text=text, bg=BG_SIDEBAR, fg=FG_SIDEBAR_MUTE,
                     font=(KOR_FONT, 9, "bold")).pack(anchor="w", **PAD)


        label("성별")
        gwrap = tk.Frame(f, bg=BG_SIDEBAR)
        gwrap.pack(fill="x", padx=20)
        self.gender_var = tk.StringVar(value="남")
        self.btn_male = self._toggle_btn(gwrap, "남성", self.gender_var, "남")
        self.btn_female = self._toggle_btn(gwrap, "여성", self.gender_var, "여")
        self.btn_male.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.btn_female.pack(side="left", fill="x", expand=True, padx=(4, 0))


        label("생년월일")
        dwrap = tk.Frame(f, bg=BG_SIDEBAR)
        dwrap.pack(fill="x", padx=20)
        self.year_var = tk.StringVar(value="1978")
        self.month_var = tk.StringVar(value="4")
        self.day_var = tk.StringVar(value="19")
        self._spin(dwrap, self.year_var, 1900, 2035, 5).pack(side="left")
        tk.Label(dwrap, text="년", bg=BG_SIDEBAR, fg=FG_SIDEBAR_MUTE).pack(side="left", padx=3)
        self._spin(dwrap, self.month_var, 1, 12, 3).pack(side="left")
        tk.Label(dwrap, text="월", bg=BG_SIDEBAR, fg=FG_SIDEBAR_MUTE).pack(side="left", padx=3)
        self._spin(dwrap, self.day_var, 1, 31, 3).pack(side="left")
        tk.Label(dwrap, text="일", bg=BG_SIDEBAR, fg=FG_SIDEBAR_MUTE).pack(side="left", padx=3)


        label("태어난 시각")
        twrap = tk.Frame(f, bg=BG_SIDEBAR)
        twrap.pack(fill="x", padx=20)
        self.hour_var = tk.StringVar(value="23")
        self.min_var = tk.StringVar(value="10")
        self.hour_spin = self._spin(twrap, self.hour_var, 0, 23, 3)
        self.hour_spin.pack(side="left")
        tk.Label(twrap, text="시", bg=BG_SIDEBAR, fg=FG_SIDEBAR_MUTE).pack(side="left", padx=3)
        self.min_spin = self._spin(twrap, self.min_var, 0, 59, 3)
        self.min_spin.pack(side="left")
        tk.Label(twrap, text="분", bg=BG_SIDEBAR, fg=FG_SIDEBAR_MUTE).pack(side="left", padx=3)

        self.unknown_time = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="태어난 시각을 몰라요 (정오 12:00으로 계산)",
                        variable=self.unknown_time, style="Side.TCheckbutton",
                        command=self._toggle_time).pack(anchor="w", padx=20, pady=(4, 0))


        label("출생지")
        self.city_var = tk.StringVar(value="대구")

        REGION_GROUPS = [
            ("수도권", ["서울", "인천", "경기도"]),
            ("충청·강원", ["대전", "세종", "충청북도", "충청남도", "강원도"]),
            ("호남", ["광주", "전라북도", "전라남도"]),
            ("영남", ["부산", "대구", "울산", "경상북도", "경상남도"]),
            ("제주·울릉", ["제주도", "울릉도"]),
        ]
        self.city_buttons = []
        region_wrap = tk.Frame(f, bg=BG_SIDEBAR)
        region_wrap.pack(fill="x", padx=20)
        for gname, cities in REGION_GROUPS:
            tk.Label(region_wrap, text=gname, bg=BG_SIDEBAR, fg=FG_SIDEBAR_MUTE,
                     font=(KOR_FONT, 8, "bold")).pack(anchor="w", pady=(8, 3))
            grow = tk.Frame(region_wrap, bg=BG_SIDEBAR)
            grow.pack(fill="x")
            for i, cname in enumerate(cities):
                btn = self._toggle_btn(grow, cname, self.city_var, cname, small=True)
                btn.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 4, 0))
                grow.grid_columnconfigure(i, weight=1)
                self.city_buttons.append(btn)

        tk.Label(f, text="울릉도는 경상북도 본토와 경도 차이가 커서 "
                        "따로 두었습니다. 그 외 시·군은 소속 시/도로 계산합니다.",
                 bg=BG_SIDEBAR, fg=FG_SIDEBAR_MUTE, font=(KOR_FONT, 8),
                 wraplength=260, justify="left").pack(anchor="w", padx=20, pady=(8, 0))


        label("계산 옵션")
        opt_card = tk.Frame(f, bg=BG_SIDEBAR2)
        opt_card.pack(fill="x", padx=20, pady=(0, 4))


        jrow = tk.Frame(opt_card, bg=BG_SIDEBAR2)
        jrow.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(jrow, text="23시대 출생자 일주 기준", bg=BG_SIDEBAR2, fg=FG_SIDEBAR_MUTE,
                 font=(KOR_FONT, 8, "bold")).pack(anchor="w")
        jbtns = tk.Frame(opt_card, bg=BG_SIDEBAR2)
        jbtns.pack(fill="x", padx=10, pady=(0, 10))
        self.jasi_var = tk.StringVar(value="야자시")
        self.btn_jasi1 = self._toggle_btn(jbtns, "야자시", self.jasi_var, "야자시", small=True)
        self.btn_jasi2 = self._toggle_btn(jbtns, "정자시", self.jasi_var, "정자시", small=True)
        self.btn_jasi1.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.btn_jasi2.pack(side="left", fill="x", expand=True, padx=(4, 0))
        ToolTip(self.btn_jasi1, OPT_HELP["야자시"])
        ToolTip(self.btn_jasi2, OPT_HELP["정자시"])

        sep1 = tk.Frame(opt_card, bg="#3A4066", height=1)
        sep1.pack(fill="x", padx=10)


        self.apply_lon = tk.BooleanVar(value=True)
        self.apply_eot = tk.BooleanVar(value=False)
        self.btn_lon = self._onoff_btn(opt_card, "진태양시 경도 보정", self.apply_lon)
        self.btn_lon.pack(fill="x", padx=10, pady=(10, 4))
        ToolTip(self.btn_lon, OPT_HELP["진태양시"])

        self.btn_eot = self._onoff_btn(opt_card, "균시차(均時差) 보정", self.apply_eot)
        self.btn_eot.pack(fill="x", padx=10, pady=(4, 10))
        ToolTip(self.btn_eot, OPT_HELP["균시차"])


        btn_wrap = tk.Frame(f, bg=BG_SIDEBAR)
        btn_wrap.pack(fill="x", padx=20, pady=(22, 6))
        self.calc_btn = tk.Button(
            btn_wrap, text="🔮  사주 계산하기", command=self.on_calculate,
            bg=ACCENT, fg="#2A2306", activebackground=ACCENT_DARK,
            activeforeground="#2A2306", font=(KOR_FONT, 12, "bold"),
            relief="flat", cursor="hand2", pady=10)
        self.calc_btn.pack(fill="x")

        tk.Button(f, text="예시 값 채우기 (1990-05-15 14:30 서울 남)",
                 command=self._fill_example, bg=BG_SIDEBAR2, fg=FG_SIDEBAR_MUTE,
                 activebackground=BG_SIDEBAR2, relief="flat", font=(KOR_FONT, 8),
                 cursor="hand2").pack(fill="x", padx=20, pady=(0, 10))

        self.status_label = tk.Label(f, text="", bg=BG_SIDEBAR, fg="#E27878",
                                     font=(KOR_FONT, 9), wraplength=280, justify="left")
        self.status_label.pack(fill="x", padx=20, pady=(0, 20))

    def _entry(self, master):
        e = tk.Entry(master, bg=BG_SIDEBAR2, fg=FG_SIDEBAR, insertbackground=FG_SIDEBAR,
                     relief="flat", font=(KOR_FONT, 10))
        return e

    def _spin(self, master, var, lo, hi, width):
        return ttk.Spinbox(master, from_=lo, to=hi, textvariable=var, width=width,
                           style="Side.TSpinbox", justify="center", font=(KOR_FONT, 10))

    def _toggle_btn(self, master, text, var, value, small=False):
        b = tk.Button(master, text=text, font=(KOR_FONT, 9 if small else 10, "bold"),
                     relief="flat", cursor="hand2", pady=5 if small else 6)

        def refresh(*_):
            active = var.get() == value
            b.configure(bg=ACCENT if active else BG_SIDEBAR2,
                       fg="#2A2306" if active else FG_SIDEBAR_MUTE,
                       activebackground=ACCENT_DARK if active else BG_SIDEBAR2)

        def on_click():
            var.set(value)
            refresh()

        b.configure(command=on_click)
        refresh()
        var.trace_add("write", refresh)
        return b

    def _onoff_btn(self, master, text, var):
        """단일 불리언(on/off)을 나타내는 버튼. 클릭할 때마다 켜짐/꺼짐이 바뀝니다."""
        b = tk.Button(master, font=(KOR_FONT, 9, "bold"), relief="flat",
                     cursor="hand2", pady=6, anchor="w", justify="left")

        def refresh(*_):
            on = var.get()
            state_txt = "●  " + text + "  —  사용함" if on else "○  " + text + "  —  사용 안 함"
            b.configure(text=state_txt,
                       bg=ACCENT if on else BG_SIDEBAR2,
                       fg="#2A2306" if on else FG_SIDEBAR_MUTE,
                       activebackground=ACCENT_DARK if on else BG_SIDEBAR2)

        def on_click():
            var.set(not var.get())
            refresh()

        b.configure(command=on_click)
        refresh()
        var.trace_add("write", refresh)
        return b

    def _toggle_time(self):
        state = "disabled" if self.unknown_time.get() else "normal"
        self.hour_spin.configure(state=state)
        self.min_spin.configure(state=state)
        if self.unknown_time.get():
            self.hour_var.set("12")
            self.min_var.set("00")

    def _fill_example(self):
        self.gender_var.set("남")
        self.year_var.set("1990"); self.month_var.set("5"); self.day_var.set("15")
        self.unknown_time.set(False); self._toggle_time()
        self.hour_var.set("14"); self.min_var.set("30")
        self.city_var.set("서울")
        self.jasi_var.set("야자시")


    def on_calculate(self):
        self.status_label.config(text="")
        try:
            y = int(self.year_var.get()); mo = int(self.month_var.get()); d = int(self.day_var.get())
            h = int(self.hour_var.get()); mi = int(self.min_var.get())
            datetime(y, mo, d)
        except ValueError:
            self.status_label.config(text="생년월일이 올바르지 않습니다. 날짜를 다시 확인해주세요.")
            return

        kwargs = dict(
            birth_year=y, birth_month=mo, birth_day=d, birth_hour=h, birth_minute=mi,
            is_male=(self.gender_var.get() == "남"),
            place=self.city_var.get().strip() or "서울",
            jasi_school=self.jasi_var.get(),
            apply_longitude=self.apply_lon.get(),
            apply_eot=self.apply_eot.get(),
        )

        self.calc_btn.configure(state="disabled", text="⏳  계산 중...")
        threading.Thread(target=self._compute, args=(kwargs,), daemon=True).start()

    def _compute(self, kwargs):
        try:
            chart = build_chart(**kwargs)
            self._log_usage(chart)
            a1 = analyze(chart)
            s1 = score_all_daeun(a1)
            a2 = analyze_v2(chart)
            s2 = score_all_daeun_v2(a2)
            self._queue.put(("ok", chart, a1, s1, a2, s2))
        except ValueError as e:
            self._queue.put(("error", str(e)))
        except Exception:
            self._queue.put(("error", "예상치 못한 오류가 발생했습니다.\n\n" + traceback.format_exc()))

    @staticmethod
    def _lookup_public_ip():
        """이 컴퓨터의 공인 IP 를 짧게 조회합니다. 실패하면 빈 문자열.

        Google Apps Script 의 doPost(e) 는 호출자의 IP 를 알려주지
        않으므로, 로그에 IP 를 남기려면 이 프로그램이 직접 외부 서비스에
        물어보는 수밖에 없습니다. 여기서 실패해도(오프라인, 서비스 장애
        등) 예외를 삼켜 계산 흐름에는 아무 영향이 없게 합니다.
        """
        try:
            with urllib.request.urlopen(
                    IP_LOOKUP_URL, timeout=IP_LOOKUP_TIMEOUT_SEC) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("ip", "")
        except Exception:
            return ""

    def _log_usage(self, chart):
        """[접속일시(KST), 성별, 연도, 월, 일, 시, 장소, IP] 한 줄을
        구글시트 'log' 탭에 기록합니다.

        LOG_WEBHOOK_URL 이 비어 있으면 아무 것도 하지 않습니다.
        이미 백그라운드 스레드(_compute) 안에서 호출되므로 여기서 블로킹
        네트워크 호출을 해도 GUI 는 멈추지 않습니다. 어떤 이유로든 실패해도
        (오프라인, URL 미설정, 응답 지연 등) 절대 계산 자체를 막지 않도록
        예외를 전부 삼킵니다.

        접속 시각은 이 프로그램을 실행 중인 컴퓨터의 로컬 시계가 아니라,
        항상 'Asia/Seoul' 기준(KST)으로 남깁니다. 컴퓨터 시계가 해외
        표준시로 맞춰져 있어도 로그 시각이 뒤섞이지 않도록 하기 위함입니다.
        """
        if not LOG_WEBHOOK_URL:
            return
        try:
            access_kst = datetime.now(ZoneInfo("Asia/Seoul"))
            client_ip = self._lookup_public_ip() if LOG_INCLUDE_IP else ""
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
            pass

    def _poll_queue(self):
        try:
            while True:
                item = self._queue.get_nowait()
                if item[0] == "ok":
                    _, chart, a1, s1, a2, s2 = item
                    self.chart, self.a1, self.s1, self.a2, self.s2 = chart, a1, s1, a2, s2
                    self.today_age = date.today().year - chart.birth_local.year + 1
                    self._render_all()
                    self.calc_btn.configure(state="normal", text="🔮  사주 계산하기")
                else:
                    self.calc_btn.configure(state="normal", text="🔮  사주 계산하기")
                    self.status_label.config(text=item[1])
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)


    def _capture_tab_image(self, version):
        if not _PIL_AVAILABLE:
            messagebox.showwarning(
                "이미지 저장 불가",
                "이미지 캡쳐 기능을 사용하려면 Pillow 패키지가 필요합니다.\n\n"
                "터미널(명령 프롬프트)에서 아래 명령을 실행한 뒤\n"
                "앱을 다시 시작해주세요:\n\n"
                "    pip install pillow")
            return

        if self.chart is None:
            messagebox.showwarning("이미지 저장 불가",
                                   "먼저 왼쪽에서 정보를 입력하고 '사주 계산하기'를 눌러주세요.")
            return

        sf = self.tab_v1 if version == "v1" else self.tab_v2
        page = self.page_v1 if version == "v1" else self.page_v2
        canvas = sf.canvas

        try:
            self.notebook.select(page)
            self.lift()
            self.update_idletasks()
            self.update()

            bbox = canvas.bbox("all")
            if not bbox:
                messagebox.showwarning("이미지 저장 불가", "캡쳐할 내용이 없습니다.")
                return

            content_h = bbox[3] - bbox[1]
            vp_w = canvas.winfo_width()
            vp_h = canvas.winfo_height()
            orig_frac = canvas.yview()[0]


            if content_h <= vp_h:
                offsets = [0]
            else:
                offsets = list(range(0, content_h - vp_h, vp_h)) + [content_h - vp_h]

            full_img = Image.new("RGB", (vp_w, max(content_h, vp_h)), "white")
            for off in offsets:
                frac = 0 if content_h <= vp_h else off / (content_h - vp_h)
                canvas.yview_moveto(max(0.0, min(1.0, frac)))
                self.update_idletasks()
                self.update()
                x0 = canvas.winfo_rootx()
                y0 = canvas.winfo_rooty()
                shot = ImageGrab.grab(bbox=(x0, y0, x0 + vp_w, y0 + vp_h))
                full_img.paste(shot, (0, off))

            canvas.yview_moveto(orig_frac)
            self.update_idletasks()

            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(downloads, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"사주_{version.upper()}_{ts}.png"
            path = os.path.join(downloads, fname)
            full_img.save(path)

            messagebox.showinfo(
                "저장 완료",
                f"이미지가 저장되었습니다.\n\n{path}\n\n"
                "ChatGPT · Gemini · Claude 같은 AI 챗봇에 이 파일을 첨부해서\n"
                "결과에 대해 추가로 질문해보세요.")
        except Exception as e:
            messagebox.showerror("캡쳐 오류", f"이미지 캡쳐 중 오류가 발생했습니다.\n\n{e}")


    def _render_all(self):
        self._render_version("v1")
        self._render_version("v2")


    def _render_version(self, version):
        """version: 'v1' 또는 'v2'. 두 탭이 같은 구조(원국 → 대운 → 비교 코멘트)를
        각자의 판정 기준으로 채우도록 하나의 함수로 처리합니다."""
        is_v1 = (version == "v1")
        sf = self.tab_v1 if is_v1 else self.tab_v2
        sf.clear()
        body = sf.body
        chart = self.chart
        a = self.a1 if is_v1 else self.a2
        s_own = self.s1 if is_v1 else self.s2


        self._build_version_intro(body, version)


        info, iin = card(body)
        info.pack(fill="x", pady=(0, 14))
        row = tk.Frame(iin, bg=BG_CARD)
        row.pack(fill="x")
        tk.Label(row, text=f"{chart.birth_local:%Y년 %m월 %d일 %H시 %M분}"
                          f"  ({'남성' if chart.is_male else '여성'})",
                 bg=BG_CARD, fg=TEXT_MAIN, font=(KOR_FONT, 13, "bold")).pack(side="left")
        tk.Label(row, text=f"  ·  {chart.place.name} (동경 {chart.place.longitude:.2f}°)",
                 bg=BG_CARD, fg=TEXT_MUTE, font=(KOR_FONT, 10)).pack(side="left")
        sub = tk.Label(iin, bg=BG_CARD, fg=TEXT_MUTE, font=(KOR_FONT, 9), justify="left",
                       text=f"진태양시 {chart.solar_time:%Y-%m-%d %H:%M}   |   "
                            f"표준시 UTC{chart.utc_offset:+g}"
                            + ("  · 서머타임 적용" if chart.is_dst else "")
                            + f"   |   자시 기준: {chart.jasi_school}설")
        sub.pack(anchor="w", pady=(4, 0))

        tk.Label(iin, text="".join(f"{h:^16}" for h in ["시주", "일주", "월주", "년주"]),
                 bg=BG_CARD, fg=TEXT_MUTE, font=(KOR_FONT, 9)).pack(anchor="w", pady=(10, 0))
        order = [chart.hour, chart.day, chart.month, chart.year]
        pillar_row = tk.Frame(iin, bg=BG_CARD)
        pillar_row.pack(anchor="w")
        for p in order:
            tk.Label(pillar_row, text=p.hanja, bg=BG_CARD, fg=TEXT_MAIN,
                     font=(KOR_FONT, 15, "bold"), width=8, justify="center").pack(side="left")

        if chart.warnings:
            wf = tk.Frame(iin, bg=WARN_BG)
            wf.pack(fill="x", pady=(10, 0))
            for w in chart.warnings:
                tk.Label(wf, text="⚠ " + w, bg=WARN_BG, fg=WARN_FG, wraplength=980,
                         justify="left", font=(KOR_FONT, 9), padx=10, pady=4).pack(anchor="w")


        sinsal_list = detect_sinsal(chart)
        if sinsal_list:
            seen_names = []
            for s in sinsal_list:
                if s["name"] not in seen_names:
                    seen_names.append(s["name"])
            sf_row = tk.Frame(iin, bg=BG_CARD)
            sf_row.pack(fill="x", pady=(12, 0))
            tk.Label(sf_row, text="신살(神殺)", bg=BG_CARD, fg=TEXT_MAIN,
                     font=(KOR_FONT, 9, "bold")).pack(side="left", padx=(0, 8))
            for name in seen_names:
                chip = tk.Label(sf_row, text=name, bg="#EDE0C8", fg="#7A5B1E",
                                font=(KOR_FONT, 9, "bold"), padx=8, pady=2)
                chip.pack(side="left", padx=(0, 6))
            sinsal_notes = "\n".join(
                f"· [{s['name']} · {s['basis']}] {s['note']}" for s in sinsal_list)
            sn_lbl = tk.Label(iin, text=sinsal_notes, bg=BG_CARD, fg=TEXT_MUTE,
                              font=(KOR_FONT, 8), wraplength=1000, justify="left")
            sn_lbl.pack(anchor="w", pady=(6, 0), fill="x")
            info.bind("<Configure>", lambda e, lbl=sn_lbl:
                      lbl.configure(wraplength=max(200, e.width - 40)), add="+")
            tk.Label(iin, text="신살은 억부·격국과는 다른 갈래의 전통 도구로, "
                              "유파에 따라 판정 기준과 해석이 크게 갈립니다. "
                              "참고용으로만 보세요.",
                     bg=BG_CARD, fg=TEXT_MUTE, font=(KOR_FONT, 8)).pack(anchor="w", pady=(6, 0))


        mid = tk.Frame(body, bg=BG_ROOT)
        mid.pack(fill="x")

        ecard, ein = card(mid)
        ecard.pack(side="left", fill="both", expand=True, padx=(0, 8))
        h3(ein, "오행 분포").pack(anchor="w", pady=(0, 8))
        erow = tk.Frame(ein, bg=BG_CARD)
        erow.pack(fill="x")
        cnt = chart.ohaeng_count()
        cv = tk.Canvas(erow, width=170, height=170, bg=BG_CARD, highlightthickness=0)
        cv.pack(side="left", padx=(0, 16))
        if sum(cnt.values()) > 0:
            draw_donut(cv, 85, 85, 78, 44, cnt, ELEM_COLOR)
        cv.create_text(85, 85, text=f"{sum(cnt.values()):.0f}자", font=(KOR_FONT, 11, "bold"),
                       fill=TEXT_MAIN)
        bars = tk.Frame(erow, bg=BG_CARD)
        bars.pack(side="left", fill="both", expand=True)
        maxv = max(cnt.values()) or 1
        for e in "목화토금수":
            tag = "도움" if e in a.yongsin else ("부담" if e in a.gisin else "")
            StatBar(bars, e, cnt[e], maxv, suffix="개", tag=tag).pack(fill="x", pady=1)

        dcard, din = card(mid)
        dcard.pack(side="left", fill="both", expand=True, padx=(8, 0))
        h3(din, "나는 어떤 사람인가").pack(anchor="w", pady=(0, 8))
        nick, desc = ILGAN_DESC[chart.day_gan]
        delem = chart.day_ohaeng
        head_row = tk.Frame(din, bg=BG_CARD)
        head_row.pack(fill="x")
        tk.Label(head_row, text=GAN_H[chart.day_gan], bg=ELEM_COLOR_SOFT[delem],
                 fg=ELEM_COLOR[delem], font=(KOR_FONT, 26, "bold"), width=2)\
            .pack(side="left", padx=(0, 10))
        tvbox = tk.Frame(head_row, bg=BG_CARD)
        tvbox.pack(side="left", fill="x", expand=True)
        tk.Label(tvbox, text=f"{nick}  ·  {delem} 기운", bg=BG_CARD, fg=TEXT_MAIN,
                 font=(KOR_FONT, 12, "bold")).pack(anchor="w")
        desc_lbl = tk.Label(tvbox, text=desc, bg=BG_CARD, fg=TEXT_MUTE, font=(KOR_FONT, 9),
                           wraplength=260, justify="left")
        desc_lbl.pack(anchor="w", pady=(2, 0), fill="x")
        dcard.bind("<Configure>", lambda e, lbl=desc_lbl:
                  lbl.configure(wraplength=max(160, e.width - 100)))
        tk.Label(din, text=f"{version.upper()} 기준 강약: {a.strength.label}  "
                          f"({a.strength.ratio:.0%})",
                 bg=BG_CARD, fg=ELEM_COLOR.get(delem, TEXT_MAIN),
                 font=(KOR_FONT, 10, "bold")).pack(anchor="w", pady=(12, 0))


        if a.yongsin:
            acard, ain = card(body)
            acard.pack(fill="x", pady=(14, 0))
            h3(ain, "생활 속 처방").pack(anchor="w", pady=(0, 10))
            e0 = a.yongsin[0]
            d_, col, thing, _organ_self = OHAENG_ADVICE[e0]
            gisin_organ = OHAENG_ADVICE[a.gisin[0]][3] if a.gisin else "-"
            grid = tk.Frame(ain, bg=BG_CARD)
            grid.pack(fill="x")
            for i, (k, v) in enumerate([("방위", d_), ("색상", col), ("가까이할 것", thing),
                                        ("건강 주의", gisin_organ)]):
                box = tk.Frame(grid, bg=ELEM_COLOR_SOFT[e0])
                box.grid(row=0, column=i, sticky="nsew", padx=4)
                grid.grid_columnconfigure(i, weight=1)
                tk.Label(box, text=k, bg=ELEM_COLOR_SOFT[e0], fg=ELEM_COLOR[e0],
                         font=(KOR_FONT, 9, "bold")).pack(pady=(10, 2))
                tk.Label(box, text=v, bg=ELEM_COLOR_SOFT[e0], fg=TEXT_MAIN,
                         font=(KOR_FONT, 10, "bold"), wraplength=180)\
                    .pack(pady=(0, 10), padx=6)
            tk.Label(ain, text="이런 처방은 마음가짐을 다잡는 장치에 가깝습니다. "
                              "실제 결과를 바꾸는 수단으로 여기지는 마세요.",
                     bg=BG_CARD, fg=TEXT_MUTE, font=(KOR_FONT, 8)).pack(anchor="w", pady=(10, 0))


        gk = getattr(a, "gyeokguk", None)
        if gk:
            VERDICT_COLOR = {"일치": "#2E7D32", "상충": "#B03A2E",
                             "부분일치": "#8A6D00", "무관": TEXT_MUTE}
            gcard, gin = card(body)
            gcard.pack(fill="x", pady=(14, 0))
            head = tk.Frame(gin, bg=BG_CARD)
            head.pack(fill="x")
            h3(head, "격국 교차검증 — 억부 외 다른 유파와 비교").pack(side="left")
            tk.Label(head, text=f"{gk['gyeok_name']} · {gk['verdict']}",
                     bg=BG_CARD, fg=VERDICT_COLOR.get(gk["verdict"], TEXT_MAIN),
                     font=(KOR_FONT, 10, "bold")).pack(side="right")
            gdesc = tk.Label(gin, text=gk["note"], bg=BG_CARD, fg=TEXT_MUTE,
                             font=(KOR_FONT, 9), wraplength=1000, justify="left")
            gdesc.pack(anchor="w", pady=(8, 0), fill="x")
            gcard.bind("<Configure>", lambda e, lbl=gdesc:
                      lbl.configure(wraplength=max(200, e.width - 40)))
            tk.Label(gin, text="억부용신과 격국론은 서로 다른 이론 틀입니다. "
                              "'상충'으로 표시된 경우는 두 유파의 결론이 갈리는 "
                              "구간이니 참고만 하고 단정하지는 마세요.",
                     bg=BG_CARD, fg=TEXT_MUTE, font=(KOR_FONT, 8)).pack(anchor="w", pady=(8, 0))


        age = self.today_age
        tcard, tin = card(body)
        tcard.pack(fill="both", expand=True, pady=(14, 14))
        h3(tin, f"{version.upper()} 대운 흐름 (행을 클릭하면 상세 근거가 보입니다)")\
            .pack(anchor="w", pady=(0, 8))

        has_rank = bool(s_own) and ("rank" in s_own[0])
        if has_rank:
            cols = ("age", "ganji", "score", "grade", "rank", "note")


            heads = ["나이", "간지", "절대점수", "절대등급", "상대순위", "비고"]
        else:
            cols = ("age", "ganji", "score", "grade", "note")
            heads = ["나이", "간지", "절대점수", "절대등급", "비고"]
        tv = ttk.Treeview(tin, columns=cols, show="headings", style="Saju.Treeview", height=9)
        for c, htext in zip(cols, heads):
            tv.heading(c, text=htext)
            tv.column(c, anchor="center", width=110 if c != "note" else 160)
        tv.pack(fill="both", expand=True)
        tv.tag_configure("current", background="#F3E6B2")
        if has_rank:
            body_note = (
                " ※ [어려움] 은 집중과 노력을, [좋음] 은 안정과 휴식을 의미함"
            )
            n_sat = s_own[0].get("n_saturated", 0) if s_own else 0
            if n_sat >= 2:
                body_note += (
                    f"\n※ 이 사주는 {n_sat}개 구간의 절대점수가 한계(±1)에 "
                    f"도달해 등급으로는 서로 구분되지 않습니다. 그 구간들은 "
                    f"상대순위로만 우열을 볼 수 있습니다."
                )
            h3(tin, body_note).pack(anchor="w", pady=(6, 0))

        for i, x in enumerate(s_own):
            is_cur = x["age"] <= age < x["age"] + 10
            note = "▶ 현재" if is_cur else ""
            tags = ["current"] if is_cur else []
            values = [f"{x['age']}~{x['age']+9}세", x["pillar"].hanja,
                      f"{x['score']:+.2f}", x["grade"]]
            if has_rank:
                values.append(f"#{x['rank']}")
            values.append(note)
            tv.insert("", "end", iid=str(i), values=tuple(values), tags=tags)

        detail_holder = {}

        def _on_select(event, tv=tv, s_own=s_own, holder=detail_holder, a=a):
            sel = tv.selection()
            if not sel:
                return
            self._show_daeun_detail_single(holder["frame"], s_own[int(sel[0])], a)

        tv.bind("<<TreeviewSelect>>", _on_select)

        dcard, ddetail = card(body)
        dcard.pack(fill="both", expand=True)
        detail_holder["frame"] = ddetail
        h3(ddetail, "대운을 선택하면 상세 근거가 여기 표시됩니다.").pack(anchor="w")


        self._build_comparison_comment(body, version)

    def _build_version_intro(self, parent, version):
        """탭 상단에 V1/V2가 각각 무엇을 의미하는지 설명하는 고정 카드."""
        icard, iin = card(parent)
        icard.pack(fill="x", pady=(0, 14))
        if version == "v1":
            title = "V1 — 기본 억부(抑扶) 판정"
            desc = ("V1은 전통 명리학의 가장 기본이 되는 억부 판정 방식입니다. "
                    "사주에 오행이 몇 개씩 있는지를 단순히 세어 일간의 힘이 "
                    "강한지 약한지를 가르고, 그에 따라 신강/신약과 용신을 정합니다. "
                    "계산 방식이 단순해서 결과를 이해하고 검증하기 쉽지만, 지장간·통근·"
                    "계절의 힘 같은 세부 요소는 반영하지 않기 때문에 정교함은 다소 떨어질 수 있습니다.")
        else:
            title = "V2 — 강화 판정 (지장간·통근·계절·종격 반영)"
            desc = ("V2는 V1의 기본 억부 판정에 지장간(地藏干), 통근(通根), 계절의 힘, "
                    "종격(從格) 여부 같은 명리학의 세부 이론을 추가로 반영한 강화 버전입니다. "
                    "같은 오행이라도 뿌리가 있는지, 태어난 계절과 기운이 맞는지에 따라 "
                    "실제 영향력을 다르게 계산하기 때문에 V1보다 더 정교한 판정을 시도합니다. "
                    "다만 반영하는 요소가 많아지는 만큼, 유파에 따라 해석이 갈릴 수 있는 "
                    "여지도 V1보다 더 큽니다.")
        tk.Label(iin, text=title, bg=BG_CARD, fg=TEXT_MAIN,
                 font=(KOR_FONT, 12, "bold")).pack(anchor="w")
        desc_lbl = tk.Label(iin, text=desc, bg=BG_CARD, fg=TEXT_MUTE, font=(KOR_FONT, 9),
                            wraplength=1000, justify="left")
        desc_lbl.pack(anchor="w", pady=(6, 0), fill="x")
        icard.bind("<Configure>", lambda e, lbl=desc_lbl:
                  lbl.configure(wraplength=max(200, e.width - 40)))

    def _build_comparison_comment(self, parent, version):
        """V1·V2를 표가 아니라 문장(코멘트)으로 비교해서 보여줍니다."""
        a1, a2 = self.a1, self.a2
        s1, s2 = self.s1, self.s2

        ccard, cin = card(parent)
        ccard.pack(fill="x", pady=(0, 4))
        other = "V2" if version == "v1" else "V1"
        h3(cin, f"{version.upper()} ↔ {other} 비교 코멘트").pack(anchor="w", pady=(0, 8))

        lines = []


        if a1.strength.label == a2.strength.label:
            lines.append(f"강약 판정은 V1({a1.strength.ratio:.0%})과 V2({a2.strength.ratio:.0%}) "
                         f"모두 '{a1.strength.label}'으로 같은 결론을 냅니다.")
        else:
            lines.append(f"강약 판정이 서로 다릅니다 — V1은 '{a1.strength.label}'"
                         f"({a1.strength.ratio:.0%}), V2는 '{a2.strength.label}'"
                         f"({a2.strength.ratio:.0%})으로 판정합니다.")
        if a2.special:
            lines.append(f"V2는 '{a2.special['name']}' 격으로 판정되어, "
                         f"일반적인 억부 판정과는 결론이 반전됩니다.")


        y1, y2 = set(a1.yongsin), set(a2.yongsin)
        if y1 == y2:
            lines.append(f"도움이 되는 기운(용신)도 V1·V2가 "
                         f"{'·'.join(sorted(y1)) or '뚜렷하지 않음'}으로 동일합니다.")
        else:
            lines.append(f"도움이 되는 기운(용신)은 V1이 {'·'.join(a1.yongsin) or '뚜렷하지 않음'}, "
                         f"V2가 {'·'.join(a2.yongsin) or '뚜렷하지 않음'}으로 차이가 있습니다.")


        flips = []
        for x, y in zip(s1, s2):
            if (x["score"] > 0.2) != (y["score"] > 0.2) and abs(x["score"] - y["score"]) > 0.3:
                flips.append(f"{x['age']}~{x['age']+9}세")
        if flips:
            lines.append(f"대운 길흉 판정이 V1과 V2 사이에서 뒤집히는 구간은 "
                         f"{', '.join(flips)} 총 {len(flips)}개입니다. "
                         f"이 구간의 대운은 두 판정을 함께 참고해서 보수적으로 해석하는 것이 좋습니다.")
        else:
            lines.append("대운 길흉 판정이 V1과 V2 사이에서 뒤집히는 구간은 없습니다 — "
                         "두 버전의 대운 흐름 해석은 대체로 일치합니다.")

        text = " ".join(lines)
        clbl = tk.Label(cin, text=text, bg=BG_CARD, fg=TEXT_MUTE, font=(KOR_FONT, 9),
                        wraplength=1000, justify="left")
        clbl.pack(anchor="w", fill="x")
        ccard.bind("<Configure>", lambda e, lbl=clbl:
                  lbl.configure(wraplength=max(200, e.width - 40)))

    def _show_daeun_detail_single(self, holder, x, analysis):
        for w in holder.winfo_children():
            w.destroy()
        h3(holder,
          f"{x['age']}~{x['age']+9}세  {x['pillar'].hanja}  "
          f"— {x['score']:+.2f} {x['grade']}"
          + (f" (전체 중 {x['rank']}위)" if "rank" in x else "")).pack(anchor="w", pady=(0, 8))
        theme = x.get("theme") or _theme(analysis, x["pillar"])
        tk.Label(holder, text=theme, bg=BG_CARD, fg=TEXT_MUTE,
                 font=(KOR_FONT, 9), wraplength=1000, justify="left").pack(anchor="w", pady=(0, 8))

        c = tk.Frame(holder, bg=BG_CARD_ALT)
        c.pack(fill="both", expand=True, padx=4)
        tk.Label(c, text="판단 근거", bg=BG_CARD_ALT, fg=TEXT_MAIN,
                 font=(KOR_FONT, 9, "bold")).pack(anchor="w", padx=8, pady=(8, 4))
        for n in x["notes"]:
            nlbl = tk.Label(c, text="· " + n, bg=BG_CARD_ALT, fg=TEXT_MAIN, font=(KOR_FONT, 8),
                           wraplength=900, justify="left")
            nlbl.pack(anchor="w", padx=8, pady=1, fill="x")
            c.bind("<Configure>", lambda e, lbl=nlbl:
                  lbl.configure(wraplength=max(140, e.width - 20)), add="+")
        tk.Label(c, text="", bg=BG_CARD_ALT).pack(pady=4)


        if isinstance(analysis, AnalysisV2):
            self._build_seun_detail(holder, x, analysis)
        else:
            tk.Label(holder, text="1년 주기(세운) 상세는 V2 탭에서 확인할 수 있습니다.",
                     bg=BG_ROOT, fg=TEXT_MUTE, font=(KOR_FONT, 8))\
                .pack(anchor="w", pady=(8, 0))

    def _build_seun_detail(self, holder, x, a2):
        """선택한 대운(10년) 구간의 1년 단위 세운 흐름을 하단에 표시."""
        ch = a2.chart
        birth_year = ch.birth_local.year
        start_year = birth_year + x["age"] - 1
        rows = score_seun_range(a2, start_year, count=10)

        sc = tk.Frame(holder, bg=BG_CARD_ALT)
        sc.pack(fill="both", expand=True, padx=4, pady=(10, 0))
        tk.Label(sc, text=f"{x['age']}~{x['age']+9}세 — 1년 주기 흐름 (세운)",
                 bg=BG_CARD_ALT, fg=TEXT_MAIN,
                 font=(KOR_FONT, 9, "bold")).pack(anchor="w", padx=8, pady=(8, 2))
        note_lbl = tk.Label(
            sc, bg=BG_CARD_ALT, fg=TEXT_MUTE, font=(KOR_FONT, 8), justify="left",
            text="세운 점수는 대운 점수와 다른 축입니다. 대운은 10년의 배경, "
                 "세운은 그 해의 사건이므로 두 값을 더하거나 평균 내지 마세요. "
                 "행을 클릭하면 그 해의 판단 근거가 아래에 나옵니다.")
        note_lbl.pack(anchor="w", padx=8, pady=(0, 8), fill="x")
        sc.bind("<Configure>", lambda e, lbl=note_lbl:
               lbl.configure(wraplength=max(200, e.width - 20)), add="+")

        cols = ("year", "ganji", "age", "score", "grade", "rank")
        heads = ["연도", "간지", "나이", "점수", "등급", "구간 내 순위"]
        tv = ttk.Treeview(sc, columns=cols, show="headings",
                          style="Saju.Treeview", height=min(10, len(rows)))
        for c, htext in zip(cols, heads):
            tv.heading(c, text=htext)
            tv.column(c, anchor="center", width=90)
        tv.pack(fill="x", padx=8, pady=(0, 4))
        tv.tag_configure("current", background="#F3E6B2")

        this_year = date.today().year
        for i, r in enumerate(rows):
            age = r["year"] - birth_year + 1
            tags = ["current"] if r["year"] == this_year else []
            tv.insert("", "end", iid=str(i), tags=tags, values=(
                r["year"], r["pillar"].hanja, f"{age}세",
                f"{r['score']:+.2f}", r["grade"], f"#{r['rank']}"))

        seun_note_holder = tk.Frame(sc, bg=BG_CARD_ALT)
        seun_note_holder.pack(fill="x", padx=8, pady=(4, 10))
        h3(seun_note_holder, "행을 선택하면 그 해의 판단 근거가 표시됩니다.")\
            .pack(anchor="w")


        seun_note_holder._wrap_labels = []

        def _on_note_holder_configure(event, nh=seun_note_holder):
            w = max(140, event.width - 20)
            for lbl in nh._wrap_labels:
                if lbl.winfo_exists():
                    lbl.configure(wraplength=w)

        seun_note_holder.bind("<Configure>", _on_note_holder_configure)

        def _on_seun_select(event, tv=tv, rows=rows, note_holder=seun_note_holder):
            sel = tv.selection()
            if not sel:
                return
            self._show_seun_notes(note_holder, rows[int(sel[0])])

        tv.bind("<<TreeviewSelect>>", _on_seun_select)

    def _show_seun_notes(self, holder, r):
        for w in holder.winfo_children():
            w.destroy()
        h3(holder, f"{r['year']}년 {r['pillar'].hanja} — 판단 근거").pack(anchor="w")
        width = max(140, holder.winfo_width() - 20)
        labels = []
        for n in r["notes"]:
            nlbl = tk.Label(holder, text="· " + n, bg=BG_CARD_ALT, fg=TEXT_MAIN,
                            font=(KOR_FONT, 8), wraplength=width, justify="left")
            nlbl.pack(anchor="w", pady=1, fill="x")
            labels.append(nlbl)
        holder._wrap_labels = labels


def main():
    app = SajuApp()
    app.mainloop()


if __name__ == "__main__":
    main()
