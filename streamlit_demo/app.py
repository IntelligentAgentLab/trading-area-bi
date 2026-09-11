import streamlit as st

st.set_page_config(page_title="소비상권 BI 데모", page_icon="📊", layout="wide")


def 홈():
    st.title("소비·상권 BI 프로젝트")

    st.markdown(
        """
        상단 메뉴에서 페이지를 선택하세요.

        - **대시보드**: 매출 데이터 시각화 (최재원·남지우 담당 — 준비 중)
        - **토픽모델링**: BigKinds 뉴스 LDA 토픽 비중 추이·대표 기사 (완료, 실데이터 연동됨)
        - **소비자상담**: 1372 소비자상담 데이터 탐색 (완료, 실데이터 연동됨)
        - **인과추론**: DiD 등 정책 효과 추정 (조소민 담당 — 준비 중)
        - **통합요약**: 세 페이지 핵심 결과를 한 화면에 모으는 페이지 (각자 작업 끝난 뒤 정리 예정)

        **참고**: 토픽모델링·소비자상담 페이지는 대시보드·인과추론과 데이터로 연결돼 있지 않습니다 —
        매출이 특이한 시기를 뉴스·상담 데이터로 확인하는 용도라 업종 구분 없이 독립적으로 동작합니다.
        공통 사이드바 필터는 없고, 페이지별로 필요하면 각자 구현하면 됩니다.
        """
    )

    st.info("상단 메뉴에서 각 화면으로 이동하세요.")


# st.navigation(position="top")을 쓰면 페이지 목록이 좌측 사이드바 대신 화면 상단에 가로로
# 뜬다. 이 방식을 쓰는 순간 pages/ 폴더 자동 인식은 꺼지고 여기 나열한 목록이 곧 전체 메뉴가
# 되므로, 페이지를 추가/삭제할 땐 이 리스트도 같이 고쳐야 한다. 각 페이지 파일 쪽의
# st.set_page_config() 호출은 지웠음 — 앱 전체에서 최초 1번(바로 위)만 허용되기 때문.
pages = [
    st.Page(홈, title="홈", icon="🏠", default=True),
    st.Page("pages/1_대시보드.py", title="대시보드", icon="📊"),
    st.Page("pages/2_토픽모델링.py", title="토픽모델링", icon="🗣️"),
    st.Page("pages/3_소비자상담.py", title="소비자상담", icon="🔎"),
    st.Page("pages/4_인과추론.py", title="인과추론", icon="📈"),
    st.Page("pages/5_통합요약.py", title="통합요약", icon="🧩"),
]

st.navigation(pages, position="top").run()
