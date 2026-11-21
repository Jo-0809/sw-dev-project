"""놓칠뻔 데모 테스트 — 단위(해석기·대조기·판정 엔진·수집 허용 규칙) + 시연 시나리오 전체 흐름.

실행: python -m pytest -q
모의 게시판과 저장된 실제 응답(recordings/web)을 쓰므로 인터넷 연결 없이 돈다. API 키는 쓰지 않는다.
"""
import os
import socket
import tempfile
import threading
import time

_tmp = tempfile.mkdtemp()
_sock = socket.socket()
_sock.bind(("127.0.0.1", 0))
PORT = _sock.getsockname()[1]
_sock.close()
os.environ.update(DB_PATH=os.path.join(_tmp, "t.db"), PORT=str(PORT), SELF_URL=f"http://127.0.0.1:{PORT}",
                  SCHEDULER_ENABLED="0", GEMINI_API_KEY="", ANTHROPIC_API_KEY="", DEMO_TODAY="2026-11-16",
                  FETCH_MODE="replay", LLM_MODE="auto", LLM_PROVIDER="gemini", DEMO_MODE="1",
                  DEMO_ID="demo-t", DEMO_PASSWORD="Tq7-demo-pw",
                  LLM_RECORD_DIR=os.path.join(_tmp, "llm"))

import pytest  # noqa: E402
import requests  # noqa: E402
import uvicorn  # noqa: E402

from app import config
from app.demo import mockdata  # noqa: E402
from app.control import engine, parser, robots_rule, verifier  # noqa: E402

BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def server():
    srv = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=PORT, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        try:
            requests.get(BASE + "/login", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.1)
    from app.entity import Account
    Account.set_password("test", "test1234")               # 테스트용 두 번째 계정 (서버 밖에서만 씀)
    yield BASE
    srv.should_exit = True


# ------------------------------------------------------------------ 단위
def test_rss_and_list_numbers(server):
    rss = requests.get(f"{BASE}/mock/main/na/ntt/selectRssFeed.do?mi=1376&bbsId=1075").text
    assert parser.extract_numbers_from_rss(rss)[:2] == ["8800107", "8800105"]
    html = requests.get(f"{BASE}/mock/sw/na/ntt/selectNttList.do?mi=2001&bbsId=3001").text
    assert set(parser.extract_numbers_from_list(html)) == {"8800201", "8800202"}


def test_detail_and_empty_page(server):
    html = requests.get(f"{BASE}/mock/main/na/ntt/selectNttInfo.do?nttSn=8800101").text
    assert parser.check_post_area(html)
    d = parser.parse_detail(html, "u", "8800101")
    assert d["title"] == "2026 GNU SW 해커톤 참가자 모집"
    assert "본교 학부 재학생 1~3학년 (전공 무관)" in d["body"]
    assert "첨부파일을 참고" in d["body"]                 # 본문 속 '첨부파일' 글자는 본문으로 남는다
    assert d["attachments"][0]["name"].endswith(".hwp") and "hwp" not in d["body"]
    assert d["posted_at"] == "2026-11-10"
    bad = requests.get(f"{BASE}/mock/main/na/ntt/selectNttInfo.do?nttSn=8800110")
    assert bad.status_code == 200 and not parser.check_post_area(bad.text)   # HTTP 200인데 게시글 영역 없음


def test_verifier():
    body = "□ 참가 대상: 본교 2~4학년 재학생\n□ 신청 마감: 2026. 11. 20.(금) 18:00"
    r = verifier.verify({"conditions": [{"item": "학년", "value": "2~4학년", "evidence": "□ 참가 대상:  본교 2~4학년 재학생"},
                                        {"item": "학년", "value": "3학년", "evidence": "3학년 이상 재학생"}],
                         "deadline": "2026-11-20 18:00", "deadline_evidence": "신청 마감: 2026. 11. 20.(금) 18:00"}, body)
    assert [c["verified"] for c in r["conditions"]] == [True, False]
    assert r["deadline_verified"]


@pytest.mark.parametrize("item,value,expect", [
    ("학년", "1~3학년", "충족"), ("학년", "4학년", "불충족"), ("학년", "2학년 이상", "충족"), ("학년", "학년 무관", "충족"),
    ("학과", "전공 무관", "충족"), ("학과", "소프트웨어공학과", "충족"), ("학과", "기계공학부", "불충족"),
    ("학과", "공과대학 소속", "확인 필요"), ("재학 상태", "재학생 (휴학생 제외)", "충족"),
    ("소속 대학", "경상국립대학교 (본교)", "충족"), ("기타", "평점 3.5 이상", "확인 필요"),
])
def test_engine_items(item, value, expect):
    prof = {"university": "경상국립대학교", "department": "소프트웨어공학과", "grade": 2, "status": "재학"}
    assert engine._match_item(item, value, prof)[0] == expect


