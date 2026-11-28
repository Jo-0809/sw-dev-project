"""테스트 공통 — 환경 변수, 테스트 서버, 테스트 계정, 단위 테스트용 빈 DB.

실행: python -m pytest -q
모의 게시판과 저장된 실제 응답(recordings/web)을 쓰므로 인터넷 연결 없이 돈다. API 키는 쓰지 않는다.
환경 변수는 app 을 불러오기 전에 정해야 해서 이 파일 맨 위에서 정한다.
"""

import os
import socket
import tempfile
import threading
import time

_tmp = tempfile.mkdtemp()
_sock = socket.socket()
_sock.bind(("127.0.0.1", 0))
PORT = _sock.getsockname()[1]
_sock.close()
os.environ.update(
    DB_PATH=os.path.join(_tmp, "t.db"),
    PORT=str(PORT),
    SELF_URL=f"http://127.0.0.1:{PORT}",
    SCHEDULER_ENABLED="0",
    GEMINI_API_KEY="",
    ANTHROPIC_API_KEY="",
    DEMO_TODAY="2026-11-16",
    FETCH_MODE="replay",
    LLM_MODE="auto",
    LLM_PROVIDER="gemini",
    DEMO_MODE="1",
    DEMO_ID="demo-t",
    DEMO_PASSWORD="Tq7-demo-pw",
    LLM_RECORD_DIR=os.path.join(_tmp, "llm"),
)

import pytest  # noqa: E402
import requests  # noqa: E402
import uvicorn  # noqa: E402

BASE = f"http://127.0.0.1:{PORT}"
PROFILE = {"university": "경상국립대학교", "department": "소프트웨어공학과", "grade": 2, "status": "재학"}
TEST_ID, TEST_PW = "tester", "tester-pw-123"  # 테스트용 두 번째 계정 (예전 시연 계정 test 와 다른 이름)


@pytest.fixture(scope="session")
def server():
    srv = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=PORT, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        try:
            requests.get(BASE + "/login", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.1)
    from app.pd.user import account

    account.set_password(TEST_ID, TEST_PW)
    yield BASE
    srv.should_exit = True


@pytest.fixture
def test_account(server):
    from app.pd.user import account

    return account.match(TEST_ID, TEST_PW)


@pytest.fixture
def mock_notices(test_account):
    """모의 게시판 공지가 수집돼 있게 한다 (없으면 테스트 계정으로 등록하고 수집). 모의 출처 번호 목록을 돌려준다."""
    from app.pd.collect.collect_ctl import collector
    from app.pd.notice import notice
    from app.pd.source import source, subscription

    mock_ids = [s["id"] for s in source.all() if s["kind"] == "mock"]
    for sid in mock_ids:
        subscription.save(test_account, sid)
    if not notice.list_for(mock_ids):
        collector.start()
    return mock_ids


def login(session, login_id=TEST_ID, pw=TEST_PW):
    return session.post(BASE + "/login", data={"login_id": login_id, "password": pw})


# ---- 단위 테스트용 (tests/unit) — 서버를 띄우지 않고 테스트마다 빈 DB를 새로 만든다 ----
@pytest.fixture
def unit_db(tmp_path, monkeypatch):
    """config.DB_PATH 를 임시 파일로 바꾸고 스키마를 만든다. 테스트가 끝나면 원래 값으로 돌아간다."""
    from app import config
    from app.dm import db

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "unit.db")
    db.init_db()
    return tmp_path / "unit.db"


@pytest.fixture
def two_accounts(unit_db):
    """계정 두 개 (관심 출처·프로필은 계정 번호가 있어야 저장된다)."""
    from app.pd.user import account

    account.create("user-a", "pw-a-1234")
    account.create("user-b", "pw-b-1234")
    return account.match("user-a", "pw-a-1234"), account.match("user-b", "pw-b-1234")
