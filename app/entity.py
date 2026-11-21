"""<<entity>> 실체 클래스 (클래스 다이어그램의 실체 11개 중 SPRINT 1~2에서 쓰는 9개).

계정, 로그인 세션, 학적 프로필, 출처, 관심 출처, 공지, 참여 조건, 수집 실패 기록, 열람 기록.
알림 채널·알림 발송 기록은 SPRINT 3(알림) 범위라 테이블만 만들어 두고 쓰지 않는다.
메소드 이름 옆 주석은 클래스 다이어그램의 연산 이름이다.
"""
import hashlib
import json
import secrets
import sqlite3
from datetime import timedelta

from . import config

SCHEMA = """
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
"""


def connect():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as c:
        c.executescript(SCHEMA)


def retag_test_sources():
    """v2.1까지는 실패 확인 출처(bbsId 오타 1076)를 'preset' 으로 넣었다. 시연용임을 구분하려고 'test' 로 바꾼다."""
    with connect() as c:
        c.execute("UPDATE source SET kind='test' WHERE kind='preset' AND mi='1376' AND bbs_id='1076'")


def reset_demo_data():
    """시연 초기화: 수집한 공지·조건·기록·프로필·관심 출처·직접 입력 출처를 지운다 (계정은 남김). DEMO_MODE에서만 부른다."""
    with connect() as c:
        for t in ("view_log", "condition", "notice", "failure_log", "subscription", "profile"):
            c.execute(f"DELETE FROM {t}")
        c.execute("DELETE FROM source WHERE kind='custom'")


def _now():
    return config.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- 계정
class Account:
    @staticmethod
    def count():
        with connect() as c:
            return c.execute("SELECT COUNT(*) FROM account").fetchone()[0]

    @staticmethod
    def _hash(pw, salt):
        return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()

    @staticmethod
    def create(login_id, pw):
        salt = secrets.token_hex(8)
        with connect() as c:
            c.execute("INSERT INTO account(login_id, pw_hash, salt) VALUES (?,?,?) ON CONFLICT DO NOTHING",
                      (login_id, Account._hash(pw, salt), salt))

    @staticmethod
    def set_password(login_id, pw):
        """있으면 비밀번호를 바꾸고 그 계정의 로그인 세션을 모두 끊는다 (같은 비밀번호면 아무것도 안 함).
        없으면 만든다 (시연 계정용)."""
        if Account.match(login_id, pw):
            return
        salt = secrets.token_hex(8)
        with connect() as c:
            row = c.execute("SELECT id FROM account WHERE login_id=?", (login_id,)).fetchone()
            if row:
                c.execute("UPDATE account SET pw_hash=?, salt=? WHERE id=?",
                          (Account._hash(pw, salt), salt, row["id"]))
                c.execute("DELETE FROM login_session WHERE account_id=?", (row["id"],))
            else:
                c.execute("INSERT INTO account(login_id, pw_hash, salt) VALUES (?,?,?)",
                          (login_id, Account._hash(pw, salt), salt))

    @staticmethod
    def rename(old_id, new_id):
        """아이디만 바꾼다 (프로필·관심 출처는 그대로). 새 아이디가 이미 있으면 바꾸지 않는다."""
        with connect() as c:
            if c.execute("SELECT 1 FROM account WHERE login_id=?", (new_id,)).fetchone():
                return False
            c.execute("UPDATE account SET login_id=? WHERE login_id=?", (new_id, old_id))
            c.execute("DELETE FROM login_session WHERE account_id=(SELECT id FROM account WHERE login_id=?)",
                      (new_id,))
            return True

    @staticmethod
    def remove(login_id):
        """계정과 그 계정의 세션·프로필·관심 출처·열람 기록·알림 설정을 지운다."""
        with connect() as c:
            row = c.execute("SELECT id FROM account WHERE login_id=?", (login_id,)).fetchone()
            if not row:
                return
            for t in ("login_session", "profile", "subscription", "view_log", "notify_channel", "notify_log"):
                c.execute(f"DELETE FROM {t} WHERE account_id=?", (row["id"],))
            c.execute("DELETE FROM account WHERE id=?", (row["id"],))

    @staticmethod
    def match(login_id, pw):                          # 대조한다(아이디, 비밀번호) : 일치 여부
        with connect() as c:
            row = c.execute("SELECT * FROM account WHERE login_id=?", (login_id,)).fetchone()
        if row and secrets.compare_digest(row["pw_hash"], Account._hash(pw, row["salt"])):
            return row["id"]
        return None

    @staticmethod
    def get(account_id):
        with connect() as c:
            return c.execute("SELECT * FROM account WHERE id=?", (account_id,)).fetchone()


