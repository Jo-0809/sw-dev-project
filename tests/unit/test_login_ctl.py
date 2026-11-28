"""단위 테스트 — app/pd/user/login_ctl.py (로그인 제어, UC1)

기법: 의사결정 테이블 + 스텁
  login_ctl 이 부르는 account.match(계정 대조)와 session.create/find/delete(세션)를 스텁으로 바꿔서
  login_ctl 의 판단만 시험한다. DB와 서버는 쓰지 않는다.

의사결정 테이블 (login)
  조건            R1   R2   R3   R4   R5
  아이디 입력됨     N    N    Y    Y    Y      (공백만 있으면 입력 안 함)
  비밀번호 입력됨   N    Y    N    Y    Y
  계정 일치        -    -    -    N    Y
  결과            필수  필수  필수  불일치 성공
"""

import pytest

from app.pd.user import account, login_ctl, session


@pytest.fixture
def stubs(monkeypatch):
    """계정 대조·세션 생성 스텁. 부른 기록을 calls 에 남긴다."""
    calls = {"match": [], "create": [], "delete": []}

    def fake_match(login_id, pw):
        calls["match"].append((login_id, pw))
        return 7 if (login_id, pw) == ("tester", "pw-1234") else None

    def fake_create(account_id, auto):
        calls["create"].append((account_id, auto))
        return "token-abc"

    monkeypatch.setattr(account, "match", fake_match)
    monkeypatch.setattr(session, "create", fake_create)
    monkeypatch.setattr(session, "delete", lambda token: calls["delete"].append(token))
    return calls


# ---- _check_required: 필수 입력 확인 (동치 분할: 입력 있음 / 빈 문자열 / 공백만 / None) ----
@pytest.mark.parametrize(
    "login_id, pw, expected",
    [
        ("tester", "pw-1234", []),
        ("", "pw-1234", ["login_id"]),
        ("   ", "pw-1234", ["login_id"]),  # 공백만 → 입력 안 한 것
        ("tester", "", ["password"]),
        ("", "", ["login_id", "password"]),
        (None, None, ["login_id", "password"]),  # 폼 값이 아예 없을 때
    ],
    ids=["UT-L-01", "UT-L-02", "UT-L-03", "UT-L-04", "UT-L-05", "UT-L-06"],
)
def test_check_required(login_id, pw, expected):
    assert login_ctl._check_required(login_id, pw) == expected


def test_password_space_is_input():
    """UT-L-07 비밀번호는 공백도 문자라서 지우지 않는다 → ' ' 는 입력한 것으로 본다."""
    assert login_ctl._check_required("tester", " ") == []


# ---- login: 의사결정 테이블 R1~R5 ----
@pytest.mark.parametrize(
    "login_id, pw, missing",
    [("", "", ["login_id", "password"]), ("", "pw-1234", ["login_id"]), ("tester", "", ["password"])],
    ids=["UT-L-08", "UT-L-09", "UT-L-10"],
)
def test_login_required_does_not_check_account(stubs, login_id, pw, missing):
    """R1~R3 빈칸이 있으면 '필수' 오류. 계정 대조(account.match)를 부르지 않는다."""
    assert login_ctl.login(login_id, pw, auto=False) == (False, None, "required", missing)
    assert stubs["match"] == [] and stubs["create"] == []


def test_login_mismatch(stubs):
    """UT-L-11 R4 계정 불일치 → '불일치' 오류, 세션을 만들지 않는다."""
    assert login_ctl.login("tester", "wrong-pw", auto=False) == (False, None, "mismatch", [])
    assert stubs["match"] == [("tester", "wrong-pw")] and stubs["create"] == []


@pytest.mark.parametrize("auto", [False, True], ids=["UT-L-12", "UT-L-13"])
def test_login_success_creates_session(stubs, auto):
    """R5 성공 → 세션 토큰을 돌려준다. 자동 로그인 선택 여부를 세션 생성에 그대로 넘긴다."""
    assert login_ctl.login("tester", "pw-1234", auto=auto) == (True, "token-abc", None, [])
    assert stubs["create"] == [(7, auto)]


def test_login_strips_id_spaces(stubs):
    """UT-L-14 아이디 앞뒤 공백은 지우고 대조한다 (비밀번호는 그대로)."""
    ok, *_ = login_ctl.login("  tester  ", "pw-1234", auto=False)
    assert ok and stubs["match"] == [("tester", "pw-1234")]


# ---- auto_login: 저장된 세션으로 인증 (UC1 대안 1) ----
@pytest.mark.parametrize(
    "found, expected",
    [({"account_id": 7, "token": "t"}, 7), (None, None)],
    ids=["UT-L-15", "UT-L-16"],
)
def test_auto_login(monkeypatch, found, expected):
    monkeypatch.setattr(session, "find", lambda token: found)
    assert login_ctl.auto_login("t") == expected


def test_logout_deletes_session(stubs):
    """UT-L-17 로그아웃하면 그 토큰의 세션을 지운다."""
    login_ctl.logout("token-abc")
    assert stubs["delete"] == ["token-abc"]


# ---- 설계 외 보조 함수 (실제 DB 사용) ----
def test_login_id_of_and_has_accounts(unit_db):
    """UT-L-18 계정 0개 → has_accounts False (경계), 1개 → True. 없는 번호의 아이디는 None."""
    assert login_ctl.has_accounts() is False
    account.create("tester", "pw-1234")
    aid = account.match("tester", "pw-1234")
    assert login_ctl.has_accounts() is True
    assert login_ctl.login_id_of(aid) == "tester"
    assert login_ctl.login_id_of(aid + 999) is None
