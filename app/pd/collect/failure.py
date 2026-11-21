"""<<entity>> 수집 실패 기록 — 출처, 게시물 번호, 실패 단계, 사유, 시각."""

from ...dm.db import connect, now_text


def record(source_id, reason, ntt_sn=None, stage="목록"):  # 기록한다(출처, 사유) / 기록한다(출처, 번호, 사유)
    with connect() as c:
        c.execute(
            "INSERT INTO failure_log(source_id, ntt_sn, stage, reason, at) VALUES (?,?,?,?,?)",
            (source_id, ntt_sn, stage, reason, now_text()),
        )


def recent(limit=20):
    with connect() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT f.*, s.name AS source_name FROM failure_log f JOIN source s ON s.id=f.source_id "
                "ORDER BY f.id DESC LIMIT ?",
                (limit,),
            )
        ]
