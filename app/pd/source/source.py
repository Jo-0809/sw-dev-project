"""<<entity>> 출처 — 수집할 게시판 (사이트 주소, 게시판 식별값 mi·bbsId, RSS 제공 여부, 직접 입력한 목록 주소).

종류(kind)
  preset : 처음부터 넣어 둔 실제 경상국립대 게시판 (presets.py)
  custom : 사용자가 직접 입력한 주소
  mock   : 모의 게시판 (시연 모드에서만 보임)
  test   : 실패 확인용 출처 (시연 모드에서만 보임)
"""

from ... import config
from ...dm.db import connect

DEMO_KINDS = ("mock", "test")


def visible(src):  # 설계 외: 시연 출처 숨김
    """시연 모드가 아니면 모의·실패 확인 출처는 없는 것처럼 다룬다."""
    return config.DEMO_MODE or src["kind"] not in DEMO_KINDS


def all(include_demo=None):  # 조회한다() : 출처 목록
    """include_demo=None 이면 시연 모드(DEMO_MODE)를 따른다."""
    show_demo = config.DEMO_MODE if include_demo is None else include_demo
    with connect() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM source ORDER BY id")]
    return [r for r in rows if show_demo or r["kind"] not in DEMO_KINDS]


def get(source_id):
    with connect() as c:
        row = c.execute("SELECT * FROM source WHERE id=?", (source_id,)).fetchone()
    return dict(row) if row else None


def add(name, site_url, mi=None, bbs_id=None, rss=1, list_url=None, kind="custom"):  # 추가한다(주소) : 출처
    with connect() as c:
        row = c.execute(
            "SELECT id FROM source WHERE site_url=? AND COALESCE(mi,'')=COALESCE(?,'') "
            "AND COALESCE(bbs_id,'')=COALESCE(?,'') AND COALESCE(list_url,'')=COALESCE(?,'')",
            (site_url, mi, bbs_id, list_url),
        ).fetchone()
        if row:
            return row["id"]
        cur = c.execute(
            "INSERT INTO source(name, site_url, mi, bbs_id, rss, list_url, kind) VALUES (?,?,?,?,?,?,?)",
            (name, site_url, mi, bbs_id, rss, list_url, kind),
        )
        return cur.lastrowid


def seed(kind, name, site_url, mi, bbs_id, rss):  # 미리 넣어 두는 출처 (실제·모의 게시판)
    with connect() as c:
        row = c.execute(
            "SELECT id FROM source WHERE kind=? AND mi=? AND bbs_id=? AND (kind='mock' OR site_url=?)",
            (kind, mi, bbs_id, site_url),
        ).fetchone()
        if row:
            c.execute("UPDATE source SET name=?, site_url=?, rss=? WHERE id=?", (name, site_url, rss, row["id"]))
        else:
            c.execute(
                "INSERT INTO source(name, site_url, mi, bbs_id, rss, kind) VALUES (?,?,?,?,?,?)",
                (name, site_url, mi, bbs_id, rss, kind),
            )


def has_rss(src):  # RSS 제공 여부를 확인한다(출처) : 제공 여부
    return bool(src.get("rss")) and bool(src.get("mi")) and bool(src.get("bbs_id"))
