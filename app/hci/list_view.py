"""<<boundary>> 공고 목록 화면 (UC5, 5-1 메인 화면 · 5-5 전체 보기 · 5-6 공고 없음)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..pd.notice import query_ctl
from . import common

router = APIRouter()


@router.get("/notices", response_class=HTMLResponse)
def notices(request: Request, view: str = "possible", saved: str = "", past: int = 0):
    aid = common.current_account(request)
    if not aid:
        return common.login_redirect()
    if view == "all":
        data = query_ctl.request_all(aid, include_past=bool(past))  # 전체 목록을 요청한다() (대안 1)
    else:
        data = query_ctl.request_list(aid)  # 공고 목록을 요청한다(계정)
    if data["profile"] is None:  # UC5 예외 1 → 2-1
        return common.redirect("/profile?first=1")
    return common.render(request, "list_view.html", aid, data=data, saved=saved, past=bool(past))
