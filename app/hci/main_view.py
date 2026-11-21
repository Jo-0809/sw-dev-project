"""<<boundary>> 메인 화면 진입 (/) — 갈 곳만 정한다.

UI 설계서: 메인 화면 = 공고 목록 화면 5-1 (지원 가능 공고). 그래서 따로 화면을 그리지 않고
  로그인 안 됨 → 로그인 화면 / 프로필 없음 → 프로필 입력 화면(2-1, UC5 예외 1) / 그 밖 → 공고 목록 화면
"""

from fastapi import APIRouter, Request

from ..pd.user import profile_ctl
from . import common

router = APIRouter()


@router.get("/")
def home(request: Request):
    aid = common.current_account(request)
    if not aid:
        return common.login_redirect()
    if profile_ctl.load(aid) is None:
        return common.redirect("/profile?first=1")
    return common.redirect("/notices")
