import streamlit as st

st.set_page_config(page_title="인과추론", page_icon="📈", layout="wide")
st.title("📈 인과추론")

st.info(
    "🚧 D 담당(조소민) — DiD 등 인과추론 분석을 여기에 구현하세요.\n\n"
    "`streamlit_demo/common.py`의 `load_topics()` 패턴 참고: 실데이터(예: statsmodels 추정 결과)가 "
    "있으면 그걸 쓰고, 없으면 더미로 폴백하는 함수를 만들면 다른 페이지가 안 깨집니다."
)
