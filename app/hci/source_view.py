"""<<boundary>> 관심 출처 관리 화면 (UC3, 3-1 ~ 3-4)."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ..pd.source import source_ctl
from . import common

router = APIRouter()


def _page(request, aid, **ctx):
    available, registered = source_ctl.request_list(aid)  # 목록을 요청한다(계정)
    ctx.setdefault("msg", request.query_params.get("msg", ""))
    ctx.setdefault("new_ids", set())
    return common.render(request, "source_view.html", aid, available=available, registered=registered, **ctx)


@router.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, new: str = ""):
    aid = common.current_account(request)
    if not aid:
        return common.login_redirect()
    return _page(request, aid, new_ids={int(x) for x in new.split(",") if x.isdigit()})


@router.post("/sources/register")
def sources_register(request: Request, source_ids: list[int] = Form(default=[])):
    aid = common.current_account(request)
    if not aid:
        return common.login_redirect()
    added, refused = source_ctl.register_many(aid, source_ids)  # 등록한다(계정, 출처)
    if refused:
        names = ", ".join(f"{name} ({why})" for name, why in refused)
        return _page(request, aid, register_error=f"등록하지 않은 출처: {names}", new_ids=set(added))
    if not source_ids:
        return common.redirect("/sources")
    return common.redirect(f"/sources?msg=added&new={','.join(map(str, source_ids))}")


@router.post("/sources/release")
def sources_release(request: Request, source_id: int = Form(...)):
    aid = common.current_account(request)
    if not aid:
        return common.login_redirect()
    source_ctl.release(aid, source_id)  # 해제한다(계정, 출처)
    return common.redirect("/sources?msg=released")


@router.post("/sources/address", response_class=HTMLResponse)
def sources_address(request: Request, address: str = Form("")):
    aid = common.current_account(request)
    if not aid:
        return common.login_redirect()
    ok, message, sid = source_ctl.register_address(aid, address)  # 주소를 등록한다(계정, 주소)
    if not ok:  # 3-3, 3-4 (예외 1·2·3 같은 자리)
        return _page(request, aid, address_error=message, address_value=address)
    return common.redirect(f"/sources?msg=added&new={sid}")
