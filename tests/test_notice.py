"""공고 패키지 — 판정 엔진(항목 대조, 제외 조건), judge(profile), 공고 조회 제어(UC5)."""

import pytest
from conftest import PROFILE

from app.pd.notice import engine


@pytest.mark.parametrize(
    "item,value,expect",
    [
        ("학년", "1~3학년", "충족"),
        ("학년", "4학년", "불충족"),
        ("학년", "2학년 이상", "충족"),
        ("학년", "학년 무관", "충족"),
        ("학과", "전공 무관", "충족"),
        ("학과", "소프트웨어공학과", "충족"),
        ("학과", "기계공학부", "불충족"),
        ("학과", "공과대학 소속", "확인 필요"),
        ("재학 상태", "재학생 (휴학생 제외)", "충족"),
        ("소속 대학", "경상국립대학교 (본교)", "충족"),
        ("기타", "평점 3.5 이상", "확인 필요"),
    ],
)
def test_engine_items(item, value, expect):
    prof = dict(PROFILE)
    assert engine._match_item(item, value, prof)[0] == expect


def test_engine_v2_rules():
    p = dict(PROFILE)
    assert engine._match_item("학년", "2학년 2학기 이상", p)[0] == engine.CHECK
    assert engine._match_item("학년", "2학년 2학기 이상", {**p, "grade": 3})[0] == engine.OK
    assert engine._match_item("학과", "전공 불문", p)[0] == engine.OK
    assert engine._match_item("학과", "의생명과학분야 관련 학과", p)[0] == engine.CHECK  # 넓은 표현 → 확인 필요


def test_dept_rules_feedback_table():
    p = dict(PROFILE)

    def m(v):
        return engine._match_item("학과", v, p)[0]

    assert m("SW 관련 학과") == engine.OK
    assert m("컴퓨터·소프트웨어 관련 학과") == engine.OK
    assert m("IT계열 학과") == engine.OK
    assert m("소프트웨어학과") == engine.CHECK
    assert m("컴퓨터소프트웨어공학과") == engine.CHECK  # 이름 일부만 겹침 → 충족으로 보지 않음
    assert m("기계공학과, 항공우주공학과") == engine.NO
    assert m("UNIT 관련 학과") == engine.CHECK  # 영문 약어는 단어 단위로만


def test_grades_ignore_school_year():
    assert engine._grades("2026학년도 2학기 재학생") is None  # 2026학년도의 6을 6학년으로 읽지 않음
    assert engine._grades("2026학년도 1, 2학년") == {1, 2}


def test_exclusion_conditions():
    p = dict(PROFILE)

    def m(i, v, pr=p):
        return engine._match_item(i, v, pr)[0]

    assert m("학과", "소프트웨어공학과 제외") == engine.NO
    assert m("학과", "의과대학 제외 전 학과") == engine.OK
    assert m("학과", "의학계열 제외") == engine.CHECK
    assert m("학년", "1학년 제외") == engine.OK
    assert m("학년", "2학년 제외") == engine.NO
    assert m("소속 대학", "경상국립대학교 제외") == engine.NO
    assert m("학과", "제한 없음") == engine.OK  # '제한 없음'은 제외가 아님


def test_dept_partial_needs_two_chars():
    p = {"university": "경상국립대학교", "department": "경영학과", "grade": 2, "status": "재학"}
    assert engine._match_item("학과", "경제학부", p)[0] == engine.NO  # '경' 한 글자로 겹침 판정하지 않음
    q = {**p, "department": "항공우주공학과"}
    assert engine._match_item("학과", "항공우주공학부", q)[0] == engine.CHECK


def test_exclusion_of_other_groups():
    """'휴학생·졸업예정자·대학원생 제외'는 그 항목의 제외가 아니다. 지원 가능한 공고를 지원 불가로 숨기지 않는다."""
    p = dict(PROFILE)

    def m(i, v):
        return engine._match_item(i, v, p)[0]

    assert m("학년", "2~4학년 (휴학생 제외)") == engine.OK
    assert m("학년", "2학년 이상 재학생(졸업예정자 제외)") == engine.OK
    assert m("학과", "소프트웨어공학과 재학생 (휴학생 제외)") == engine.OK
    assert m("소속 대학", "경상국립대학교 재학생(휴학생 제외)") == engine.OK
    assert m("학과", "소프트웨어공학과 제외") == engine.NO
    assert m("학과", "전 학과 (대학원생 제외)") == engine.OK
    assert m("학년", "2학년 이상, 휴학생 제외") == engine.OK  # 쉼표 뒤 다른 종류는 따로 끊는다
    assert m("학년", "1~4학년 (2학년 제외)") == engine.NO
    assert m("학과", "기계공학과, 소프트웨어공학과 제외") == engine.NO  # 쉼표로 이어진 같은 종류는 함께 제외


def test_exclusion_without_separators():
    """괄호·쉼표 없이 이어 써도 '제외' 바로 앞의 같은 종류 낱말만 제외 대상으로 본다."""
    p = dict(PROFILE)

    def m(i, v):
        return engine._match_item(i, v, p)[0]

    assert m("학년", "2학년 이상 휴학생 제외") == engine.OK
    assert m("학과", "소프트웨어공학과 휴학생 제외") == engine.OK
    assert m("학과", "소프트웨어공학과 재학생 중 휴학생은 제외") == engine.OK
    assert m("소속 대학", "경상국립대학교 휴학생 제외") == engine.OK
    assert m("학년", "1학년 및 2학년 제외") == engine.NO  # '및'으로 이은 같은 종류는 함께
    assert m("학과", "기계공학과 소프트웨어공학과 제외") == engine.NO  # 띄어쓰기로 이은 같은 종류도 함께
    assert m("학과", "전 학과 (의예과 제외)") == engine.OK
    assert m("학년", "2~4학년 재학생, 휴학생 제외") == engine.OK


def test_judge_takes_profile_only(test_account):
    """판정한다(프로필): 프로필 주인의 관심 출처 공지만 판정한다 (출처·공지 번호를 따로 받지 않음)."""
    from app.pd.notice import notice
    from app.pd.source import source, subscription
    from app.pd.user import profile

    profile.save(test_account, **PROFILE)
    mine = {s["id"] for s in subscription.find(test_account)}
    judged = engine.judge(profile.find(test_account))
    for nid in judged:
        assert notice.get(nid)["source_id"] in mine
    other = [s["id"] for s in source.all() if s["id"] not in mine]
    assert not any(n["id"] in judged for n in notice.list_for(other))


def test_detail_uses_judge_result(mock_notices, test_account):
    """상세의 판정은 목록과 같은 judge(profile) 결과를 쓴다."""
    from app.pd.notice import query_ctl
    from app.pd.user import profile

    profile.save(test_account, **PROFILE)
    items = query_ctl.request_all(test_account)["items"]
    for i in items[:5]:
        d = query_ctl.request_detail(test_account, i["notice"]["id"])
        assert d["judgement"]["verdict"] == i["verdict"]


def test_view_log_viewed_with_notice_ids(mock_notices, test_account):
    """열람 여부를 조회한다(계정, 임박): 공지 번호 목록을 주면 그 안에서만 본다 (UC6 대비)."""
    from app.pd.notice import notice, view_log

    ids = [n["id"] for n in notice.list_for(mock_notices)][:3]
    view_log.save(test_account, ids[0])
    assert ids[0] in view_log.viewed(test_account)
    assert view_log.viewed(test_account, ids) == view_log.viewed(test_account) & set(ids)
    assert ids[0] in view_log.viewed(test_account, ids[:1]) and view_log.viewed(test_account, []) == set()
