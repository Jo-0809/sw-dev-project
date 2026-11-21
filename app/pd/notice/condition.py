"""<<entity>> 참여 조건 — 공지와 합성. 조건 항목, 값, 근거 문장, 근거 대조 통과 여부."""

from ...dm.db import connect


def save_all(notice_id, rows):  # 저장한다(조건 항목, 값, 근거 문장)
    with connect() as c:
        c.execute("DELETE FROM condition WHERE notice_id=?", (notice_id,))
        c.executemany(
            "INSERT INTO condition(notice_id, item, value, evidence, verified) VALUES (?,?,?,?,?)",
            [(notice_id, r["item"], r["value"], r.get("evidence"), 1 if r.get("verified", True) else 0) for r in rows],
        )


def find(notice_id):  # 조회한다(번호) : 참여 조건
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM condition WHERE notice_id=? ORDER BY id", (notice_id,))]


def find_many(notice_ids):  # 조회한다(공지 목록) : 조건 목록
    if not notice_ids:
        return {}
    q = ",".join("?" * len(notice_ids))
    out = {i: [] for i in notice_ids}
    with connect() as c:
        for r in c.execute(f"SELECT * FROM condition WHERE notice_id IN ({q}) ORDER BY id", list(notice_ids)):
            out[r["notice_id"]].append(dict(r))
    return out
