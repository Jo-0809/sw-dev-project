"""단위 테스트 — app/pd/source/subscription.py (관심 출처, UC3 정상 5 · 대안 2)

기법: 상태 기반 + 동치 분할
  상태  : 등록 안 됨 → save → 등록됨 → save(중복) → 등록됨(1건) → remove → 등록 안 됨
  조회 순서 : 최근 등록 순 (created_at 내림차순, 같은 시각이면 출처 번호 내림차순)
  보이기 : 시연 모드(DEMO_MODE) {켜짐, 꺼짐} × 출처 종류 {preset, custom, mock, test}
"""

import pytest

from app import config
from app.pd.source import source, subscription


@pytest.fixture
def sources(unit_db):
    """종류별 출처 하나씩. {종류: 출처 번호}"""
    return {
        kind: source.add(f"{kind} 게시판", f"https://{kind}.example", mi="1", bbs_id=kind, kind=kind)
        for kind in ("preset", "custom", "mock", "test")
    }


def _ids(rows):
    return [r["id"] for r in rows]


def test_save_find_remove_states(two_accounts, sources):
    """UT-S-01 등록 안 됨 → 저장 → 조회됨 → 해제 → 조회 안 됨."""
    a, _ = two_accounts
    sid = sources["preset"]
    assert subscription.find(a) == []
    subscription.save(a, sid)
    assert _ids(subscription.find(a)) == [sid]
    subscription.remove(a, sid)
    assert subscription.find(a) == []


def test_save_twice_keeps_one(two_accounts, sources):
    """UT-S-02 같은 출처를 두 번 등록해도 한 건 (오류 없음)."""
    a, _ = two_accounts
    subscription.save(a, sources["preset"])
    subscription.save(a, sources["preset"])
    assert _ids(subscription.find(a)) == [sources["preset"]]


def test_remove_not_registered_is_noop(two_accounts, sources):
    """UT-S-03 등록하지 않은 출처를 해제해도 오류 없이 그대로."""
    a, _ = two_accounts
    subscription.save(a, sources["preset"])
    subscription.remove(a, sources["custom"])
    assert _ids(subscription.find(a)) == [sources["preset"]]


def test_find_is_per_account(two_accounts, sources):
    """UT-S-04 계정마다 따로. A가 해제해도 B의 관심 출처는 남는다."""
    a, b = two_accounts
    subscription.save(a, sources["preset"])
    subscription.save(b, sources["preset"])
    subscription.remove(a, sources["preset"])
    assert subscription.find(a) == [] and _ids(subscription.find(b)) == [sources["preset"]]


def test_find_order_latest_first(two_accounts, sources, monkeypatch):
    """UT-S-05 최근 등록 순. 늦게 등록한 출처가 번호가 작아도 앞에 온다. 같은 시각이면 번호 큰 것이 앞."""
    a, _ = two_accounts
    times = iter(["2026-11-20T09:00:00", "2026-11-21T09:00:00", "2026-11-21T09:00:00"])
    monkeypatch.setattr(subscription, "now_text", lambda: next(times))
    subscription.save(a, sources["custom"])  # 11-20
    subscription.save(a, sources["preset"])  # 11-21 (번호는 preset 이 더 작음)
    subscription.save(a, sources["mock"])  # 11-21 (같은 시각, 번호 큼)
    assert _ids(subscription.find(a)) == [sources["mock"], sources["preset"], sources["custom"]]


@pytest.mark.parametrize(
    "demo, shown",
    [(True, {"preset", "custom", "mock", "test"}), (False, {"preset", "custom"})],
    ids=["UT-S-06", "UT-S-07"],
)
def test_visibility_by_mode(two_accounts, sources, monkeypatch, demo, shown):
    """시연 모드가 아니면 모의(mock)·실패 확인(test) 출처는 조회 결과에서 뺀다 (find, registered_sources 모두)."""
    a, b = two_accounts
    for sid in sources.values():
        subscription.save(a, sid)
    subscription.save(b, sources["preset"])  # 두 계정이 같은 출처 → registered_sources 에는 한 번
    monkeypatch.setattr(config, "DEMO_MODE", demo)
    want = {sources[k] for k in shown}
    assert set(_ids(subscription.find(a))) == want
    reg = _ids(subscription.registered_sources())
    assert set(reg) == want and len(reg) == len(set(reg))
