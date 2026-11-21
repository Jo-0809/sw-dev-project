"""공지수집 패키지 — 응답 해석기, 근거 대조기, 수집 제어(UC4), 조건 추출 제어."""

import json

import requests
from conftest import BASE, PROFILE

from app.pd.collect import parser, verifier

SYSTEM_NOTICE = """<html><body><div class="system_guide">
<h1>시스템안내</h1><p>요청하신 페이지를 찾을 수 없습니다.</p></div></body></html>"""
V4_DETAIL = """<html><body><div class="bbs_ViewA">
<h2>장학금 신청 안내</h2><div class="date">등록일 2026-09-28</div>
<div class="bbsV_cont"><p>신청 자격 : 평점평균 2.6 이상</p><p>자세한 내용은 첨부파일을 참고하시기 바랍니다.</p>
<table class="file_list"><tbody><tr><th>첨부파일</th><td>
<a href="/common/nttFileDownload.do?fileSn=1&amp;atchFileId=F1">신청서.hwp</a></td></tr></tbody></table>
</div></div></body></html>"""


# ------------------------------------------------------------------ 응답 해석기
def test_rss_and_list_numbers(server):
    rss = requests.get(f"{BASE}/mock/main/na/ntt/selectRssFeed.do?mi=1376&bbsId=1075").text
    nums = parser.extract_numbers_from_rss(rss)  # 시연 중 새로 올린 공지(8800108~)가 앞에 올 수 있다
    assert nums[nums.index("8800107") + 1] == "8800105"
    html = requests.get(f"{BASE}/mock/sw/na/ntt/selectNttList.do?mi=2001&bbsId=3001").text
    assert set(parser.extract_numbers_from_list(html)) == {"8800201", "8800202"}


def test_detail_and_empty_page(server):
    html = requests.get(f"{BASE}/mock/main/na/ntt/selectNttInfo.do?nttSn=8800101").text
    assert parser.check_post_area(html)
    d = parser.parse_detail(html, "u", "8800101")
    assert d["title"] == "2026 GNU SW 해커톤 참가자 모집"
    assert "본교 학부 재학생 1~3학년 (전공 무관)" in d["body"]
    assert "첨부파일을 참고" in d["body"]  # 본문 속 '첨부파일' 글자는 본문으로 남는다
    assert d["attachments"][0]["name"].endswith(".hwp") and "hwp" not in d["body"]
    assert d["posted_at"] == "2026-11-10"
    bad = requests.get(f"{BASE}/mock/main/na/ntt/selectNttInfo.do?nttSn=8800110")
    assert bad.status_code == 200 and not parser.check_post_area(bad.text)  # HTTP 200인데 게시글 영역 없음


def test_v4_rules_error_page_and_attachments():
    assert parser.check_post_area(SYSTEM_NOTICE) is False
    n = parser.parse_detail(V4_DETAIL, "https://x/na/ntt/selectNttInfo.do?nttSn=1", "1")
    assert "첨부파일을 참고" in n["body"] and "신청서.hwp" not in n["body"]
    assert [a["name"] for a in n["attachments"]] == ["신청서.hwp"]
    title_err = (
        "<html><head><title>수강신청 시스템 오류가 발생하여 일정 변경 안내</title></head><body>"
        "<div class='bbs_ViewA'><h2>수강신청 시스템 오류가 발생하여 일정 변경 안내</h2>"
        "<div class='bbsV_cont'><p>수강신청 시스템 점검으로 일정을 변경합니다.</p></div></div></body></html>"
    )
    assert parser.check_post_area(title_err) is True  # 제목의 '오류'로 실패 처리하지 않음


def test_v4_rules_listing():
    goto = (
        "<table><tbody><tr><td><a href=\"javascript:goTo.view('list','8748643','1376','');\">장학</a></td></tr>"
        "<tr><td><a href=\"javascript:goTo.view('list','8748502','1376','');\">성적</a></td></tr></tbody></table>"
    )
    assert parser.extract_numbers_from_list(goto) == ["8748643", "8748502"]
    menu = (
        "<div id='gnb'><a href=\"javascript:fn_goMenu('10200','1');\">교육과정</a></div>"
        "<table class='board_list'><tbody><tr><td><a href=\"javascript:goTo.view('list','3310221','3003','');\">"
        "동문장학금</a></td></tr></tbody></table><div class='paging'><a href='javascript:goPage(2);'>2</a></div>"
    )
    assert parser.extract_numbers_from_list(menu) == ["3310221"]
    data_id = (
        "<div id='gnb'><a href=\"javascript:fn_goMenu('10200','1');\">메뉴</a></div><table class='board_list'>"
        "<tbody><tr><td><a href='javascript:' data-id='8615327' class='nttInfoBtn'>DAAD</a></td></tr></tbody></table>"
    )
    assert parser.extract_numbers_from_list(data_id) == ["8615327"]


