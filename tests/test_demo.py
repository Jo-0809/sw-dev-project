"""시연·측정 코드(app/demo) — 규칙 기반 대체 추출, 채점, 시연 모드 경계."""

import requests
from conftest import BASE, login


def test_rule_based_fallback():
    from app.demo import mockdata
    from app.demo.rule_based import rule_based

    p = next(x for x in mockdata.POSTS if x["ntt"] == "8800105")
    r = rule_based(p["title"], mockdata.render(p["body"]))
    items = {c["item"]: c["value"] for c in r["conditions"]}
    assert r["is_recruitment"] and r["deadline"].startswith("2026-11-25")
    assert items["학년"].replace(" ", "") == "2학년이상" and items["학과"] == "전공 무관"
    q = next(x for x in mockdata.POSTS if x["ntt"] == "8800107")
    assert rule_based(q["title"], mockdata.render(q["body"]))["is_recruitment"] is False


def test_evaluation_rule_baseline():
    from app.demo import evaluation

    s = evaluation.run_method("rule")["summary"]
    assert s["sample_total"] == 10 and s["excluded"] == 2 and s["scored"] == 8
    assert s["verdict_acc"] is not None and s["fabricated"] >= 0


def test_check_ratio_metric():
    from app.demo import evaluation

    s = evaluation.run_method("rule")["summary"]
    assert s["check_ratio"] is not None and 0 <= s["check_ratio"] <= 100
    assert evaluation.TARGETS["check_ratio"] == "10% 이하"


def test_demo_reset_only_in_demo_mode(server, monkeypatch):
    from app import config

    s = requests.Session()
    login(s)
    monkeypatch.setattr(config, "DEMO_MODE", False)
    assert s.post(BASE + "/demo/reset", allow_redirects=False).status_code == 404
    assert requests.get(BASE + "/compare", allow_redirects=False).status_code == 404


def test_demo_panels_are_injected(server):
    """시연 패널(지금 수집·시연 초기화)은 app/demo 가 관심 출처 화면에 끼운다. 화면 템플릿에는 없다."""
    from pathlib import Path

    s = requests.Session()
    login(s)
    page = s.get(BASE + "/sources").text
    assert "지금 수집" in page and "시연 초기화" in page and "추출 API 비교" in page
    tpl = (Path(__file__).resolve().parent.parent / "app" / "hci" / "templates" / "source_view.html").read_text("utf-8")
    assert "/collect" not in tpl and "/demo/reset" not in tpl


def test_example_provider_injected_only_in_demo(server):
    """예시 결과는 app/main.py 가 시연 모드에서 조건 추출 제어에 넣는다 (조건 추출 제어는 app.demo 를 모름)."""
    from app.demo import examples
    from app.pd.collect import extract_ctl

    assert extract_ctl._example_provider is examples.fallback
