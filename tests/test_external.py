"""외부 패키지 — 홈페이지 연결(접속 확인), 게시판 HTML 읽기, LLM API 연결."""

import pytest
from conftest import BASE


def test_check_reachable_states(server):
    """접속을 확인한다(주소): ok / unreachable(예외 1) / no_posts(예외 3)."""
    from app.pd.external import web

    good = BASE + "/mock/sw/na/ntt/selectNttList.do?mi=2001&bbsId=3001"
    assert web.check_reachable(good) == web.OK
    assert web.check_reachable(BASE + "/nope/na/ntt/selectNttList.do?mi=1&bbsId=2") == web.UNREACHABLE
    typo = BASE + "/mock/main/na/ntt/selectNttList.do?mi=1376&bbsId=1076"
    assert web.check_reachable(typo, BASE + "/mock/main/na/ntt/selectRssFeed.do?mi=1376&bbsId=1076") == web.NO_POSTS


def test_rss_without_lxml(monkeypatch):
    """lxml 이 없는 PC: BeautifulSoup 'xml' 해석기가 없어도 표준 라이브러리로 RSS 번호를 읽는다."""
    from bs4 import FeatureNotFound

    from app.pd.external import board_html

    real_bs = board_html.BeautifulSoup

    def no_xml(markup, features=None, *a, **k):
        if features == "xml":
            raise FeatureNotFound("lxml 없음 (흉내)")
        return real_bs(markup, features, *a, **k)

    monkeypatch.setattr(board_html, "BeautifulSoup", no_xml)
    rss = (
        "<?xml version='1.0' encoding='UTF-8'?><rss><channel><item><title>a</title>"
        "<link>https://x/na/ntt/selectNttInfo.do?nttSn=8800783&amp;mi=1376</link></item></channel></rss>"
    )
    assert board_html.extract_numbers_from_rss(rss) == ["8800783"]
    assert board_html.extract_numbers_from_rss("<rss><item><link>https://x/?nttSn=12345</link></item") == ["12345"]


def test_requirements_has_lxml():
    from pathlib import Path

    req = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
    assert "lxml" in req


def test_llm_record_then_replay(monkeypatch):
    from app import config
    from app.pd.external import llm_client

    calls = []
    resp = {
        "is_recruitment": True,
        "deadline": None,
        "deadline_evidence": None,
        "conditions": [{"item": "학년", "value": "1~3학년", "evidence": "1~3학년"}],
    }
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setitem(llm_client._CALL, "gemini", lambda t, b: calls.append(1) or resp)
    d1, i1 = llm_client.extract_conditions("녹화 시험", "본문 1~3학년", provider="gemini", mode="auto")
    d2, i2 = llm_client.extract_conditions("녹화 시험", "본문 1~3학년", provider="gemini", mode="auto")
    assert i1["how"] == "live" and i2["how"] == "replay" and len(calls) == 1 and d2 == resp
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with pytest.raises(llm_client.LLMUnavailableError):
        llm_client.extract_conditions("녹화 없음", "다른 본문", provider="gemini", mode="replay")


def test_anthropic_request_shape(monkeypatch):
    from app import config
    from app.pd.external import llm_client

    seen = {}

    class R:
        status_code = 200

        def json(self):
            return {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "report_conditions",
                        "input": {"is_recruitment": False, "conditions": []},
                    }
                ]
            }

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json)
        return R()

    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    data, info = llm_client.extract_conditions("제목", "본문", provider="anthropic", mode="live")
    assert data["is_recruitment"] is False and info["how"] == "live"
    assert seen["url"].endswith("/v1/messages") and seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["body"]["tool_choice"] == {"type": "tool", "name": "report_conditions"}