def _real(site, ntt):
    from app.pd.external import web

    url = f"https://www.gnu.ac.kr/{site}/na/ntt/selectNttInfo.do?nttSn={ntt}"
    return parser.parse_detail(json.loads(web._record_path(url).read_text(encoding="utf-8"))["text"], url, ntt)


def test_real_responses_parse():
    a = _real("main", "8800783")
    assert a["title"].startswith("아산사회복지재단") and "접수 기간" in a["body"] and a["posted_at"] == "2026-10-06"
    assert len(a["attachments"]) == 2 and not a["needs_review"]
    img = _real("main", "8829161")
    assert img is not None and img["needs_review"] and img["body"] == ""
    assert len(_real("main", "8540681")["attachments"]) == 4
    assert "희망사다리" in _real("ise", "8640162")["title"]


# ------------------------------------------------------------------ 근거 대조기
def test_verifier():
    body = "□ 참가 대상: 본교 2~4학년 재학생\n□ 신청 마감: 2026. 11. 20.(금) 18:00"
    r = verifier.verify(
        {
            "conditions": [
                {"item": "학년", "value": "2~4학년", "evidence": "□ 참가 대상:  본교 2~4학년 재학생"},
                {"item": "학년", "value": "3학년", "evidence": "3학년 이상 재학생"},
            ],
            "deadline": "2026-11-20 18:00",
            "deadline_evidence": "신청 마감: 2026. 11. 20.(금) 18:00",
        },
        body,
    )
    assert [c["verified"] for c in r["conditions"]] == [True, False]
    assert r["deadline_verified"]


def test_value_number_check():
    body = "지원 자격: 1, 2학년 재학생"
    r = verifier.verify(
        {
            "conditions": [
                {"item": "학년", "value": "3학년 이상", "evidence": "1, 2학년 재학생"},
                {"item": "학년", "value": "1~2학년", "evidence": "1, 2학년 재학생"},
            ]
        },
        body,
    )
    assert [c["verified"] for c in r["conditions"]] == [False, True]
    assert r["conditions"][0]["why"] == "값의 숫자가 근거와 다름"


def test_deadline_date_check():
    dm = verifier.deadline_matches
    assert dm("2026-11-21", "마감 2026.11.20") is False  # 날짜가 다르면 실패
    assert dm("2026-11-20", "마감 2026.11.20") is True  # 쓰는 방식만 다름
    assert dm("2026-11-20 18:00", "~ 11. 20.(금) 18:00까지") is True
    assert dm("2026-10-26 23:59", "2026년 10월 6일(화) ~ 10월 26일(월) 23시 59분") is True
    assert dm("2026-11-20 23:59", "~ 11. 20.(금)") is False  # 근거에 없는 시각
    assert dm("2027-11-20", "2026년 11월 20일") is False  # 연도가 다름
    assert dm("2026-11-20 17:00", "11월 20일 18시") is False  # 시각이 다름
    body = "접수: 2026. 11. 20.(금) 18:00까지"
    r = verifier.verify(
        {"deadline": "2026-11-21 18:00", "deadline_evidence": "접수: 2026. 11. 20.(금) 18:00까지", "conditions": []},
        body,
    )
    assert r["deadline_verified"] is False


def test_deadline_range_end_and_year():
    dm = verifier.deadline_matches
    ev = "신청 기간: 2026. 11. 10.(월) ~ 11. 20.(금) 18:00까지"
    assert dm("2026-11-10", ev) is False  # 접수 시작일
    assert dm("2027-11-20", ev) is False  # 연도는 앞 날짜에서 이어받음
    assert dm("2026-11-20", ev) is True
    assert dm("2026-11-20 18:00", ev) is True
    ev2 = "접수: 2026. 12. 20.(일) ~ 1. 10.(일)"
    assert dm("2027-01-10", ev2) is True  # 해를 넘기는 기간
    assert dm("2026-01-10", ev2) is False


