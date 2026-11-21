"""<<boundary>> 공고 상세 화면 (UC5, 5-2 ~ 5-4)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..pd.notice import query_ctl
from . import common

router = APIRouter()


@router.get("/notices/{notice_id}", response_class=HTMLResponse)
def notice_detail(request: Request, notice_id: int, back: str = "possible"):
    aid = common.current_account(request)
    if not aid:
        return common.login_redirect()
    d = query_ctl.request_detail(aid, notice_id)  # 상세를 요청한다(계정, 번호)
    if d is None:
        return common.redirect("/notices")
    return common.render(request, "detail_view.html", aid, d=d, back=back)
