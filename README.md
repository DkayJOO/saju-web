# 사주풀이 (Saju Web App)

생년월일시를 입력하면 원국·강약·용신·대운을 풀이해주는 사주(四柱) 분석 웹앱입니다.
전통 억부용신 판정(V1)과, 지장간·통근·계절·종격까지 반영한 심화 판정(V2)을 함께 제공하며,
V2를 먼저 보여주고 V1은 참고용으로 아래에 접어둡니다.

⚠️ 이 결과는 명리학이라는 전통 해석 체계를 코드로 옮긴 것이며, 과학적으로 검증된
예측이 아닙니다. 자기 성찰의 참고 자료로만 사용하세요.

## 주요 기능

- **모바일 우선 UI** — 폰에서 바로 쓰기 좋은 세로 레이아웃, 큰 탭 영역
- **V2 우선 노출** — 정밀 분석(V2) 결과를 먼저 보여주고, 간편 버전(V1)은 아래 토글로 제공
- **결과 내보내기** — JSON / TXT / 이미지(PNG) 3가지 형식으로 다운로드
  - JSON·TXT 파일은 ChatGPT·Claude 등 AI 챗봇에 올려서 추가 질문(궁합, 시기 등)을
    이어가는 용도로 쓸 수 있습니다.
- **시간 설정 안내** — 야자시/정자시, 진태양시, 균시차가 무엇인지 쉬운 말로 설명하고
  기본값을 추천해줍니다 (연장자·초심자도 헷갈리지 않도록)
- **한지·먹빛 테마** — 라이트 모드는 한지 바탕에 주색(인주) 포인트, 다크 모드는
  먹지 바탕에 금박 텍스트로 자동 전환됩니다 (기기의 다크모드 설정을 따라갑니다)

## 폴더 구조

```
saju_web/
├── streamlit_app.py      # UI (Streamlit)
├── saju_app.py            # 계산 엔진 (원본 파일, 수정 없이 그대로 사용)
├── fonts/
│   ├── NotoSansKR-Regular.ttf   # 이미지 내보내기용 한글 폰트 (OFL 라이선스)
│   └── OFL.txt
├── requirements.txt
├── .streamlit/config.toml # 기본(라이트) 테마
└── .gitignore
```

## 로컬 실행

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

브라우저가 자동으로 `http://localhost:8501` 을 엽니다.

## GitHub에 올리기

```bash
cd saju_web
git init
git add .
git commit -m "사주풀이 웹앱 초기 버전"
git branch -M main
git remote add origin https://github.com/<본인계정>/<저장소이름>.git
git push -u origin main
```

- `saju_app.py`는 tkinter가 없는 환경(clouds)에서도 계산 엔진만 안전하게 import
  되도록 이미 처리돼 있어서(내부에 tkinter stub 처리) 별도 수정 없이 그대로 올리면 됩니다.
- `fonts/NotoSansKR-Regular.ttf`는 10MB 정도라 GitHub 용량 제한(파일당 100MB)에는
  문제없지만, 저장소를 가볍게 하고 싶다면 정적 굵기(static weight) TTF로 교체해도 됩니다.

## Streamlit Community Cloud에 배포하기

1. [share.streamlit.io](https://share.streamlit.io) 접속 후 GitHub 계정으로 로그인
2. **New app** 클릭 → 방금 올린 저장소 선택
3. **Main file path**에 `streamlit_app.py` 지정
4. **Deploy** 클릭 — 1~2분 후 `https://<앱이름>.streamlit.app` 주소가 생성됩니다
5. 이후 GitHub에 새 커밋을 push하면 앱이 자동으로 재배포됩니다

배포 후 접속 링크만 있으면 누구나 브라우저(모바일 포함)로 바로 쓸 수 있습니다.
별도 설치나 로그인이 필요 없습니다.

## 커스터마이징 메모

- **테마 색상**: `streamlit_app.py` 상단 `CUSTOM_CSS`의 `--hanji-bg`, `--seal` 등
  CSS 변수를 바꾸면 라이트/다크 모드 배색을 함께 조정할 수 있습니다.
- **이미지 카드 디자인**: `make_summary_image()` 함수에서 PIL로 그립니다. 카드에
  넣을 항목(대운 요약 등)을 추가하고 싶으면 이 함수만 수정하면 됩니다.
- **지역 목록 확장**: `saju_app.py`의 `CITIES` 딕셔너리에 시·군 단위를 추가하면
  UI의 지역 선택 목록에도 자동 반영됩니다.

## 라이선스

- 계산 엔진(`saju_app.py`)의 저작권은 원 저작자에게 있습니다.
- 번들 폰트 `NotoSansKR-Regular.ttf`는 SIL Open Font License 1.1을 따릅니다
  (`fonts/OFL.txt` 참고).