# ------------------------------------------------------------------ 수집 제어
def test_replay_real_sources(test_account):
    """저장된 실제 응답으로 실제 게시판 5곳 수집: 10건 저장(이미지 2건은 확인 필요), 오타 게시판은 번호 확보 실패."""
    from app.pd.collect import failure
    from app.pd.collect.collect_ctl import collector
    from app.pd.notice import engine, notice
    from app.pd.source import source, subscription
    from app.pd.user import profile

    profile.save(test_account, **PROFILE)
    real = [s for s in source.all() if s["kind"] in ("preset", "test")]
    for s in real:
        subscription.save(test_account, s["id"])
    results = [collector._collect_source(s) for s in real]
    assert sum(r["new"] for r in results) == 10 and sum(r["review"] for r in results) == 2
    assert sum(r["failed"] for r in results) == 0
    typo = next(r for r in results if "오타" in r["source"])
    assert typo["error"] and "시스템안내" in typo["error"]
    assert any(f["stage"] == "번호 확보" for f in failure.recent(20))
    notices = {n["ntt_sn"]: n for n in notice.list_for([s["id"] for s in real])}
    judged = engine.judge(profile.find(test_account))  # 판정한다(프로필)
    v = {k: judged[n["id"]]["verdict"] for k, n in notices.items() if n["id"] in judged}
    # 아산재단: '의생명과학분야 관련 학과'는 넓은 표현이라 확인 필요
    assert v["8800783"] == "확인 필요" and v["8748643"] == "확인 필요" and v["8829161"] == "확인 필요"
    assert notices["8610403"]["status"] == "모집 공고 아님" and notices["8610403"]["id"] not in judged
    assert notices["8800783"]["extract_method"].startswith("예시 결과")


def test_end_source_when_no_new(test_account):
    """대안 2: 신규 공지가 없으면 이 출처의 수집을 종료한다."""
    from app.pd.collect.collect_ctl import collector
    from app.pd.source import source

    src = next(s for s in source.all() if s["kind"] == "preset" and s["bbs_id"] == "1374")
    collector._collect_source(src)
    again = collector._collect_source(src)
    assert again["new"] == 0 and again["ended"] == "새 공지 없음" and again["error"] is None


def test_one_source_error_does_not_stop_others(mock_notices, monkeypatch):
    """품질 시나리오 #2 '출처 간 연쇄 중단 0건': 첫 출처에서 예상 못 한 오류가 나도 두 번째 출처는 수집된다."""
    from app.pd.collect import failure
    from app.pd.collect.collect_ctl import collector

    seen = []
    real = collector._collect_source

    def flaky(src):
        seen.append(src["id"])
        if len(seen) == 1:
            raise AttributeError("일부러 낸 오류")
        return real(src)

    monkeypatch.setattr(collector, "_collect_source", flaky)
    out = collector.start()
    assert len(out["results"]) == len(seen) >= 2
    assert "AttributeError" in out["results"][0]["error"]
    assert all(r.get("error") is None or "AttributeError" not in r["error"] for r in out["results"][1:])
    assert any(f["stage"] == "출처" and "AttributeError" in f["reason"] for f in failure.recent(30))


def test_collect_checks_robots_every_request(monkeypatch):
    """처음부터 넣어 둔 출처도 수집할 때 요청마다 robots.txt 를 확인한다. 확인 불가면 요청하지 않는다."""
    from app.pd.collect.collect_ctl import collector
    from app.pd.external import web
    from app.pd.source import source

    asked = []
    monkeypatch.setattr(web, "read_robots", lambda url: asked.append(url) or (None, ""))
    monkeypatch.setattr(web, "_fetch", lambda url: (_ for _ in ()).throw(AssertionError("요청하면 안 됨")))
    src = next(s for s in source.all() if s["kind"] == "preset" and s["bbs_id"] == "1075")
    r = collector._collect_source(src)
    assert len(asked) == 2 and "robots.txt" in r["error"] and r["new"] == 0  # RSS, 목록 두 번 물음


def test_extract_error_marks_notice_and_continues(server, monkeypatch):
    """한 공지의 추출에서 예상 못 한 오류가 나도 그 공지만 확인 필요로 두고 다음 공지로 넘어간다."""
    from app.pd.collect import extract_ctl
    from app.pd.collect.collect_ctl import collector
    from app.pd.notice import notice
    from app.pd.source import source

    sid = source.add(
        "추출 오류 시험",
        "https://www.gnu.ac.kr/ise",
        mi="3003",
        bbs_id="1374",
        rss=0,
        list_url="https://www.gnu.ac.kr/ise/na/ntt/selectNttList.do?mi=3003&bbsId=1374",
    )
    real, calls = extract_ctl.extract, []

    def flaky(nid):
        calls.append(nid)
        if len(calls) == 1:
            raise TypeError("일부러 낸 오류")
        return real(nid)

    monkeypatch.setattr(extract_ctl, "extract", flaky)
    r = collector._collect_source(source.get(sid))
    assert r["new"] == 2 and r["extract_error"] == 1 and len(calls) == 2
    first = notice.get(calls[0])
    assert first["status"] == "확인 필요" and "추출 중 오류" in first["extract_method"]
    assert notice.get(calls[1])["status"] != "추출 대기"
    assert len(notice.list_for([sid])) == 2


