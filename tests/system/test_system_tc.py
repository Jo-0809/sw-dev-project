"""시스템 테스트 케이스 STC-01 ~ STC-04 (유스케이스 명세서 흐름 기반, 표 15-7 형식).

사용자가 화면에서 하는 입력을 그대로 HTTP 요청으로 보내고, 화면에 나오는 결과를 확인한다.
구체적인 입력값과 예상 결과는 docs/test/TEST_CASES.md 의 표와 같다.

  STC-01  UC1 대안 흐름 1   자동 로그인을 고른 뒤 다시 접속하면 로그인 화면 없이 메인 화면
  STC-02  UC2 예외 흐름 1   학과를 고르지 않고 저장 → '학과와 학년은 반드시 입력해야 합니다', 저장 안 됨
  STC-03  UC3 예외 흐름 2   robots.txt 로 금지된 게시판 주소 직접 입력 → '수집이 허용되지 않는 게시판입니다'
  STC-04  UC5 정상 흐름     지원 가능 공고만 마감일 가까운 순으로 표시

시연 날짜는 2026-11-16 (tests/conftest.py 의 DEMO_TODAY), 공지는 모의 게시판에서 수집한다.
"""

import re

import requests
from conftest import BASE

STC_ID, STC_PW = "stc-user", "Stc-pw-2026"


def _fresh_user(profile=None):
    """시스템 테스트 전용 계정을 만들고 프로필·관심 출처를 비운다. 프로필을 주면 저장한다."""
    from app.dm.db import connect
    from app.pd.user import account
    from app.pd.user import profile as prof

    account.set_password(STC_ID, STC_PW)
    aid = account.match(STC_ID, STC_PW)
    with connect() as c:
        for t in ("login_session", "profile", "subscription", "view_log"):
            c.execute(f"DELETE FROM {t} WHERE account_id=?", (aid,))
    if profile:
        prof.save(aid, *profile)
    return aid


def _rows(html):
    """공고 목록 표의 행을 (마감 D-day, 제목, 판정, 마감 일시)로 읽는다."""
    out = []
    for tr in re.findall(r"<tr class=.*?</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", td).strip() for td in re.findall(r"<td>(.*?)</td>", tr, re.S)]
        out.append((cells[0], cells[1].split("\n")[0].strip(), cells[2], cells[3]))
    return out


def _login(s, auto=False):
    data = {"login_id": STC_ID, "password": STC_PW}
    if auto:
        data["auto"] = "on"
    return s.post(BASE + "/login", data=data)


def test_stc01_auto_login(server):
    """STC-01 UC1 대안 흐름 1 — 자동 로그인."""
    _fresh_user(profile=("경상국립대학교", "항공우주공학부", 3, "재학"))
    s1 = requests.Session()
    r = _login(s1, auto=True)  # 자동 로그인 체크 + [로그인]
    assert r.url.endswith("/notices")
    cookie = next(c for c in s1.cookies if c.name == "nc_session")
    assert cookie.expires is not None  # 브라우저를 닫아도 남는 쿠키 (30일)
    # 브라우저를 다시 연 상황: 저장된 쿠키만 가지고 로그인 화면 주소로 접속
    s2 = requests.Session()
    s2.cookies.set("nc_session", cookie.value)
    r = s2.get(BASE + "/login")
    assert r.url.endswith("/notices") and 'action="/login"' not in r.text  # 로그인 화면을 거치지 않음


def test_stc02_profile_department_missing(server):
    """STC-02 UC2 예외 흐름 1 — 학과를 고르지 않고 저장."""
    from app.pd.user import profile

    aid = _fresh_user()
    s = requests.Session()
    assert _login(s).url.endswith("/profile?first=1")  # 프로필이 없으면 프로필 입력 화면 (2-1)
    r = s.post(
        BASE + "/profile",
        data={"first": 1, "university": "경상국립대학교", "department": "", "grade": "3", "status": "재학"},
    )
    assert r.status_code == 200
    assert "학과와 학년은 반드시 입력해야 합니다" in r.text and "학과를 선택하세요" in r.text
    assert "학년을 선택하세요" not in r.text  # 학년은 골랐으므로 학과 칸만 표시
    assert profile.find(aid) is None  # 저장되지 않음


def test_stc03_robots_blocked_address(server):
    """STC-03 UC3 예외 흐름 2 — robots.txt 로 금지된 게시판 주소."""
    from app.pd.source import subscription

    aid = _fresh_user(profile=("경상국립대학교", "항공우주공학부", 3, "재학"))
    s = requests.Session()
    _login(s)
    address = BASE + "/mock/edu/na/ntt/selectNttList.do?mi=9001&bbsId=9999"
    r = s.post(BASE + "/sources/address", data={"address": address})
    assert "수집이 허용되지 않는 게시판입니다" in r.text
    assert subscription.find(aid) == []  # 관심 출처에 추가되지 않음


def test_stc04_possible_list_sorted_by_deadline(server):
    """STC-04 UC5 정상 흐름 — 지원 가능 공고를 마감일 가까운 순으로."""
    from app.demo import seed
    from app.pd.collect.collect_ctl import collector
    from app.pd.source import source, subscription

    seed.reset_demo_data()
    collector.reset_last_run()
    aid = _fresh_user(profile=("경상국립대학교", "소프트웨어공학과", 2, "재학"))
    for src in source.all():
        if src["kind"] == "mock":
            subscription.save(aid, src["id"])
    collector.start()  # UC4 수집 (모의 게시판 3곳)
    s = requests.Session()
    r = _login(s)  # 로그인하면 메인 화면 = 공고 목록 화면 (5-1)
    assert r.url.endswith("/notices")
    assert _rows(r.text) == [  # 오늘 2026-11-16 기준
        ("D-1", "소프트웨어공학과 전공 멘토링 멘티 모집", "지원 가능", "2026-11-17 18:00"),
        ("D-2", "2026 GNU SW 해커톤 참가자 모집", "지원 가능", "2026-11-18 23:59"),
        ("D-4", "2026 동계 해외 단기연수 프로그램 참가자 모집", "지원 가능", "2026-11-20 18:00"),
        ("D-9", "2027학년도 1학기 교환학생 선발 공고", "지원 가능", "2026-11-25 16:00"),
    ]
    for not_shown in ("2026 동계 산학협력 현장실습(인턴십) 참여 학생 모집", "2027학년도 1학기 학습 튜터링 튜터 모집"):
        assert not_shown not in r.text  # 지원 불가·확인 필요는 기본 목록에 없음