def test_robots():
    rules = "User-agent: *\nDisallow: /mock/common/\nDisallow: /mock/edu/\n"
    assert robots_rule.judge(rules, "http://x/mock/main/na/ntt/selectNttList.do?mi=1&bbsId=2")
    assert not robots_rule.judge(rules, "http://x/mock/edu/na/ntt/selectNttList.do?mi=9001&bbsId=9999")


# ------------------------------------------------------------------ 시연 시나리오 (UC1 → UC2 → UC3 → UC4 → UC5)
def test_full_scenario(server):
    s = requests.Session()
    # UC1 예외 2, 예외 1, 정상
    assert "필수 항목을 입력하세요" in s.post(BASE + "/login", data={"login_id": "", "password": ""}).text
    assert "올바르지 않습니다" in s.post(BASE + "/login", data={"login_id": "demo-t", "password": "x"}).text
    r = s.post(BASE + "/login", data={"login_id": "demo-t", "password": "Tq7-demo-pw", "auto": "on"})
    assert r.url.endswith("/profile?first=1")             # UC5 예외 1 → 2-1
    assert "프로필을 먼저 입력하세요" in r.text
    # UC2 예외 1 → 정상
    assert "학과와 학년은 반드시" in s.post(BASE + "/profile", data={"first": 1, "status": "재학"}).text
    r = s.post(BASE + "/profile", data={"first": 1, "university": "경상국립대학교", "department": "소프트웨어공학과",
                                        "grade": "2", "status": "재학"})
    assert "관심 출처를 먼저 등록하세요" in r.text          # 5-6 (관심 출처 없음)
    # UC3 예외 1, 예외 2, 정상
    t = s.post(BASE + "/sources/address", data={"address": BASE + "/nope/na/ntt/selectNttList.do?mi=1&bbsId=2"}).text
    assert "해당 주소에 접속할 수 없습니다" in t
    t = s.post(BASE + "/sources/address",
               data={"address": BASE + "/mock/edu/na/ntt/selectNttList.do?mi=9001&bbsId=9999"}).text
    assert "수집이 허용되지 않는 게시판입니다" in t
    from app.entity import Source
    mock_ids = [x["id"] for x in Source.all() if "[모의]" in x["name"]]
    s.post(BASE + "/sources/register", data={"source_ids": mock_ids})
    # UC4: 수집 (동기 실행)
    from app.control import collect_ctl
    res = collect_ctl.start()["results"]
    assert sum(r["new"] for r in res) == 9 and sum(r["failed"] for r in res) == 1
    assert {r["path"] for r in res} == {"RSS", "목록 HTML"}
    # UC5
    from app.control import query_ctl
    aid = 1
    lst = query_ctl.request_list(aid, "possible")
    titles = [i["notice"]["title"] for i in lst["items"]]
    assert titles == ["소프트웨어공학과 전공 멘토링 멘티 모집", "2026 GNU SW 해커톤 참가자 모집",
                      "2026 동계 해외 단기연수 프로그램 참가자 모집", "2027학년도 1학기 교환학생 선발 공고"]
    allv = {i["notice"]["title"]: i["verdict"] for i in query_ctl.request_list(aid, "all")["items"]}
    assert allv["2026 동계 산학협력 현장실습(인턴십) 참여 학생 모집"] == "지원 불가"
    assert allv["대학 홍보 서포터즈 '경상누리' 7기 모집"] == "확인 필요"
    assert allv["2027학년도 1학기 학습 튜터링 튜터 모집"] == "확인 필요"
    assert allv["2026학년도 2학기 국가근로장학생 선발 명단 안내"] == "모집 공고 아님"
    # 상세 + 열람 기록
    nid = lst["items"][1]["notice"]["id"]
    page = s.get(f"{BASE}/notices/{nid}").text
    assert "지원할 수 있어요" in page and "원문 공지 보기" in page
    assert query_ctl.request_list(aid, "possible")["items"][1]["viewed"]
    # 새 공지 게시 → 다시 수집 → 1건만 추가(중복 없음)
    mockdata.publish("8800108")
    res = collect_ctl.start()["results"]
    assert sum(r["new"] for r in res) == 1
    # LLM이 원문에 없는 조건을 낸 경우 → 근거 대조기가 걸러 확인 필요
    mockdata.publish("8800109")
    collect_ctl.start()
    allv = {i["notice"]["title"]: i for i in query_ctl.request_list(aid, "all")["items"]}
    x = allv["○○장학재단 2027년도 장학생 모집"]
    assert x["verdict"] == "확인 필요" and "원문에 근거 없음" in x["notice"]["extract_note"]
    assert len(query_ctl.request_list(aid, "possible")["items"]) == 5


