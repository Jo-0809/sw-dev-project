"""<<entity>> 관심 출처 — 계정과 출처의 연결. 시연 모드가 아니면 모의·실패 확인 출처는 결과에서 뺀다."""

from ...dm.db import connect, now_text
from .source import visible


def find(account_id):  # 조회한다(계정) : 등록 목록
    with connect() as c:
        rows = [
            dict(r)
            for r in c.execute(
                "SELECT s.*, sub.created_at FROM subscription sub JOIN source s ON s.id = sub.source_id "
                "WHERE sub.account_id=? ORDER BY sub.created_at DESC, s.id DESC",
                (account_id,),
            )
        ]
    return [r for r in rows if visible(r)]


def registered_sources():  # 등록된 출처를 조회한다() : 출처 목록
    with connect() as c:
        rows = [
            dict(r)
            for r in c.execute(
                "SELECT DISTINCT s.* FROM subscription sub JOIN source s ON s.id = sub.source_id ORDER BY s.id"
            )
        ]
    return [r for r in rows if visible(r)]


def save(account_id, source_id):  # 저장한다(계정, 출처)
    with connect() as c:
        c.execute(
            "INSERT INTO subscription(account_id, source_id, created_at) VALUES (?,?,?) ON CONFLICT DO NOTHING",
            (account_id, source_id, now_text()),
        )


def remove(account_id, source_id):  # 제거한다(계정, 출처)
    with connect() as c:
        c.execute("DELETE FROM subscription WHERE account_id=? AND source_id=?", (account_id, source_id))
