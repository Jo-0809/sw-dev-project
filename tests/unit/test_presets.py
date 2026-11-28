"""단위 테스트 — app/pd/source/presets.py (처음부터 넣어 두는 실제 게시판, UC3 정상 2의 '등록 가능한 출처 목록')

기법: 상태 기반(여러 번 실행) + 동치 분할
  상태  : 빈 DB → seed → 4건 → seed 다시 → 4건 그대로 (앱을 켤 때마다 실행되므로 중복이 생기면 안 된다)
  갱신  : 게시판 이름·RSS 사용 값이 바뀐 뒤 seed → 새 행을 만들지 않고 같은 행을 고친다
  RSS 사용 : {1: RSS로 수집, 0: 목록 HTML로 수집} 두 클래스에서 하나 이상씩
"""

import pytest

from app import config
from app.pd.source import presets, source


def _presets():
    return [s for s in source.all(include_demo=True) if s["kind"] == "preset"]


def test_seed_inserts_real_sources(unit_db):
    """UT-PR-01 빈 DB에 seed → REAL_SOURCES 4건이 같은 값(이름·사이트·mi·bbsId·RSS)으로 들어간다."""
    presets.seed()
    got = sorted((s["name"], s["site_url"], s["mi"], s["bbs_id"], s["rss"]) for s in _presets())
    assert got == sorted(presets.REAL_SOURCES)


def test_seed_twice_no_duplicates(unit_db):
    """UT-PR-02 seed를 두 번 실행해도 4건 그대로, 번호도 그대로."""
    presets.seed()
    ids = sorted(s["id"] for s in _presets())
    presets.seed()
    assert sorted(s["id"] for s in _presets()) == ids and len(ids) == 4


@pytest.mark.parametrize(
    "name, has_rss",
    [("경상국립대 대학 공지 – 장학", True), ("경상국립대 산업시스템공학부 – 장학정보", False)],
    ids=["UT-PR-03", "UT-PR-04"],
)
def test_rss_flag(unit_db, name, has_rss):
    """RSS 사용 1인 게시판은 RSS로, 0인 게시판(산업시스템공학부)은 목록 HTML로 수집한다."""
    presets.seed()
    src = next(s for s in _presets() if s["name"] == name)
    assert source.has_rss(src) is has_rss


def test_seed_updates_changed_values(unit_db, monkeypatch):
    """UT-PR-05 이름·RSS 사용 값이 바뀌면 같은 행(사이트·mi·bbsId가 같은 행)을 고친다. 새 행은 생기지 않는다."""
    presets.seed()
    before = {s["bbs_id"]: s["id"] for s in _presets()}
    changed = [(f"{n} (개명)", site, mi, bbs, 0) for n, site, mi, bbs, _ in presets.REAL_SOURCES]
    monkeypatch.setattr(presets, "REAL_SOURCES", changed)
    presets.seed()
    after = _presets()
    assert {s["bbs_id"]: s["id"] for s in after} == before
    assert all(s["name"].endswith("(개명)") and s["rss"] == 0 for s in after)


def test_presets_visible_without_demo_mode(unit_db, monkeypatch):
    """UT-PR-06 시연 모드를 꺼도 실제 게시판은 출처 목록에 보인다 (모의·실패 확인 출처만 숨김)."""
    presets.seed()
    monkeypatch.setattr(config, "DEMO_MODE", False)
    assert len([s for s in source.all() if s["kind"] == "preset"]) == 4