def test_rule_based_fallback():
    from app.control.extract_ctl import rule_based
    p = next(x for x in mockdata.POSTS if x["ntt"] == "8800105")
    r = rule_based(p["title"], mockdata.render(p["body"]))
    items = {c["item"]: c["value"] for c in r["conditions"]}
    assert r["is_recruitment"] and r["deadline"].startswith("2026-11-25")
    assert items["학년"].replace(" ", "") == "2학년이상" and items["학과"] == "전공 무관"
    q = next(x for x in mockdata.POSTS if x["ntt"] == "8800107")
    assert rule_based(q["title"], mockdata.render(q["body"]))["is_recruitment"] is False


def test_llm_three_failures(server, monkeypatch):
    from app.boundary import llm_client
    from app.control import extract_ctl
    from app.entity import Notice
    calls = []

    def boom(title, body, provider=None, mode=None):
        calls.append(1)
        raise llm_client.LLMError("HTTP 503")
    monkeypatch.setattr(llm_client, "extract_conditions", boom)
    from app.entity import Source
    mock_ids = [x["id"] for x in Source.all() if x["kind"] == "mock"]
    nid = Notice.list_for(mock_ids)[0]["id"]
    extract_ctl.extract(nid)
    n = Notice.get(nid)
    assert len(calls) == 3 and n["status"] == "확인 필요" and "3회 실패" in n["extract_note"]


# ====================================================================== v2: 수집기 v4 규칙 · 실제 응답 · LLM 녹화 · 채점
SYSTEM_NOTICE = """<html><body><div class="system_guide">
<h1>시스템안내</h1><p>요청하신 페이지를 찾을 수 없습니다.</p></div></body></html>"""
V4_DETAIL = """<html><body><div class="bbs_ViewA">
<h2>장학금 신청 안내</h2><div class="date">등록일 2026-09-28</div>
<div class="bbsV_cont"><p>신청 자격 : 평점평균 2.6 이상</p><p>자세한 내용은 첨부파일을 참고하시기 바랍니다.</p>
<table class="file_list"><tbody><tr><th>첨부파일</th><td>
<a href="/common/nttFileDownload.do?fileSn=1&amp;atchFileId=F1">신청서.hwp</a></td></tr></tbody></table>
</div></div></body></html>"""


def test_v4_rules_error_page_and_attachments():
    assert parser.check_post_area(SYSTEM_NOTICE) is False
    n = parser.parse_detail(V4_DETAIL, "https://x/na/ntt/selectNttInfo.do?nttSn=1", "1")
    assert "첨부파일을 참고" in n["body"] and "신청서.hwp" not in n["body"]
    assert [a["name"] for a in n["attachments"]] == ["신청서.hwp"]
    title_err = ("<html><head><title>수강신청 시스템 오류가 발생하여 일정 변경 안내</title></head><body>"
                 "<div class='bbs_ViewA'><h2>수강신청 시스템 오류가 발생하여 일정 변경 안내</h2>"
                 "<div class='bbsV_cont'><p>수강신청 시스템 점검으로 일정을 변경합니다.</p></div></div></body></html>")
    assert parser.check_post_area(title_err) is True          # 제목의 '오류'로 실패 처리하지 않음


def test_v4_rules_listing():
    goto = ("<table><tbody><tr><td><a href=\"javascript:goTo.view('list','8748643','1376','');\">장학</a></td></tr>"
            "<tr><td><a href=\"javascript:goTo.view('list','8748502','1376','');\">성적</a></td></tr></tbody></table>")
    assert parser.extract_numbers_from_list(goto) == ["8748643", "8748502"]
    menu = ("<div id='gnb'><a href=\"javascript:fn_goMenu('10200','1');\">교육과정</a></div>"
            "<table class='board_list'><tbody><tr><td><a href=\"javascript:goTo.view('list','3310221','3003','');\">"
            "동문장학금</a></td></tr></tbody></table><div class='paging'><a href='javascript:goPage(2);'>2</a></div>")
    assert parser.extract_numbers_from_list(menu) == ["3310221"]
    data_id = ("<div id='gnb'><a href=\"javascript:fn_goMenu('10200','1');\">메뉴</a></div><table class='board_list'><tbody>"
               "<tr><td><a href='javascript:' data-id='8615327' class='nttInfoBtn'>DAAD</a></td></tr></tbody></table>")
    assert parser.extract_numbers_from_list(data_id) == ["8615327"]


def _real(site, ntt):
    import json as _j
    from app.boundary import web_client
    url = f"https://www.gnu.ac.kr/{site}/na/ntt/selectNttInfo.do?nttSn={ntt}"
    return parser.parse_detail(_j.loads(web_client._record_path(url).read_text(encoding="utf-8"))["text"], url, ntt)


def test_real_responses_parse():
    a = _real("main", "8800783")
    assert a["title"].startswith("아산사회복지재단") and "접수 기간" in a["body"] and a["posted_at"] == "2026-10-06"
    assert len(a["attachments"]) == 2 and not a["needs_review"]
    img = _real("main", "8829161")
    assert img is not None and img["needs_review"] and img["body"] == ""
    assert len(_real("main", "8540681")["attachments"]) == 4
    assert "희망사다리" in _real("ise", "8640162")["title"]


