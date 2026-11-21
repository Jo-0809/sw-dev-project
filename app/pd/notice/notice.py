"""<<entity>> 공지 — 수집한 게시물 (번호, 제목, 등록일, 본문, 원문 링크, 첨부 링크, 마감일, 상태).

상태: 추출 대기 / 추출 완료 / 확인 필요 / 모집 공고 아님
"""

import json

from ...dm.db import connect, now_text

WAITING, DONE, CHECK, NOT_RECRUIT = "추출 대기", "추출 완료", "확인 필요", "모집 공고 아님"


def _row(r):
    d = dict(r)
    d["attachments"] = json.loads(d["attachments"] or "[]")
    return d


def saved_numbers(source_id):  # 조회한다(출처) : 저장된 번호
    with connect() as c:
        return {r["ntt_sn"] for r in c.execute("SELECT ntt_sn FROM notice WHERE source_id=?", (source_id,))}


def insert(source_id, parsed):
    with connect() as c:
        cur = c.execute(
            "INSERT INTO notice(source_id, ntt_sn, title, posted_at, body, url, attachments, status, collected_at) "
            "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (
                source_id,
                parsed["ntt_sn"],
                parsed["title"],
                parsed.get("posted_at"),
                parsed["body"],
                parsed["url"],
                json.dumps(parsed.get("attachments", []), ensure_ascii=False),
                WAITING,
                now_text(),
            ),
        )
        return cur.lastrowid if cur.rowcount else None


def save_result(notice_id, status, deadline=None, deadline_evidence=None, method=None, note=None):
    # 저장한다(공지, 상태) / 저장한다(공지, 마감일, 상태)
    with connect() as c:
        c.execute(
            "UPDATE notice SET status=?, deadline=?, deadline_evidence=?, extract_method=?, extract_note=? WHERE id=?",
            (status, deadline, deadline_evidence, method, note, notice_id),
        )


def get(notice_id):  # 조회한다(번호) : 공지
    with connect() as c:
        row = c.execute(
            "SELECT n.*, s.name AS source_name FROM notice n JOIN source s ON s.id=n.source_id WHERE n.id=?",
            (notice_id,),
        ).fetchone()
    return _row(row) if row else None


def list_for(source_ids):  # 조회한다() : 공지 목록 (관심 출처 범위)
    if not source_ids:
        return []
    q = ",".join("?" * len(source_ids))
    with connect() as c:
        rows = c.execute(
            f"SELECT n.*, s.name AS source_name FROM notice n JOIN source s ON s.id=n.source_id "
            f"WHERE n.source_id IN ({q}) ORDER BY n.id",
            list(source_ids),
        ).fetchall()
    return [_row(r) for r in rows]


def pending():
    with connect() as c:
        return [r["id"] for r in c.execute("SELECT id FROM notice WHERE status=? ORDER BY id", (WAITING,))]
