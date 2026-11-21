"""<<entity>> 로그인 세션 (클래스 다이어그램 이름 LoginSession) — 자동 로그인 토큰과 만료 시각."""

import secrets
from datetime import timedelta

from ... import config
from ...dm.db import connect


def create(account_id, auto_login):  # 생성한다(계정)
    token = secrets.token_urlsafe(24)
    days = config.AUTO_LOGIN_DAYS if auto_login else config.LOGIN_DAYS
    # 만료는 실제 시각 기준 (DEMO_TODAY로 날짜를 고정해도 세션은 만료된다)
    expires = (config.real_now() + timedelta(days=days)).isoformat(timespec="seconds")
    with connect() as c:
        c.execute("INSERT INTO login_session VALUES (?,?,?,?)", (token, account_id, expires, 1 if auto_login else 0))
    return token


def find(token):  # 저장된 세션을 조회한다() : 세션
    if not token:
        return None
    with connect() as c:
        row = c.execute("SELECT * FROM login_session WHERE token=?", (token,)).fetchone()
    if not row or row["expires_at"] < config.real_now().isoformat(timespec="seconds"):
        return None
    return dict(row)


def delete(token):
    with connect() as c:
        c.execute("DELETE FROM login_session WHERE token=?", (token,))
