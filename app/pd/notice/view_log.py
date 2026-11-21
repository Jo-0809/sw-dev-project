"""<<entity>> 열람 기록 — 계정이 공지 상세를 처음 연 시각."""

from ...dm.db import connect, now_text


def save(account_id, notice_id):  # 저장한다(계정, 번호, 열람 시각)
    with connect() as c:
        c.execute(
            "INSERT INTO view_log(account_id, notice_id, viewed_at) VALUES (?,?,?) ON CONFLICT DO NOTHING",
            (account_id, notice_id, now_text()),
        )


def viewed(account_id):  # 열람 여부를 조회한다(계정, ...) : 열람 여부
    with connect() as c:
        return {r["notice_id"] for r in c.execute("SELECT notice_id FROM view_log WHERE account_id=?", (account_id,))}
