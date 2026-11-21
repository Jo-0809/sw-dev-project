"""설정값. 프로젝트 폴더의 .env 파일을 읽는다 (없으면 기본값)."""

import os
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()

DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "data" / "notchilppeon.db"))
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
# 모의 게시판 주소를 만들 때 쓰는 이 서버의 주소
SELF_URL = os.environ.get("SELF_URL", f"http://{HOST}:{PORT}")

# ---- 홈페이지 연결: 학교 사이트 요청 방식 (replay / live / record) ----
FETCH_MODE = os.environ.get("FETCH_MODE", "replay").strip().lower()
WEB_RECORD_DIR = Path(os.environ.get("WEB_RECORD_DIR", BASE_DIR / "recordings" / "web"))

# ---- LLM API 연결 ----
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()  # gemini / anthropic
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL", "gemini-3.8-flash"
)  # 폐기 일정 페이지: 새 프로젝트는 3.8 Flash 권장 (2026-11-14 확인)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")  # 모델 이름 확인 필요
# auto   : 녹화된 응답이 있으면 그것을 쓰고(호출 안 함), 없으면 API 호출 후 녹화
# live   : 항상 API 호출 후 녹화
# replay : 녹화된 응답만 쓴다. API를 부르지 않는다 (발표장)
LLM_MODE = os.environ.get("LLM_MODE", "auto").strip().lower()
LLM_RECORD_DIR = Path(os.environ.get("LLM_RECORD_DIR", BASE_DIR / "recordings" / "llm"))
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "60"))
LLM_MAX_RETRY = 3  # 조건 추출 제어: 최대 재시도 횟수 = 3

AUTO_LOGIN_DAYS = 30  # 로그인 제어: 자동 로그인 유지 기간 (일)
LOGIN_DAYS = 1  # 자동 로그인을 고르지 않았을 때
COLLECT_INTERVAL_MIN = int(os.environ.get("COLLECT_INTERVAL_MIN", "30"))  # 수집 스케줄러: 수집 주기
SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "1") == "1"
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "10"))
USER_AGENT = "NotchilppeonBot/0.2 (GNU SW Engineering class project)"

# 시연 모드: 시연 계정(demo·test), 모의 게시판, 시연 초기화(/demo/reset)를 켠다. 실제로 쓸 때는 0.
DEMO_MODE = os.environ.get("DEMO_MODE", "0").strip().lower() in ("1", "true", "yes", "on")
# 시연 계정. 비밀번호를 비워 두면 처음 실행할 때 무작위로 만들어 data/demo_account.txt 에 적어 둔다.
# 예전 시연 계정(demo/demo1234, test/test1234)은 흔한 비밀번호라 브라우저가 '유출된 비밀번호' 경고를 띄워서 쓰지 않는다.
DEMO_ID = os.environ.get("DEMO_ID", "").strip() or "notchil-demo"
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "").strip()


def demo_credentials():
    """(아이디, 비밀번호). .env 값이 있으면 그것, 없으면 data/demo_account.txt (없으면 새로 만듦)."""
    if DEMO_PASSWORD:
        return DEMO_ID, DEMO_PASSWORD
    path = Path(DB_PATH).parent / "demo_account.txt"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("password="):
                return DEMO_ID, line.split("=", 1)[1].strip()
    import secrets

    pw = secrets.token_urlsafe(9)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# 놓칠뻔 시연 계정 (자동 생성, git에 올리지 않음)\nid={DEMO_ID}\npassword={pw}\n", encoding="utf-8"
    )
    return DEMO_ID, pw


# 시연용 '오늘' 날짜. 비우면 실제 오늘. 예: DEMO_TODAY=2026-10-31
_demo_today = os.environ.get("DEMO_TODAY", "").strip()


def today() -> date:
    if _demo_today:
        return date.fromisoformat(_demo_today)
    return date.today()


def real_now() -> datetime:
    """실제 시각. 로그인 세션 만료처럼 시연 날짜와 상관없이 흘러야 하는 시간에 쓴다."""
    return datetime.now()


def now() -> datetime:
    if _demo_today:
        t = datetime.now()
        return datetime.combine(today(), t.time())
    return datetime.now()