# ------------------------------------------------------------------ 조건 추출 제어
def test_llm_three_failures(mock_notices, monkeypatch):
    from app.pd.collect import extract_ctl
    from app.pd.external import llm_client
    from app.pd.notice import notice

    calls = []

    def boom(title, body, provider=None, mode=None):
        calls.append(1)
        raise llm_client.LLMError("HTTP 503")

    monkeypatch.setattr(llm_client, "extract_conditions", boom)
    nid = notice.list_for(mock_notices)[0]["id"]
    extract_ctl.extract(nid)
    n = notice.get(nid)
    assert len(calls) == extract_ctl.MAX_RETRY == 3 and n["status"] == "확인 필요" and "3회 실패" in n["extract_note"]


def test_malformed_llm_response_retries_then_check(mock_notices, monkeypatch):
    """conditions 원소가 객체가 아니면 LLMError → 3회 재시도 → '확인 필요'. 예외가 밖으로 나가지 않는다."""
    from app import config
    from app.pd.collect import extract_ctl
    from app.pd.external import llm_client
    from app.pd.notice import notice

    calls = []
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_MODE", "live")
    monkeypatch.setitem(
        llm_client._CALL,
        "gemini",
        lambda t, b: calls.append(1) or {"is_recruitment": True, "conditions": ["학과 무관"]},
    )
    nid = notice.list_for(mock_notices)[0]["id"]
    extract_ctl.extract(nid)
    n = notice.get(nid)
    assert len(calls) == 3 and n["status"] == "확인 필요" and "형식 오류" in n["extract_note"]


def test_no_llm_in_production_marks_check(mock_notices, monkeypatch):
    """운영(대체 결과 제공자 없음)에서 키도 녹화도 없으면 조건을 지어내지 않고 '확인 필요' + 'LLM 미설정'."""
    from app.pd.collect import extract_ctl
    from app.pd.notice import condition, notice

    monkeypatch.setattr(extract_ctl, "_example_provider", None)
    nid = notice.list_for(mock_notices)[0]["id"]
    extract_ctl.extract(nid)
    n = notice.get(nid)
    assert n["status"] == "확인 필요" and "LLM 미설정" in n["extract_note"] and condition.find(nid) == []


def test_scheduler_runs_once_at_start(monkeypatch):
    """서버를 켜면 한 번 바로 수집한다 (첫 수집이 주기만큼 밀리지 않게). 그 뒤로는 주기마다."""
    import time
    from datetime import datetime, timedelta

    from app import config
    from app.pd.collect import collect_scheduler
    from app.pd.collect.collect_ctl import collector

    calls = []
    monkeypatch.setattr(config, "SCHEDULER_ENABLED", True)
    monkeypatch.setattr(collector, "start", lambda: calls.append(1))  # 실제 수집은 하지 않음
    sch = collect_scheduler.CollectScheduler()
    sch.start()
    try:
        for _ in range(50):
            if calls:
                break
            time.sleep(0.1)
        assert calls == [1]  # 켜자마자 한 번
        job = sch._scheduler.get_job(collect_scheduler.JOB_ID)
        expected = datetime.now(collect_scheduler.TIMEZONE) + timedelta(minutes=collect_scheduler.INTERVAL_MIN)
        assert abs((job.next_run_time - expected).total_seconds()) < 10  # 다음은 주기 뒤
    finally:
        sch.stop()


def test_verifier_accepts_title_evidence():
    """제목도 원문이다: 제목에만 있는 조건·마감일도 근거로 통과한다. 본문과 제목을 이어 붙인 가짜 문장은 안 된다."""
    title = "희망사다리 장학생 신청기간 연장 안내(~9/30, 18:00)"
    body = "신청대상: 학부 재학생"
    r = verifier.verify(
        {
            "conditions": [
                {"item": "재학 상태", "value": "학부 재학생", "evidence": "학부 재학생"},
                {"item": "기타", "value": "연장", "evidence": "18:00)신청대상"},
            ],
            "deadline": "2026-09-30 18:00",
            "deadline_evidence": "신청기간 연장 안내(~9/30, 18:00)",
        },
        body,
        title,
    )
    assert [c["verified"] for c in r["conditions"]] == [True, False] and r["deadline_verified"]
    assert (
        verifier.verify(
            {"conditions": [], "deadline": "2026-09-30 18:00", "deadline_evidence": "신청기간 연장 안내(~9/30, 18:00)"},
            body,
        )["deadline_verified"]
        is False
    )


def test_prompt_v3_title_and_academic_rule():
    """PROMPT_VERSION v3: 제목도 근거, 학사 절차 신청은 모집 공고 아님 (팀 결정 2026-11-21)."""
    from app.pd.external import llm_client

    assert llm_client.PROMPT_VERSION == "v3"
    assert "제목과 본문만 보고" in llm_client.PROMPT and "성적포기" in llm_client.PROMPT
    assert "본문만 보고" not in llm_client.PROMPT.replace("제목과 본문만 보고", "")
