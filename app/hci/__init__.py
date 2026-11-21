"""HCI 계층 — 웹 화면(경계 클래스)과 라우팅. PD 계층의 제어 클래스만 부르고 DM 계층은 직접 쓰지 않는다.

화면 → 부르는 패키지 (tests/test_architecture.py 의 HCI_PACKAGE)
  login_view   로그인 화면          → 사용자
  main_view    메인 화면 (/ 진입)    → 사용자   메인 화면 = 공고 목록 화면 5-1 (UI 설계서). / 는 갈 곳만 정한다
  profile_view 프로필 입력 화면      → 사용자
  source_view  관심 출처 관리 화면   → 관심출처
  list_view    공고 목록 화면        → 공고
  detail_view  공고 상세 화면        → 공고
  common       쿠키 로그인 확인·화면 그리기 공통 (설계 외 보조 모듈, 사용자 패키지와 설정만 씀)
"""