def test_engine_v2_rules():
    p = {"university": "경상국립대학교", "department": "소프트웨어공학과", "grade": 2, "status": "재학"}
    assert engine._match_item("학년", "2학년 2학기 이상", p)[0] == engine.CHECK
    assert engine._match_item("학년", "2학년 2학기 이상", {**p, "grade": 3})[0] == engine.OK
    assert engine._match_item("학과", "전공 불문", p)[0] == engine.OK
    assert engine._match_item("학과", "의생명과학분야 관련 학과", p)[0] == engine.CHECK   # 넓은 표현 → 확인 필요


def test_replay_real_sources(server):
    """저장된 실제 응답으로 실제 게시판 5곳 수집: 10건 저장(이미지 2건은 확인 필요), 오타 게시판은 번호 확보 실패."""
    from app.control import collect_ctl, engine as eng
    from app.entity import Account, Condition, FailureLog, Notice, Profile, Source, Subscription
    aid = Account.match("test", "test1234")
    aid = aid if isinstance(aid, int) else aid["id"]
    Profile.save(aid, "경상국립대학교", "소프트웨어공학과", 2, "재학")
    real = [s for s in Source.all() if s["kind"] in ("preset", "test")]
    for s in real:
        Subscription.save(aid, s["id"])
    results = [collect_ctl.collect_source(s) for s in real]
    assert sum(r["new"] for r in results) == 10 and sum(r["review"] for r in results) == 2
    assert sum(r["failed"] for r in results) == 0
    typo = next(r for r in results if "오타" in r["source"])
    assert typo["error"] and "시스템안내" in typo["error"]
    assert any(f["stage"] == "번호 확보" for f in FailureLog.recent(20))
    notices = {n["ntt_sn"]: n for n in Notice.list_for([s["id"] for s in real])}
    prof = Profile.find(aid)
    v = {k: eng.judge_one(prof, n, Condition.find(n["id"]))["verdict"] for k, n in notices.items()
         if n["status"] != "모집 공고 아님"}
    # 아산재단: '의생명과학분야 관련 학과'는 넓은 표현이라 확인 필요 (학과 판정 규칙 변경 뒤)
    assert v["8800783"] == "확인 필요" and v["8748643"] == "확인 필요" and v["8829161"] == "확인 필요"
    assert notices["8610403"]["status"] == "모집 공고 아님"
    assert notices["8800783"]["extract_method"].startswith("예시 결과")


def test_llm_record_then_replay(monkeypatch):
    from app.boundary import llm_client
    calls = []
    resp = {"is_recruitment": True, "deadline": None, "deadline_evidence": None,
            "conditions": [{"item": "학년", "value": "1~3학년", "evidence": "1~3학년"}]}
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setitem(llm_client._CALL, "gemini", lambda t, b: calls.append(1) or resp)
    d1, i1 = llm_client.extract_conditions("녹화 시험", "본문 1~3학년", provider="gemini", mode="auto")
    d2, i2 = llm_client.extract_conditions("녹화 시험", "본문 1~3학년", provider="gemini", mode="auto")
    assert i1["how"] == "live" and i2["how"] == "replay" and len(calls) == 1 and d2 == resp
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with pytest.raises(llm_client.NotAvailable):
        llm_client.extract_conditions("녹화 없음", "다른 본문", provider="gemini", mode="replay")


