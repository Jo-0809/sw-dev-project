"""<<entity>> 학적 프로필 — 소속 대학, 학과, 학년, 재학 상태 (평점은 받지 않는다: 팀 결정)."""

from ...dm.db import connect


def find(account_id):  # 조회한다(계정) : 프로필
    with connect() as c:
        row = c.execute("SELECT * FROM profile WHERE account_id=?", (account_id,)).fetchone()
    return dict(row) if row else None


def save(account_id, university, department, grade, status):  # 저장한다(소속 대학, 학과, 학년, 재학 상태)
    with connect() as c:
        c.execute(
            """INSERT INTO profile VALUES (?,?,?,?,?)
               ON CONFLICT(account_id) DO UPDATE SET university=excluded.university,
               department=excluded.department, grade=excluded.grade, status=excluded.status""",
            (account_id, university, department, int(grade), status),
        )
