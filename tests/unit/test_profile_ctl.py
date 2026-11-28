"""단위 테스트 — app/pd/user/profile_ctl.py (프로필 제어, UC2)

기법: 동치 분할 + 경계값 분석
  학과  : 입력함 / 빈 문자열 / 공백만 / 값 없음(None)
  학년  : 입력 범위는 프로필 화면(2-1)의 선택지 1~4학년
          유효 클래스 {1..4}, 무효 클래스 {0 이하}, {5 이상}, {숫자 아님}
          경계값 0 · 1 · 4 · 5 와 특수값 '', '2.5', 'abc'
  무효 입력은 저장하지 않고 '필수 항목 누락'과 같은 자리(예외 1)로 돌려준다.
"""

import pytest

from app.pd.user import profile, profile_ctl

VALID = {"university": "경상국립대학교", "department": "항공우주공학부", "grade": "3", "status": "재학"}


def _with(**kw):
    return {**VALID, **kw}


# ---- _check_required: 학과 동치 분할 ----
@pytest.mark.parametrize(
    "department, expected",
    [("항공우주공학부", []), ("", ["department"]), ("   ", ["department"]), (None, ["department"])],
    ids=["UT-P-01", "UT-P-02", "UT-P-03", "UT-P-04"],
)
def test_department_required(department, expected):
    assert profile_ctl._check_required(_with(department=department)) == expected


# ---- _check_required: 학년 경계값·특수값 ----
@pytest.mark.parametrize(
    "grade, ok",
    [
        ("0", False),  # 경계 아래
        ("1", True),  # 하한 경계
        ("4", True),  # 상한 경계
        ("5", False),  # 경계 위
        ("", False),  # 빈칸
        (None, False),
        ("2.5", False),  # 정수 아님
        ("abc", False),  # 숫자 아님
        (" 2 ", True),  # 앞뒤 공백은 허용
    ],
    ids=[
        "UT-P-05",
        "UT-P-06",
        "UT-P-07",
        "UT-P-08",
        "UT-P-09",
        "UT-P-10",
        "UT-P-11",
        "UT-P-12",
        "UT-P-13",
    ],
)
def test_grade_boundary(grade, ok):
    assert profile_ctl._check_required(_with(grade=grade)) == ([] if ok else ["grade"])


def test_both_missing():
    """UT-P-14 학과·학년 둘 다 비면 두 항목 모두 돌려준다 (화면이 두 칸 모두 표시)."""
    assert profile_ctl._check_required({"department": "", "grade": ""}) == ["department", "grade"]


# ---- save / load ----
@pytest.mark.parametrize("grade", ["0", "5", "abc"], ids=["UT-P-15", "UT-P-16", "UT-P-17"])
def test_invalid_grade_is_not_saved(two_accounts, grade):
    """무효 학년은 오류 없이 (False, ['grade']) 를 돌려주고 DB에 쓰지 않는다."""
    aid, _ = two_accounts
    assert profile_ctl.save(aid, _with(grade=grade)) == (False, ["grade"])
    assert profile.find(aid) is None


def test_save_valid_and_defaults(two_accounts):
    """UT-P-18 소속 대학·재학 상태를 비우면 기본값(경상국립대학교, 재학). 학년은 정수로 저장."""
    aid, _ = two_accounts
    assert profile_ctl.save(aid, {"department": "항공우주공학부", "grade": "4"}) == (True, [])
    p = profile.find(aid)
    assert (p["university"], p["department"], p["grade"], p["status"]) == (
        "경상국립대학교",
        "항공우주공학부",
        4,
        "재학",
    )


def test_save_overwrites_and_load_prefills(two_accounts):
    """UT-P-19 다시 저장하면 덮어쓴다. load 는 기존 값을 돌려준다 (UC2 대안 1 미리 채우기). 다른 계정은 그대로."""
    a, b = two_accounts
    profile_ctl.save(a, _with(grade="1"))
    profile_ctl.save(a, _with(grade="2", status="휴학"))
    assert profile_ctl.load(a)["grade"] == 2 and profile_ctl.load(a)["status"] == "휴학"
    assert profile_ctl.load(b) is None
