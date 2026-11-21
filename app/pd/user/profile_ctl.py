"""<<control>> 프로필 제어 — 필수 항목 검사, 학적 프로필 저장 (UC2).

필수 항목: 학과, 학년 (예외 1: 누락 시 '학과와 학년은 반드시 입력해야 합니다').
평점(학점)은 받지 않는다 (팀 결정).
"""

from . import profile

REQUIRED = ("department", "grade")  # 필수 항목
UNIVERSITIES = ["경상국립대학교"]
DEPARTMENTS = [
    "소프트웨어공학과",
    "컴퓨터공학과",
    "항공우주공학부",
    "기계공학부",
    "산업시스템공학부",
    "전기공학과",
    "화학공학과",
    "건축공학과",
    "경영학과",
    "경제학부",
    "국어국문학과",
    "영어영문학과",
]
STATUSES = ["재학", "휴학", "졸업예정"]


def load(account_id):  # 프로필을 불러온다(계정) : 기존 값
    return profile.find(account_id)


def _check_required(values):  # 필수 항목을 검사한다(입력값)
    return [k for k in REQUIRED if not str(values.get(k) or "").strip()]


def save(account_id, values):  # 저장한다(입력값)
    missing = _check_required(values)
    if missing:
        return False, missing
    profile.save(
        account_id,
        values.get("university") or UNIVERSITIES[0],
        values["department"],
        int(values["grade"]),
        values.get("status") or "재학",
    )
    return True, []
