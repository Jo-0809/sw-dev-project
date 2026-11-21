"""DB 연결 — SQLite 연결을 열고 스키마(schema.sql)를 만든다.

SQL 위치 (팀 결정 B안): 테이블마다의 SQL은 그 실체 모듈(app/pd/*/ 의 account.py, notice.py …)이 갖고,
이 모듈은 연결·스키마·시각 문자열만 맡는다.
"""

import sqlite3
from pathlib import Path

from .. import config

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def connect():
    path = Path(config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as c:
        c.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))


def now_text():
    """저장용 현재 시각 문자열 (시연 날짜 고정 DEMO_TODAY 를 따른다)."""
    return config.now().isoformat(timespec="seconds")
