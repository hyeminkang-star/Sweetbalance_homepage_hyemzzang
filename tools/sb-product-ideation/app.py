"""신제품 아이디어 발굴 프로그램 화면. 실행: streamlit run app.py (또는 실행 파일 더블클릭)"""
import os
from pathlib import Path

import streamlit as st

from ideation import ai
from ideation.pipeline import LINK_TYPES, run

HERE = Path(__file__).resolve().parent
KEY_FILE = HERE / "api_key.txt"
DEFAULT_OUT = HERE / "결과"

st.set_page_config(page_title="스윗밸런스 신제품 아이디어 발굴", page_icon="🥗", layout="wide")
st.markdown("<style>h1{color:#2E7D32}</style>", unsafe_allow_html=True)
st.title("🥗 신제품 아이디어 발굴")
st.caption("리뷰·매출·트렌드 데이터를 근거로 신제품 콘셉트 후보를 뽑습니다. 점수는 AI 참고 의견이며, 최종 선택은 상품팀이 합니다.")


def load_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    try:
        return KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Claude API 키", value=load_key(), type="password",
                            help="console.anthropic.com → API Keys에서 발급한 키 (sk-ant-로 시작)")
    if st.checkbox("이 PC에 키 저장", value=KEY_FILE.exists(), help=f"{KEY_FILE.name} 파일에 저장됩니다. 공용 PC에서는 끄세요."):
        if api_key and api_key != load_key():
            KEY_FILE.write_text(api_key, encoding="utf-8")
    elif KEY_FILE.exists():
        KEY_FILE.unlink()
    model = st.selectbox("AI 모델", list(ai.MODEL_CHOICES), format_func=ai.MODEL_CHOICES.get)
    n_concepts = st.slider("콘셉트 후보 개수", 10, 80, 50, step=5)
    category = st.text_input("카테고리만 보기 (선택)", placeholder="예: 샐러드")
    web_trends = st.checkbox("트렌드 파일이 없으면 웹 검색으로 찾기", value=True)
    max_reviews = st.number_input("AI에게 보낼 최대 리뷰 수", 200, 5000, 1500, step=100,
                                  help="리뷰가 이보다 많으면 요청·불만·대표 리뷰를 우선 보냅니다. 많을수록 비용이 늘어납니다.")
    out_root = st.text_input("결과 저장 폴더", value=str(DEFAULT_OUT))

st.subheader("1. 데이터 넣기")
st.markdown("PC 폴더와 구글 링크 중 **하나만 넣어도, 둘 다 넣어도** 됩니다.")
local_dir = st.text_input("PC 데이터 폴더 경로", placeholder=r"예: C:\Users\혜민\Documents\리뷰데이터  또는  /Users/hyemin/리뷰데이터",
                          help="폴더 안에 리뷰/ 매출/ 트렌드/ 하위 폴더를 두거나, 파일명에 '리뷰', '매출', '트렌드', '마스터'를 넣어 주세요.")

st.markdown("**구글 시트 / 구글 드라이브 파일 링크** (한 줄에 하나씩)")
st.caption("구글 파일의 [공유] → 일반 액세스를 '링크가 있는 모든 사용자(뷰어)'로 바꿔야 불러올 수 있습니다. 드라이브 '폴더' 링크는 안 되고 파일 링크만 됩니다.")
cols = st.columns(len(LINK_TYPES))
google_links = {}
for col, kind in zip(cols, LINK_TYPES):
    with col:
        google_links[kind] = st.text_area(f"{kind} 링크", height=110, key=f"links_{kind}",
                                          placeholder="https://docs.google.com/spreadsheets/d/...").splitlines()

st.subheader("2. 실행")
if st.button("신제품 아이디어 뽑기", type="primary", use_container_width=True):
    if not api_key:
        st.error("왼쪽 설정에 Claude API 키를 넣어 주세요.")
        st.stop()
    logs = []
    box = st.status("실행 중...", expanded=True)

    def log(msg):
        logs.append(msg)
        box.write(msg)

    try:
        res = run(out_root, local_dir=local_dir or None, google_links=google_links, api_key=api_key, model=model,
                  category=category or None, n_concepts=n_concepts, web_trends=web_trends, max_reviews=int(max_reviews), log=log)
    except Exception as e:  # noqa: BLE001 - 화면에 오류를 보여 주고 멈춘다
        box.update(label="실패", state="error")
        st.error(str(e))
        st.stop()
    box.update(label="완료", state="complete", expanded=False)
    st.session_state["result"] = res

res = st.session_state.get("result")
if res:
    st.subheader("3. 결과")
    st.success(f"저장 폴더: {res['out_dir']}")
    if res["warnings"]:
        st.warning("근거 리뷰 ID를 확인해야 하는 콘셉트가 있습니다(엑셀에서 빨간색):\n" + "\n".join(res["warnings"]))
    c1, c2 = st.columns(2)
    c1.download_button("엑셀 내려받기", res["excel"].read_bytes(), file_name=res["excel"].name, use_container_width=True,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    c2.download_button("요약 보고서 내려받기(.md)", res["report"].read_bytes(), file_name=res["report"].name, use_container_width=True)
    rv = {r["id"]: r for r in res["analysis"]["reviews"]}
    st.markdown("#### 상위 후보")
    for n, c in enumerate(res["concepts"][:10], 1):
        with st.expander(f"{n}. {c['name']} — {c['_total']}점 · {c['approach']}"):
            st.write(c["one_liner"])
            st.write(f"**근거**: {c['rationale']}")
            for i in c["_valid"][:3]:
                r = rv[i]
                st.caption(f"\"{r['text']}\" — {r['file']} {r['row']}행")
            st.write(f"**리스크**: {c['risks']}")
    st.markdown("#### 요약 보고서 미리보기")
    st.markdown(res["report"].read_text(encoding="utf-8"))