# ---------------------------------------------------------------- 로그인 세션
class LoginSession:
    @staticmethod
    def create(account_id, auto_login):               # 생성한다(계정)
        token = secrets.token_urlsafe(24)
        days = 30 if auto_login else 1
        # 만료는 실제 시각 기준 (DEMO_TODAY로 날짜를 고정해도 세션은 만료된다)
        expires = (config.real_now() + timedelta(days=days)).isoformat(timespec="seconds")
        with connect() as c:
            c.execute("INSERT INTO login_session VALUES (?,?,?,?)",
                      (token, account_id, expires, 1 if auto_login else 0))
        return token

    @staticmethod
    def find(token):                                  # 저장된 세션을 조회한다() : 세션
        if not token:
            return None
        with connect() as c:
            row = c.execute("SELECT * FROM login_session WHERE token=?", (token,)).fetchone()
        if not row or row["expires_at"] < config.real_now().isoformat(timespec="seconds"):
            return None
        return row

    @staticmethod
    def delete(token):
        with connect() as c:
            c.execute("DELETE FROM login_session WHERE token=?", (token,))


# ---------------------------------------------------------------- 학적 프로필
class Profile:
    @staticmethod
    def find(account_id):                             # 조회한다(계정) : 프로필
        with connect() as c:
            row = c.execute("SELECT * FROM profile WHERE account_id=?", (account_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def save(account_id, university, department, grade, status):   # 저장한다(소속 대학, 학과, 학년, 재학 상태)
        with connect() as c:
            c.execute("""INSERT INTO profile VALUES (?,?,?,?,?)
                         ON CONFLICT(account_id) DO UPDATE SET university=excluded.university,
                         department=excluded.department, grade=excluded.grade, status=excluded.status""",
                      (account_id, university, department, int(grade), status))


# ---------------------------------------------------------------- 출처
class Source:
    @staticmethod
    def all():                                        # 조회한다() : 출처 목록
        with connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM source ORDER BY id")]

    @staticmethod
    def get(source_id):
        with connect() as c:
            row = c.execute("SELECT * FROM source WHERE id=?", (source_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def add(name, site_url, mi=None, bbs_id=None, rss=1, list_url=None, kind="custom"):  # 추가한다(주소) : 출처
        with connect() as c:
            row = c.execute("SELECT id FROM source WHERE site_url=? AND COALESCE(mi,'')=COALESCE(?,'') "
                            "AND COALESCE(bbs_id,'')=COALESCE(?,'') AND COALESCE(list_url,'')=COALESCE(?,'')",
                            (site_url, mi, bbs_id, list_url)).fetchone()
            if row:
                return row["id"]
            cur = c.execute("INSERT INTO source(name, site_url, mi, bbs_id, rss, list_url, kind) "
                            "VALUES (?,?,?,?,?,?,?)", (name, site_url, mi, bbs_id, rss, list_url, kind))
            return cur.lastrowid

    @staticmethod
    def seed(kind, name, site_url, mi, bbs_id, rss):  # 미리 넣어 두는 출처 (모의·실제 게시판)
        with connect() as c:
            row = c.execute("SELECT id FROM source WHERE kind=? AND mi=? AND bbs_id=? AND (kind='mock' OR site_url=?)",
                            (kind, mi, bbs_id, site_url)).fetchone()
            if row:
                c.execute("UPDATE source SET name=?, site_url=?, rss=? WHERE id=?", (name, site_url, rss, row["id"]))
            else:
                c.execute("INSERT INTO source(name, site_url, mi, bbs_id, rss, kind) VALUES (?,?,?,?,?,?)",
                          (name, site_url, mi, bbs_id, rss, kind))

    @staticmethod
    def has_rss(source):                              # RSS 제공 여부를 확인한다(출처) : 제공 여부
        return bool(source.get("rss")) and bool(source.get("mi")) and bool(source.get("bbs_id"))


# ---------------------------------------------------------------- 관심 출처
class Subscription:
    @staticmethod
    def find(account_id):                             # 조회한다(계정) : 등록 목록
        with connect() as c:
            return [dict(r) for r in c.execute(
                "SELECT s.*, sub.created_at FROM subscription sub JOIN source s ON s.id = sub.source_id "
                "WHERE sub.account_id=? ORDER BY sub.created_at DESC, s.id DESC", (account_id,))]

    @staticmethod
    def registered_sources():                         # 등록된 출처를 조회한다() : 출처 목록
        with connect() as c:
            return [dict(r) for r in c.execute(
                "SELECT DISTINCT s.* FROM subscription sub JOIN source s ON s.id = sub.source_id ORDER BY s.id")]

    @staticmethod
    def save(account_id, source_id):                  # 저장한다(계정, 출처)
        with connect() as c:
            c.execute("INSERT INTO subscription(account_id, source_id, created_at) VALUES (?,?,?) ON CONFLICT DO NOTHING",
                      (account_id, source_id, _now()))

    @staticmethod
    def remove(account_id, source_id):                # 제거한다(계정, 출처)
        with connect() as c:
            c.execute("DELETE FROM subscription WHERE account_id=? AND source_id=?", (account_id, source_id))


# ---------------------------------------------------------------- 공지
class Notice:
    @staticmethod
    def saved_numbers(source_id):                     # 조회한다(출처) : 저장된 번호
        with connect() as c:
            return {r["ntt_sn"] for r in c.execute("SELECT ntt_sn FROM notice WHERE source_id=?", (source_id,))}

    @staticmethod
    def insert(source_id, parsed):
        with connect() as c:
            cur = c.execute(
                "INSERT INTO notice(source_id, ntt_sn, title, posted_at, body, url, attachments, "
                "status, collected_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (source_id, parsed["ntt_sn"], parsed["title"], parsed.get("posted_at"), parsed["body"],
                 parsed["url"], json.dumps(parsed.get("attachments", []), ensure_ascii=False), "추출 대기", _now()))
            return cur.lastrowid if cur.rowcount else None

    @staticmethod
    def save_result(notice_id, status, deadline=None, deadline_evidence=None, method=None, note=None):
        # 저장한다(공지, 상태) / 저장한다(공지, 마감일, 상태)
        with connect() as c:
            c.execute("UPDATE notice SET status=?, deadline=?, deadline_evidence=?, extract_method=?, "
                      "extract_note=? WHERE id=?", (status, deadline, deadline_evidence, method, note, notice_id))

    @staticmethod
    def get(notice_id):                               # 조회한다(번호) : 공지
        with connect() as c:
            row = c.execute("SELECT n.*, s.name AS source_name FROM notice n JOIN source s ON s.id=n.source_id "
                            "WHERE n.id=?", (notice_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["attachments"] = json.loads(d["attachments"] or "[]")
        return d

    @staticmethod
    def list_for(source_ids):                         # 조회한다() : 공지 목록 (관심 출처 범위)
        if not source_ids:
            return []
        q = ",".join("?" * len(source_ids))
        with connect() as c:
            rows = c.execute(f"SELECT n.*, s.name AS source_name FROM notice n JOIN source s ON s.id=n.source_id "
                             f"WHERE n.source_id IN ({q}) ORDER BY n.id", list(source_ids)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["attachments"] = json.loads(d["attachments"] or "[]")
            out.append(d)
        return out

    @staticmethod
    def pending():
        with connect() as c:
            return [r["id"] for r in c.execute("SELECT id FROM notice WHERE status='추출 대기' ORDER BY id")]


# ---------------------------------------------------------------- 참여 조건
class Condition:
    @staticmethod
    def save_all(notice_id, rows):                    # 저장한다(조건 항목, 값, 근거 문장)
        with connect() as c:
            c.execute("DELETE FROM condition WHERE notice_id=?", (notice_id,))
            c.executemany("INSERT INTO condition(notice_id, item, value, evidence, verified) VALUES (?,?,?,?,?)",
                          [(notice_id, r["item"], r["value"], r.get("evidence"), 1 if r.get("verified", True) else 0)
                           for r in rows])

    @staticmethod
    def find(notice_id):                              # 조회한다(번호) : 참여 조건
        with connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM condition WHERE notice_id=? ORDER BY id", (notice_id,))]

    @staticmethod
    def find_many(notice_ids):                        # 조회한다(공지 목록) : 조건 목록
        if not notice_ids:
            return {}
        q = ",".join("?" * len(notice_ids))
        out = {i: [] for i in notice_ids}
        with connect() as c:
            for r in c.execute(f"SELECT * FROM condition WHERE notice_id IN ({q}) ORDER BY id", list(notice_ids)):
                out[r["notice_id"]].append(dict(r))
        return out


# ---------------------------------------------------------------- 수집 실패 기록
class FailureLog:
    @staticmethod
    def record(source_id, reason, ntt_sn=None, stage="목록"):   # 기록한다(출처, 사유) / 기록한다(출처, 번호, 사유)
        with connect() as c:
            c.execute("INSERT INTO failure_log(source_id, ntt_sn, stage, reason, at) VALUES (?,?,?,?,?)",
                      (source_id, ntt_sn, stage, reason, _now()))

    @staticmethod
    def recent(limit=20):
        with connect() as c:
            return [dict(r) for r in c.execute(
                "SELECT f.*, s.name AS source_name FROM failure_log f JOIN source s ON s.id=f.source_id "
                "ORDER BY f.id DESC LIMIT ?", (limit,))]


# ---------------------------------------------------------------- 열람 기록
class ViewLog:
    @staticmethod
    def save(account_id, notice_id):                  # 저장한다(계정, 번호, 열람 시각)
        with connect() as c:
            c.execute("INSERT INTO view_log(account_id, notice_id, viewed_at) VALUES (?,?,?) ON CONFLICT DO NOTHING",
                      (account_id, notice_id, _now()))

    @staticmethod
    def viewed(account_id):                           # 열람 여부를 조회한다(계정, ...) : 열람 여부
        with connect() as c:
            return {r["notice_id"] for r in c.execute("SELECT notice_id FROM view_log WHERE account_id=?",
                                                      (account_id,))}
