-- 놓칠뻔 DB 스키마 (SQLite). dm/db.py 의 init_db() 가 실행한다. 모든 문장은 IF NOT EXISTS 라 여러 번 실행해도 된다.
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login_id TEXT UNIQUE NOT NULL,
    pw_hash TEXT NOT NULL,
    salt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_session (
    token TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES account(id),
    expires_at TEXT NOT NULL,
    auto_login INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS profile (
    account_id INTEGER PRIMARY KEY REFERENCES account(id),
    university TEXT NOT NULL,
    department TEXT NOT NULL,
    grade INTEGER NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    site_url TEXT NOT NULL,          -- 사이트 주소 (예: https://www.gnu.ac.kr/main)
    mi TEXT,                         -- 게시판 식별값 1
    bbs_id TEXT,                     -- 게시판 식별값 2
    rss INTEGER NOT NULL DEFAULT 1,  -- RSS 제공 여부
    list_url TEXT,                   -- 직접 입력한 목록 주소
    kind TEXT NOT NULL DEFAULT 'preset'
);
CREATE TABLE IF NOT EXISTS subscription (            -- 관심 출처 (계정-출처 연결)
    account_id INTEGER NOT NULL REFERENCES account(id),
    source_id INTEGER NOT NULL REFERENCES source(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY (account_id, source_id)
);
CREATE TABLE IF NOT EXISTS notice (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES source(id),
    ntt_sn TEXT NOT NULL,            -- 번호
    title TEXT NOT NULL,
    posted_at TEXT,                  -- 등록일
    body TEXT NOT NULL,
    url TEXT NOT NULL,               -- 원문 링크
    attachments TEXT NOT NULL DEFAULT '[]',   -- 첨부 링크 (JSON)
    deadline TEXT,                   -- 마감일
    deadline_evidence TEXT,
    status TEXT NOT NULL,            -- 추출 대기 / 추출 완료 / 확인 필요 / 모집 공고 아님
    extract_method TEXT,             -- LLM / LLM 녹화 재생 / 예시 결과 / 규칙 기반
    extract_note TEXT,
    collected_at TEXT NOT NULL,
    UNIQUE (source_id, ntt_sn)
);
CREATE TABLE IF NOT EXISTS condition (                -- 참여 조건 (공지와 합성)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_id INTEGER NOT NULL REFERENCES notice(id) ON DELETE CASCADE,
    item TEXT NOT NULL,              -- 조건 항목
    value TEXT NOT NULL,             -- 값
    evidence TEXT,                   -- 근거 문장
    verified INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS failure_log (              -- 수집 실패 기록
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES source(id),
    ntt_sn TEXT,                     -- 게시물 번호
    stage TEXT NOT NULL,             -- 실패 단계
    reason TEXT NOT NULL,            -- 사유
    at TEXT NOT NULL                 -- 시각
);
CREATE TABLE IF NOT EXISTS view_log (                 -- 열람 기록
    account_id INTEGER NOT NULL REFERENCES account(id),
    notice_id INTEGER NOT NULL REFERENCES notice(id) ON DELETE CASCADE,
    viewed_at TEXT NOT NULL,
    PRIMARY KEY (account_id, notice_id)
);
-- SPRINT 3 범위 (지금은 사용하지 않음)
CREATE TABLE IF NOT EXISTS notify_channel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES account(id),
    kind TEXT NOT NULL,
    address TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notify_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    notice_id INTEGER NOT NULL,
    sent_at TEXT NOT NULL,
    result TEXT NOT NULL,
    retry INTEGER NOT NULL DEFAULT 0
);
