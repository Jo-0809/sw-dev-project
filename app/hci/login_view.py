"""<<boundary>> 로그인 화면 (UC1, 1-1 ~ 1-3)."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ..pd.user import login_ctl
from . import common

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if common.current_account(request):  # 대안 1: 자동 로그인
        return common.redirect("/")
    return common.render(request, "login_view.html")


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, login_id: str = Form(""), password: str = Form(""), auto: str | None = Form(None)):
    ok, token, err, missing = login_ctl.login(login_id, password, bool(auto))
    if not ok:  # 예외 1, 예외 2
        return common.render(
            request, "login_view.html", error=err, missing=missing, login_id_value=login_id, auto=bool(auto)
        )
    resp = common.redirect("/")
    resp.set_cookie(
        common.COOKIE, token, httponly=True, samesite="lax", max_age=common.AUTO_LOGIN_MAX_AGE if auto else None
    )
    return resp


@router.get("/logout")
def logout(request: Request):
    login_ctl.logout(request.cookies.get(common.COOKIE))
    resp = common.login_redirect()
    resp.delete_cookie(common.COOKIE)
    return resp
