"""<<entity>> 계정 — 아이디와 비밀번호 해시(PBKDF2). 회원가입 화면은 범위 밖이다."""

import hashlib
import secrets

from ...dm.db import connect


def count():
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM account").fetchone()[0]


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()


def create(login_id, pw):
    salt = secrets.token_hex(8)
    with connect() as c:
        c.execute(
            "INSERT INTO account(login_id, pw_hash, salt) VALUES (?,?,?) ON CONFLICT DO NOTHING",
            (login_id, _hash(pw, salt), salt),
        )


def set_password(login_id, pw):
    """있으면 비밀번호를 바꾸고 그 계정의 로그인 세션을 모두 끊는다 (같은 비밀번호면 아무것도 안 함).
    없으면 만든다 (시연 계정용)."""
    if match(login_id, pw):
        return
    salt = secrets.token_hex(8)
    with connect() as c:
        row = c.execute("SELECT id FROM account WHERE login_id=?", (login_id,)).fetchone()
        if row:
            c.execute("UPDATE account SET pw_hash=?, salt=? WHERE id=?", (_hash(pw, salt), salt, row["id"]))
            c.execute("DELETE FROM login_session WHERE account_id=?", (row["id"],))
        else:
            c.execute("INSERT INTO account(login_id, pw_hash, salt) VALUES (?,?,?)", (login_id, _hash(pw, salt), salt))


def rename(old_id, new_id):
    """아이디만 바꾼다 (프로필·관심 출처는 그대로). 새 아이디가 이미 있으면 바꾸지 않는다."""
    with connect() as c:
        if c.execute("SELECT 1 FROM account WHERE login_id=?", (new_id,)).fetchone():
            return False
        c.execute("UPDATE account SET login_id=? WHERE login_id=?", (new_id, old_id))
        c.execute("DELETE FROM login_session WHERE account_id=(SELECT id FROM account WHERE login_id=?)", (new_id,))
        return True


def remove(login_id):
    """계정과 그 계정의 세션·프로필·관심 출처·열람 기록·알림 설정을 지운다."""
    with connect() as c:
        row = c.execute("SELECT id FROM account WHERE login_id=?", (login_id,)).fetchone()
        if not row:
            return
        for t in ("login_session", "profile", "subscription", "view_log", "notify_channel", "notify_log"):
            c.execute(f"DELETE FROM {t} WHERE account_id=?", (row["id"],))
        c.execute("DELETE FROM account WHERE id=?", (row["id"],))


def match(login_id, pw):  # 대조한다(아이디, 비밀번호) : 일치 여부
    """일치하면 계정 번호, 아니면 None."""
    with connect() as c:
        row = c.execute("SELECT * FROM account WHERE login_id=?", (login_id,)).fetchone()
    if row and secrets.compare_digest(row["pw_hash"], _hash(pw, row["salt"])):
        return row["id"]
    return None


def get(account_id):
    with connect() as c:
        row = c.execute("SELECT * FROM account WHERE id=?", (account_id,)).fetchone()
    return dict(row) if row else None
