"""사용자 패키지 — 계정, 로그인 세션, 시연 계정, 계정 만들기 도구."""

import os

import requests
from conftest import BASE


def test_demo_account_changed(server, tmp_path, monkeypatch):
    """흔한 비밀번호(demo/demo1234)는 브라우저가 '유출된 비밀번호'로 경고한다. 시연 계정은 .env 값 또는 무작위."""
    from pathlib import Path

    from app import config, main
    from app.pd.user import account

    assert account.match("demo-t", "Tq7-demo-pw")
    account.set_password("demo", "demo1234")  # 예전 판 DB 흉내
    main.seed()
    assert account.match("demo", "demo1234") is None  # 예전 시연 계정은 더 이상 로그인 안 됨
    assert account.match("demo-t", "Tq7-demo-pw")
    page = requests.get(BASE + "/login")
    assert page.status_code == 200 and "demo-t" in page.text and "demo1234" not in page.text
    monkeypatch.setattr(config, "DEMO_PASSWORD", "")
    monkeypatch.setattr(config, "DB_PATH", Path(tmp_path / "x.db"))
    _, p1 = config.demo_credentials()
    _, p2 = config.demo_credentials()
    assert p1 == p2 and len(p1) >= 10 and p1 not in ("demo1234", "test1234")
    assert (tmp_path / "demo_account.txt").exists()


def test_session_expiry_uses_real_clock(server, monkeypatch):
    """DEMO_TODAY로 날짜를 고정해도 로그인 세션은 실제 시각으로 만료된다."""
    from datetime import datetime, timedelta

    from app import config
    from app.pd.user import account, session

    account.set_password("sess", "sess-pw-123")
    aid = account.match("sess", "sess-pw-123")
    token = session.create(aid, auto_login=False)
    assert session.find(token)
    later = datetime.now() + timedelta(days=2)
    monkeypatch.setattr(config, "real_now", lambda: later)
    assert session.find(token) is None


def test_password_change_ends_sessions(server):
    from app.pd.user import account, session

    account.set_password("pwchange", "first-pw-123")
    aid = account.match("pwchange", "first-pw-123")
    token = session.create(aid, auto_login=True)
    account.set_password("pwchange", "first-pw-123")  # 같은 비밀번호: 세션 유지
    assert session.find(token)
    account.set_password("pwchange", "second-pw-456")  # 바뀐 비밀번호: 세션 끊김
    assert session.find(token) is None
    assert account.match("pwchange", "second-pw-456") == aid


def test_create_account_tool_and_login_hint(server, monkeypatch, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    from app.pd.user import account

    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "DB_PATH": str(tmp_path / "x.db"), "PYTHONUTF8": "1"}
    code = (
        "import getpass,runpy,sys; getpass.getpass=lambda p='': 'pass12345'; "
        f"sys.argv=['create_account.py','admin']; runpy.run_path(r'{root / 'tools' / 'create_account.py'}', "
        "run_name='__main__')"
    )
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=root)
    assert "계정을 만들었습니다" in out.stdout, out.stderr
    monkeypatch.setattr(account, "count", lambda: 0)
    assert "아직 계정이 없어요" in requests.get(BASE + "/login").text


def test_main_entry_redirects(server):
    """메인 진입(/): 로그인 안 됨 → 로그인 화면. 메인 화면 = 공고 목록 화면 5-1 (UI 설계서)."""
    r = requests.get(BASE + "/", allow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
