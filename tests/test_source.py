"""관심출처 패키지 — 수집 허용 규칙, 출처 등록 (UC3 정상·대안 1·예외 1~3)."""

import pytest
import requests
from conftest import BASE, login


def test_robots_judge():
    from app.pd.source import robots

    rules = "User-agent: *\nDisallow: /mock/common/\nDisallow: /mock/edu/\n"
    assert robots._judge(rules, "http://x/mock/main/na/ntt/selectNttList.do?mi=1&bbsId=2")
    assert not robots._judge(rules, "http://x/mock/edu/na/ntt/selectNttList.do?mi=9001&bbsId=9999")


def test_robots_rules():
    from app.pd.source import robots

    d = robots.decide
    rules = "User-agent: *\nDisallow: /private/"
    assert d((None, ""), "https://a.example/board") == robots.UNKNOWN  # 응답 없음 → 허용 안 함
    assert d((503, ""), "https://a.example/board") == robots.UNKNOWN
    assert d((404, "Not Found"), "https://b.example/board") == robots.ALLOWED  # 404 → 규칙 없음
    assert d((200, rules), "https://c.example/private/x") == robots.BLOCKED
    assert d((200, rules), "https://c.example/board") == robots.ALLOWED


def test_register_preset_checks_robots(test_account, monkeypatch):
    from app.pd.source import robots, source, source_ctl

    monkeypatch.setattr(robots, "decide", lambda r, url: robots.BLOCKED)
    src = next(s for s in source.all() if s["kind"] == "preset")
    assert source_ctl.register(test_account, src["id"]) == (False, source_ctl.MSG_BLOCKED)


def test_register_address_without_posts(test_account):
    """UC3 예외 3: HTTP 200인데 게시글 목록이 없는 주소(게시판 번호 오타)는 등록하지 않는다."""
    from app.pd.source import source_ctl, subscription

    before = {s["id"] for s in subscription.find(test_account)}
    ok, msg, sid = source_ctl.register_address(
        test_account, "https://www.gnu.ac.kr/main/na/ntt/selectNttList.do?mi=1376&bbsId=1076"
    )
    assert (ok, msg, sid) == (False, "공지를 가져올 수 없는 주소입니다", None)
    assert {s["id"] for s in subscription.find(test_account)} == before
    ok, msg, sid = source_ctl.register_address(
        test_account, "https://www.gnu.ac.kr/main/na/ntt/selectNttList.do?mi=1376&bbsId=1075"
    )
    assert ok and sid in {s["id"] for s in subscription.find(test_account)}


def test_register_address_without_posts_mock_board(server):
    """모의 게시판의 없는 게시판 주소도 같은 메시지 (시연 시나리오 2-2)."""
    s = requests.Session()
    login(s)
    r = s.post(
        BASE + "/sources/address", data={"address": BASE + "/mock/main/na/ntt/selectNttList.do?mi=1376&bbsId=1076"}
    )
    assert "공지를 가져올 수 없는 주소입니다" in r.text


def test_register_address_reads_robots_first(test_account, monkeypatch):
    """대안 1 순서: robots.txt 를 먼저 읽는다. 응답이 아예 없으면 게시판은 요청하지 않고 예외 1."""
    from app.pd.external import web
    from app.pd.source import source_ctl

    asked = []
    monkeypatch.setattr(web, "read_robots", lambda url: asked.append(url) or (None, ""))
    monkeypatch.setattr(web, "_get", lambda url: pytest.fail("robots.txt 응답이 없으면 게시판을 요청하면 안 됨"))
    ok, msg, _ = source_ctl.register_address(
        test_account, "https://no-such.example/na/ntt/selectNttList.do?mi=1&bbsId=2"
    )
    assert (ok, msg) == (False, source_ctl.MSG_UNREACHABLE) and len(asked) == 2  # 목록·RSS 주소 두 번


def test_register_address_robots_5xx_holds(test_account, monkeypatch):
    """robots.txt 가 5xx면 규칙을 모르므로 등록 보류 (명세 밖)."""
    from app.pd.external import web
    from app.pd.source import source_ctl

    monkeypatch.setattr(web, "read_robots", lambda url: (503, ""))
    monkeypatch.setattr(web, "_get", lambda url: pytest.fail("보류면 게시판을 요청하면 안 됨"))
    ok, msg, _ = source_ctl.register_address(test_account, "https://x.example/board")
    assert (ok, msg) == (False, source_ctl.MSG_UNKNOWN)


def test_source_list_hides_demo_kinds(test_account, monkeypatch):
    """운영(DEMO_MODE=0): 출처·관심 출처 조회에서 모의·실패 확인 출처를 뺀다."""
    from app import config
    from app.pd.source import source, source_ctl, subscription

    typo = next(s for s in source.all() if s["bbs_id"] == "1076")
    mock = next(s for s in source.all() if s["kind"] == "mock")
    subscription.save(test_account, mock["id"])
    monkeypatch.setattr(config, "DEMO_MODE", False)
    assert all(s["kind"] not in ("mock", "test") for s in source.all())
    assert any(s["kind"] == "mock" for s in source.all(include_demo=True))
    assert all(s["kind"] != "mock" for s in subscription.find(test_account))
    assert all(s["kind"] != "mock" for s in subscription.registered_sources())
    available, registered = source_ctl.request_list(test_account)
    assert all(s["kind"] not in ("mock", "test") for s in available + registered)
    assert typo["kind"] == "test" and source_ctl.register(test_account, typo["id"])[0] is False


def test_find_posts_decides_in_source_ctl(server):
    """UC3 예외 3 판단(게시글 목록 있음/없음)은 출처 등록 제어가 board_html 로 한다."""
    from app.pd.source import source_ctl

    good = BASE + "/mock/sw/na/ntt/selectNttList.do?mi=2001&bbsId=3001"
    assert source_ctl._find_posts(good, None) == (True, True)
    assert source_ctl._find_posts(BASE + "/nope/x", None) == (False, False)
    typo = BASE + "/mock/main/na/ntt/selectNttList.do?mi=1376&bbsId=1076"
    rss = BASE + "/mock/main/na/ntt/selectRssFeed.do?mi=1376&bbsId=1076"
    assert source_ctl._find_posts(typo, rss) == (True, False)
