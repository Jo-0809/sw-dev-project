"""<<boundary>> 프로필 입력 화면 (UC2, 2-1 ~ 2-5)."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ..pd.user import profile_ctl
from . import common

router = APIRouter()


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, first: int = 0):
    aid = common.current_account(request)
    if not aid:
        return common.login_redirect()
    prof = profile_ctl.load(aid)
    return common.render(
        request, "profile_view.html", aid, values=prof or {}, first=bool(first or prof is None), options=profile_ctl
    )


@router.post("/profile", response_class=HTMLResponse)
def profile_save(
    request: Request,
    university: str = Form(""),
    department: str = Form(""),
    grade: str = Form(""),
    status: str = Form("재학"),
    first: int = Form(0),
):
    aid = common.current_account(request)
    if not aid:
        return common.login_redirect()
    values = {"university": university, "department": department, "grade": grade, "status": status}
    ok, missing = profile_ctl.save(aid, values)
    if not ok:  # 2-2 필수 항목 누락
        return common.render(
            request, "profile_view.html", aid, values=values, first=bool(first), missing=missing, options=profile_ctl
        )
    if first:  # 2-5 첫 저장 → 메인
        return common.redirect("/notices?saved=first")
    return common.render(
        request,
        "profile_view.html",
        aid,
        values=values,
        first=False,
        saved=True,  # 2-4
        options=profile_ctl,
    )
