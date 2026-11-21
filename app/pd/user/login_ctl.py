"""<<control>> 로그인 제어 — 계정 인증, 로그인 세션 생성 (UC1).

정상   아이디·비밀번호 입력 → 계정 대조 → 세션 생성 → 메인 화면
대안 1 자동 로그인 세션이 유효하면 바로 메인 화면
예외 1 불일치 → '아이디 또는 비밀번호가 올바르지 않습니다'
예외 2 빈칸 → '필수 항목을 입력하세요'
"""

from . import account, session


def auto_login(token):  # 자동 로그인한다()
    s = session.find(token)
    return s["account_id"] if s else None


def _check_required(login_id, pw):  # 필수 입력을 확인한다()
    missing = []
    if not (login_id or "").strip():
        missing.append("login_id")
    if not pw:
        missing.append("password")
    return missing


def login(login_id, pw, auto):  # 로그인한다(아이디, 비밀번호)
    """(성공 여부, 세션 토큰 또는 None, 오류 종류, 빈칸 목록)"""
    missing = _check_required(login_id, pw)
    if missing:
        return False, None, "required", missing
    account_id = account.match(login_id.strip(), pw)
    if not account_id:
        return False, None, "mismatch", []
    return True, session.create(account_id, auto), None, []


def logout(token):  # 설계 외: 로그아웃 (명세서에 없음)
    session.delete(token)


def login_id_of(account_id):  # 설계 외: 화면 위쪽 아이디 표시
    """화면 위쪽에 보여 줄 아이디."""
    a = account.get(account_id)
    return a["login_id"] if a else None


def has_accounts():  # 설계 외: 계정 없을 때 안내
    """계정이 하나라도 있는지 (없으면 로그인 화면에 계정 만드는 방법을 안내)."""
    return account.count() > 0