def test_anthropic_request_shape(monkeypatch):
    from app.boundary import llm_client
    seen = {}

    class R:
        status_code = 200

        def json(self):
            return {"content": [{"type": "tool_use", "name": "report_conditions",
                                 "input": {"is_recruitment": False, "conditions": []}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json)
        return R()
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    data, info = llm_client.extract_conditions("제목", "본문", provider="anthropic", mode="live")
    assert data["is_recruitment"] is False and info["how"] == "live"
    assert seen["url"].endswith("/v1/messages") and seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["body"]["tool_choice"] == {"type": "tool", "name": "report_conditions"}


def test_evaluation_rule_baseline():
    from app.demo import evaluation
    r = evaluation.run_method("rule")
    s = r["summary"]
    assert s["sample_total"] == 10 and s["excluded"] == 2 and s["scored"] == 8
    assert s["verdict_acc"] is not None and s["fabricated"] >= 0



# ====================================================================== v2.1: 조원 피드백 반영
def test_one_source_error_does_not_stop_others(server, monkeypatch):
    """품질 시나리오 #2 '출처 간 연쇄 중단 0건': 첫 출처에서 예상 못 한 오류가 나도 두 번째 출처는 수집된다."""
    from app.control import collect_ctl
    from app.entity import FailureLog
    seen = []
    real = collect_ctl.collect_source

    def flaky(source):
        seen.append(source["id"])
        if len(seen) == 1:
            raise AttributeError("일부러 낸 오류")
        return real(source)
    monkeypatch.setattr(collect_ctl, "collect_source", flaky)
    out = collect_ctl.start()
    assert len(out["results"]) == len(seen) >= 2
    assert "AttributeError" in out["results"][0]["error"]
    assert all(r.get("error") is None or "AttributeError" not in r["error"] for r in out["results"][1:])
    assert any(f["stage"] == "출처" and "AttributeError" in f["reason"] for f in FailureLog.recent(30))


def test_malformed_llm_response_retries_then_check(server, monkeypatch):
    """conditions 원소가 객체가 아니면 LLMError → 3회 재시도 → '확인 필요'. 예외가 밖으로 나가지 않는다."""
    from app.boundary import llm_client
    from app.control import extract_ctl
    from app.entity import Notice, Source
    calls = []
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_MODE", "live")
    monkeypatch.setitem(llm_client._CALL, "gemini",
                        lambda t, b: calls.append(1) or {"is_recruitment": True, "conditions": ["학과 무관"]})
    mock_ids = [x["id"] for x in Source.all() if x["kind"] == "mock"]
    nid = Notice.list_for(mock_ids)[0]["id"]
    extract_ctl.extract(nid)
    n = Notice.get(nid)
    assert len(calls) == 3 and n["status"] == "확인 필요" and "형식 오류" in n["extract_note"]


def test_extract_error_marks_notice_and_continues(server, monkeypatch):
    """한 공지의 추출에서 예상 못 한 오류가 나도 그 공지만 확인 필요로 두고 다음 공지로 넘어간다."""
    from app.control import collect_ctl, extract_ctl
    from app.entity import Notice, Source
    sid = Source.add("추출 오류 시험", "https://www.gnu.ac.kr/ise", mi="3003", bbs_id="1374", rss=0,
                     list_url="https://www.gnu.ac.kr/ise/na/ntt/selectNttList.do?mi=3003&bbsId=1374", kind="custom")
    real, calls = extract_ctl.extract, []

    def flaky(nid):
        calls.append(nid)
        if len(calls) == 1:
            raise TypeError("일부러 낸 오류")
        return real(nid)
    monkeypatch.setattr(extract_ctl, "extract", flaky)
    r = collect_ctl.collect_source(Source.get(sid))
    notices = Notice.list_for([sid])
    assert r["new"] == 2 and r["extract_error"] == 1 and len(calls) == 2
    first = Notice.get(calls[0])
    assert first["status"] == "확인 필요" and "추출 중 오류" in first["extract_method"]
    assert Notice.get(calls[1])["status"] != "추출 대기"
    assert len(notices) == 2


def test_dept_rules_feedback_table():
    p = {"university": "경상국립대학교", "department": "소프트웨어공학과", "grade": 2, "status": "재학"}
    m = lambda v: engine._match_item("학과", v, p)[0]
    assert m("SW 관련 학과") == engine.OK
    assert m("컴퓨터·소프트웨어 관련 학과") == engine.OK
    assert m("IT계열 학과") == engine.OK
    assert m("소프트웨어학과") == engine.CHECK
    assert m("컴퓨터소프트웨어공학과") == engine.CHECK          # 이름 일부만 겹침 → 충족으로 보지 않음
    assert m("기계공학과, 항공우주공학과") == engine.NO
    assert m("UNIT 관련 학과") == engine.CHECK                 # 영문 약어는 단어 단위로만


def test_grades_ignore_school_year():
    assert engine._grades("2026학년도 2학기 재학생") is None   # 2026학년도의 6을 6학년으로 읽지 않음
    assert engine._grades("2026학년도 1, 2학년") == {1, 2}


def test_value_number_check():
    from app.control import verifier
    body = "지원 자격: 1, 2학년 재학생"
    r = verifier.verify({"conditions": [{"item": "학년", "value": "3학년 이상", "evidence": "1, 2학년 재학생"},
                                        {"item": "학년", "value": "1~2학년", "evidence": "1, 2학년 재학생"}]}, body)
    assert [c["verified"] for c in r["conditions"]] == [False, True]
    assert r["conditions"][0]["why"] == "값의 숫자가 근거와 다름"


def test_robots_rules():
    from app.control import robots_rule
    d = robots_rule.decide
    rules = "User-agent: *\nDisallow: /private/"
    assert d((None, ""), "https://a.example/board") == robots_rule.UNKNOWN          # 응답 없음 → 허용 안 함
    assert d((503, ""), "https://a.example/board") == robots_rule.UNKNOWN
    assert d((404, "Not Found"), "https://b.example/board") == robots_rule.ALLOWED  # 404 → 규칙 없음
    assert d((200, rules), "https://c.example/private/x") == robots_rule.BLOCKED
    assert d((200, rules), "https://c.example/board") == robots_rule.ALLOWED


def test_collect_checks_robots_every_request(monkeypatch):
    """처음부터 넣어 둔 출처도 수집할 때 요청마다 robots.txt 를 확인한다. 확인 불가면 요청하지 않는다."""
    from app.boundary import web_client
    from app.control import collect_ctl
    from app.entity import Source
    asked = []
    monkeypatch.setattr(web_client, "read_robots", lambda url: asked.append(url) or (None, ""))
    monkeypatch.setattr(web_client, "_fetch", lambda url: (_ for _ in ()).throw(AssertionError("요청하면 안 됨")))
    src = next(s for s in Source.all() if s["kind"] == "preset" and s["bbs_id"] == "1075")
    r = collect_ctl.collect_source(src)
    assert len(asked) == 2 and "robots.txt" in r["error"] and r["new"] == 0       # RSS, 목록 두 번 물음


def test_register_preset_checks_robots(monkeypatch):
    from app.control import robots_rule, source_ctl
    from app.entity import Account, Source
    monkeypatch.setattr(robots_rule, "decide", lambda robots, url: robots_rule.BLOCKED)
    aid = Account.match("test", "test1234")
    src = next(s for s in Source.all() if s["kind"] == "preset")
    assert source_ctl.register(aid, src["id"]) == (False, source_ctl.MSG_BLOCKED)


def test_demo_reset_only_in_demo_mode(server, monkeypatch):
    s = requests.Session()
    s.post(BASE + "/login", data={"login_id": "test", "password": "test1234"})
    monkeypatch.setattr(config, "DEMO_MODE", False)
    assert s.post(BASE + "/demo/reset", allow_redirects=False).status_code == 404



# ====================================================================== v2.2: 2차 피드백 반영
def test_rss_without_lxml(monkeypatch):
    """lxml 이 없는 PC: BeautifulSoup 'xml' 해석기가 없어도 표준 라이브러리로 RSS 번호를 읽는다."""
    from bs4 import FeatureNotFound
    real_bs = parser.BeautifulSoup

    def no_xml(markup, features=None, *a, **k):
        if features == "xml":
            raise FeatureNotFound("lxml 없음 (흉내)")
        return real_bs(markup, features, *a, **k)
    monkeypatch.setattr(parser, "BeautifulSoup", no_xml)
    rss = ("<?xml version='1.0' encoding='UTF-8'?><rss><channel><item><title>a</title>"
           "<link>https://x/na/ntt/selectNttInfo.do?nttSn=8800783&amp;mi=1376</link></item></channel></rss>")
    assert parser.extract_numbers_from_rss(rss) == ["8800783"]
    assert parser.extract_numbers_from_rss("<rss><item><link>https://x/?nttSn=12345</link></item") == ["12345"]


def test_requirements_has_lxml():
    from pathlib import Path
    req = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
    assert "lxml" in req


def test_production_mode_hides_demo(monkeypatch):
    """DEMO_MODE=0: 예시 결과를 쓰지 않고, 모의·실패 확인 출처를 목록·수집에서 빼고, 비교 화면을 닫는다."""
    from app.control import extract_ctl, source_ctl
    from app.entity import Account, Source
    monkeypatch.setattr(config, "DEMO_MODE", False)
    n = {"url": "https://www.gnu.ac.kr/main/na/ntt/selectNttInfo.do?nttSn=8800783", "ntt_sn": "8800783"}
    assert extract_ctl._example_result(n) is None
    aid = Account.match("test", "test1234")
    available, registered = source_ctl.request_list(aid)
    assert all(s["kind"] not in ("mock", "test") for s in available + registered)
    typo = next(s for s in Source.all() if s["bbs_id"] == "1076")
    assert typo["kind"] == "test" and source_ctl.register(aid, typo["id"])[0] is False
    assert requests.get(BASE + "/compare", allow_redirects=False).status_code == 404


def test_create_account_tool_and_login_hint(monkeypatch, tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "DB_PATH": str(tmp_path / "x.db"), "PYTHONUTF8": "1"}
    code = ("import getpass,runpy,sys; getpass.getpass=lambda p='': 'pass12345'; "
            f"sys.argv=['create_account.py','admin']; runpy.run_path(r'{root / 'tools' / 'create_account.py'}', run_name='__main__')")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=root)
    assert "계정을 만들었습니다" in out.stdout, out.stderr
    from app.entity import Account
    monkeypatch.setattr(Account, "count", staticmethod(lambda: 0))
    assert "아직 계정이 없어요" in requests.get(BASE + "/login").text


def test_exclusion_conditions():
    p = {"university": "경상국립대학교", "department": "소프트웨어공학과", "grade": 2, "status": "재학"}
    m = lambda i, v, pr=p: engine._match_item(i, v, pr)[0]
    assert m("학과", "소프트웨어공학과 제외") == engine.NO
    assert m("학과", "의과대학 제외 전 학과") == engine.OK
    assert m("학과", "의학계열 제외") == engine.CHECK
    assert m("학년", "1학년 제외") == engine.OK
    assert m("학년", "2학년 제외") == engine.NO
    assert m("소속 대학", "경상국립대학교 제외") == engine.NO
    assert m("학과", "제한 없음") == engine.OK                    # '제한 없음'은 제외가 아님


def test_dept_partial_needs_two_chars():
    p = {"university": "경상국립대학교", "department": "경영학과", "grade": 2, "status": "재학"}
    assert engine._match_item("학과", "경제학부", p)[0] == engine.NO       # '경' 한 글자로 겹침 판정하지 않음
    q = {**p, "department": "항공우주공학과"}
    assert engine._match_item("학과", "항공우주공학부", q)[0] == engine.CHECK



# ====================================================================== v2.3: 3차 피드백 반영
def test_deadline_date_check():
    from app.control import verifier
    dm = verifier.deadline_matches
    assert dm("2026-11-21", "마감 2026.11.20") is False                 # 날짜가 다르면 실패
    assert dm("2026-11-20", "마감 2026.11.20") is True                  # 쓰는 방식만 다름
    assert dm("2026-11-20 18:00", "~ 11. 20.(금) 18:00까지") is True
    assert dm("2026-10-26 23:59", "2026년 10월 6일(화) ~ 10월 26일(월) 23시 59분") is True
    assert dm("2026-11-20 23:59", "~ 11. 20.(금)") is False             # 근거에 없는 시각
    assert dm("2027-11-20", "2026년 11월 20일") is False                # 연도가 다름
    assert dm("2026-11-20 17:00", "11월 20일 18시") is False            # 시각이 다름
    body = "접수: 2026. 11. 20.(금) 18:00까지"
    r = verifier.verify({"deadline": "2026-11-21 18:00", "deadline_evidence": "접수: 2026. 11. 20.(금) 18:00까지",
                         "conditions": []}, body)
    assert r["deadline_verified"] is False


def test_check_ratio_metric():
    from app.demo import evaluation
    s = evaluation.run_method("rule")["summary"]
    assert s["check_ratio"] is not None and 0 <= s["check_ratio"] <= 100
    assert evaluation.TARGETS["check_ratio"] == "10% 이하"


# ====================================================================== v2.4: 4차 피드백 반영
def test_exclusion_of_other_groups():
    """'휴학생·졸업예정자·대학원생 제외'는 그 항목의 제외가 아니다. 지원 가능한 공고를 지원 불가로 숨기지 않는다."""
    p = {"university": "경상국립대학교", "department": "소프트웨어공학과", "grade": 2, "status": "재학"}
    m = lambda i, v: engine._match_item(i, v, p)[0]
    assert m("학년", "2~4학년 (휴학생 제외)") == engine.OK
    assert m("학년", "2학년 이상 재학생(졸업예정자 제외)") == engine.OK
    assert m("학과", "소프트웨어공학과 재학생 (휴학생 제외)") == engine.OK
    assert m("소속 대학", "경상국립대학교 재학생(휴학생 제외)") == engine.OK
    assert m("학과", "소프트웨어공학과 제외") == engine.NO
    assert m("학과", "전 학과 (대학원생 제외)") == engine.OK
    assert m("학년", "2학년 이상, 휴학생 제외") == engine.OK           # 쉼표 뒤 다른 종류는 따로 끊는다
    assert m("학년", "1~4학년 (2학년 제외)") == engine.NO
    assert m("학과", "기계공학과, 소프트웨어공학과 제외") == engine.NO  # 쉼표로 이어진 같은 종류는 함께 제외


def test_deadline_range_end_and_year():
    from app.control import verifier
    dm = verifier.deadline_matches
    ev = "신청 기간: 2026. 11. 10.(월) ~ 11. 20.(금) 18:00까지"
    assert dm("2026-11-10", ev) is False              # 접수 시작일
    assert dm("2027-11-20", ev) is False              # 연도는 앞 날짜에서 이어받음
    assert dm("2026-11-20", ev) is True
    assert dm("2026-11-20 18:00", ev) is True
    ev2 = "접수: 2026. 12. 20.(일) ~ 1. 10.(일)"
    assert dm("2027-01-10", ev2) is True              # 해를 넘기는 기간
    assert dm("2026-01-10", ev2) is False


def test_register_address_without_posts():
    """UC3 예외 3: HTTP 200인데 게시글 목록이 없는 주소(게시판 번호 오타)는 등록하지 않는다."""
    from app.control import source_ctl
    from app.entity import Account, Subscription
    aid = Account.match("test", "test1234")
    before = {s["id"] for s in Subscription.find(aid)}
    ok, msg, sid = source_ctl.register_address(
        aid, "https://www.gnu.ac.kr/main/na/ntt/selectNttList.do?mi=1376&bbsId=1076")
    assert (ok, msg, sid) == (False, "공지를 가져올 수 없는 주소입니다", None)
    assert {s["id"] for s in Subscription.find(aid)} == before
    ok, msg, sid = source_ctl.register_address(
        aid, "https://www.gnu.ac.kr/main/na/ntt/selectNttList.do?mi=1376&bbsId=1075")
    assert ok and sid in {s["id"] for s in Subscription.find(aid)}


def test_register_address_without_posts_mock_board(server):
    """모의 게시판의 없는 게시판 주소도 같은 메시지 (시연 시나리오 2-2)."""
    s = requests.Session()
    s.post(BASE + "/login", data={"login_id": "test", "password": "test1234"})
    r = s.post(BASE + "/sources/address",
               data={"address": BASE + "/mock/main/na/ntt/selectNttList.do?mi=1376&bbsId=1076"})
    assert "공지를 가져올 수 없는 주소입니다" in r.text



# ====================================================================== v2.5: 시연 계정 변경
def test_demo_account_changed(server, tmp_path, monkeypatch):
    """흔한 비밀번호(demo/demo1234)는 브라우저가 '유출된 비밀번호'로 경고한다. 시연 계정은 .env 값 또는 무작위."""
    from app import main
    from app.entity import Account
    assert Account.match("demo-t", "Tq7-demo-pw")
    Account.set_password("demo", "demo1234")                 # 예전 판 DB 흉내
    main.seed()
    assert Account.match("demo", "demo1234") is None         # 예전 시연 계정은 더 이상 로그인 안 됨
    assert Account.match("demo-t", "Tq7-demo-pw")
    page = requests.get(BASE + "/login")
    assert page.status_code == 200 and "demo-t" in page.text and "demo1234" not in page.text
    from pathlib import Path
    monkeypatch.setattr(config, "DEMO_PASSWORD", "")
    monkeypatch.setattr(config, "DB_PATH", Path(tmp_path / "x.db"))
    i1, p1 = config.demo_credentials()
    i2, p2 = config.demo_credentials()
    assert p1 == p2 and len(p1) >= 10 and p1 not in ("demo1234", "test1234")
    assert (tmp_path / "demo_account.txt").exists()



# ====================================================================== v2.6: 로그인 세션
def test_session_expiry_uses_real_clock(monkeypatch):
    """DEMO_TODAY로 날짜를 고정해도 로그인 세션은 실제 시각으로 만료된다."""
    from datetime import datetime, timedelta
    from app.entity import Account, LoginSession
    Account.set_password("sess", "sess-pw-123")
    aid = Account.match("sess", "sess-pw-123")
    token = LoginSession.create(aid, auto_login=False)
    assert LoginSession.find(token)
    later = datetime.now() + timedelta(days=2)
    monkeypatch.setattr(config, "real_now", lambda: later)
    assert LoginSession.find(token) is None


def test_password_change_ends_sessions():
    from app.entity import Account, LoginSession
    Account.set_password("pwchange", "first-pw-123")
    aid = Account.match("pwchange", "first-pw-123")
    token = LoginSession.create(aid, auto_login=True)
    Account.set_password("pwchange", "first-pw-123")         # 같은 비밀번호: 세션 유지
    assert LoginSession.find(token)
    Account.set_password("pwchange", "second-pw-456")        # 바뀐 비밀번호: 세션 끊김
    assert LoginSession.find(token) is None
    assert Account.match("pwchange", "second-pw-456") == aid


# ====================================================================== v2.7: 구분 기호 없이 붙여 쓴 '제외'
def test_exclusion_without_separators():
    """괄호·쉼표 없이 이어 써도 '제외' 바로 앞의 같은 종류 낱말만 제외 대상으로 본다."""
    p = {"university": "경상국립대학교", "department": "소프트웨어공학과", "grade": 2, "status": "재학"}
    m = lambda i, v: engine._match_item(i, v, p)[0]
    assert m("학년", "2학년 이상 휴학생 제외") == engine.OK
    assert m("학과", "소프트웨어공학과 휴학생 제외") == engine.OK
    assert m("학과", "소프트웨어공학과 재학생 중 휴학생은 제외") == engine.OK
    assert m("소속 대학", "경상국립대학교 휴학생 제외") == engine.OK
    assert m("학년", "1학년 및 2학년 제외") == engine.NO              # '및'으로 이은 같은 종류는 함께
    assert m("학과", "기계공학과 소프트웨어공학과 제외") == engine.NO    # 띄어쓰기로 이은 같은 종류도 함께
    assert m("학과", "전 학과 (의예과 제외)") == engine.OK
    assert m("학년", "2~4학년 재학생, 휴학생 제외") == engine.OK
