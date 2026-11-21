"""<<entity>> 열람 기록 — 계정이 공지 상세를 처음 연 시각."""

from ...dm.db import connect, now_text


def save(account_id, notice_id):  # 저장한다(계정, 번호, 열람 시각)
    with connect() as c:
        c.execute(
            "INSERT INTO view_log(account_id, notice_id, viewed_at) VALUES (?,?,?) ON CONFLICT DO NOTHING",
            (account_id, notice_id, now_text()),
        )


def viewed(account_id, notice_ids=None):  # 열람 여부를 조회한다(계정, 임박) : 열람 여부
    """열람한 공지 번호 집합. notice_ids 를 주면 그 안에서만 본다 (UC6 임박 공지 목록용, SPRINT 3)."""
    with connect() as c:
        seen = {r["notice_id"] for r in c.execute("SELECT notice_id FROM view_log WHERE account_id=?", (account_id,))}
    return seen if notice_ids is None else seen & set(notice_ids)
