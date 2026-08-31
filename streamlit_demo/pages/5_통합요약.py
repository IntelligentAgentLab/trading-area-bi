import streamlit as st

from common import render_filters

st.set_page_config(page_title="통합요약", page_icon="🧩", layout="wide")
st.title("🧩 통합요약 — 현상 → 원인 → 효과")

선택업종 = render_filters()

st.info(
    "🚧 대시보드(A)·토픽모델링(C)·인과추론(D) 세 페이지가 준비되는 대로 이 페이지에서 "
    "① 현상 → ② 원인 → ③ 효과를 한 화면에 모을 예정입니다. 세 담당자 작업이 어느 정도 끝난 뒤 "
    "다같이 정리하면 됩니다.\n\n"
    "참고: 토픽모델링(②)은 업종 구분이 없어서(`common.py`의 `load_topics()`) 사이드바 업종을 "
    "바꿔도 값이 안 바뀝니다 — ①③만 업종별로 연동하면 됩니다."
)
