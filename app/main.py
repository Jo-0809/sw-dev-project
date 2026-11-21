"""놓칠뻔 데모 — 웹 화면(경계 클래스)과 라우팅.

<<boundary>> 로그인 화면, 메인 화면(= 공고 목록 화면 5-1), 프로필 입력 화면, 관심 출처 관리 화면,
              공고 목록 화면, 공고 상세 화면  → templates/*.html
"""
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, entity
if config.DEMO_MODE:                                        # 시연용 코드는 시연 모드에서만 불러온다
    from .demo import evaluation, mockboard, mockdata
from .boundary import llm_client, web_client
from .control import collect_ctl, collect_scheduler, login_ctl, profile_ctl, query_ctl, source_ctl
from .entity import Account, FailureLog, Source

APP_DIR = Path(__file__).resolve().parent
COOKIE = "nc_session"

# 실제 경상국립대 게시판. 수집기 v4(sources.json)와 같은 값이고, 2026-10-11에 저장한 실제 응답이 recordings/web/ 에 있다.
# (이름, 사이트, mi, bbsId, RSS 사용)  산업시스템공학부는 목록 HTML 경로를 보이려고 v4처럼 RSS를 끔
REAL_SOURCES = [
    ("경상국립대 대학 공지 – 장학", "https://www.gnu.ac.kr/main", "1376", "1075", 1),
    ("경상국립대 대학 공지 – 학사", "https://www.gnu.ac.kr/main", "1127", "1029", 1),
    ("경상국립대 대학 공지 – 외부기관", "https://www.gnu.ac.kr/main", "1132", "1033", 1),
    ("경상국립대 산업시스템공학부 – 장학정보", "https://www.gnu.ac.kr/ise", "3003", "1374", 0),
]
# 시연용 실패 확인 출처 (게시판 번호 오타 → '시스템안내' 화면 → 번호 확보 실패). 시연 모드에서만 넣는다.
TEST_SOURCES = [
    ("[실패 확인] 대학 공지 – 장학 (bbsId 오타 1076)", "https://www.gnu.ac.kr/main", "1376", "1076", 1),
]

LEGACY_DEMO_ACCOUNTS = [("demo", "demo1234"), ("test", "test1234")]


def seed():
    entity.init_db()
    entity.retag_test_sources()                             # v2.1 이전 DB: 실패 확인 출처를 'test' 종류로
    for name, site, mi, bbs, rss in REAL_SOURCES:
        Source.seed("preset", name, site, mi, bbs, rss)
    if not config.DEMO_MODE:
        if Account.count() == 0:
            print("[놓칠뻔] 로그인할 계정이 없습니다. 'python tools/create_account.py 아이디' 로 만드세요 "
                  "(시연이면 .env 에 DEMO_MODE=1).")
        return
    for name, site, mi, bbs, rss in TEST_SOURCES:
        Source.seed("test", name, site, mi, bbs, rss)
    demo_id, demo_pw = config.demo_credentials()            # 시연 계정 (회원가입은 범위 밖)
    for old_id, old_pw in LEGACY_DEMO_ACCOUNTS:             # v2.4까지의 흔한 비밀번호 계정 정리
        if (old_id, old_pw) == (demo_id, demo_pw) or not Account.match(old_id, old_pw):
            continue
        if old_id == "demo" and Account.rename(old_id, demo_id):
            continue                                        # 예전 시연 계정은 새 아이디로 (프로필·관심 출처 유지)
        Account.remove(old_id)
    Account.set_password(demo_id, demo_pw)                  # 비밀번호가 바뀌었으면 적용하고 예전 세션을 끊음
    for key in ("scholar", "external", "sw"):
        b = mockdata.BOARDS[key]
        Source.seed("mock", f"[모의] {b['name']}" + ("" if b["rss"] else " (RSS 없음)"),
                    f"{config.SELF_URL}/mock/{b['site']}", b["mi"], b["bbs"], 1 if b["rss"] else 0)


@asynccontextmanager
async def lifespan(app):
    seed()
    collect_scheduler.start()
    yield
    collect_scheduler.stop()


app = FastAPI(title="놓칠뻔 데모", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
if config.DEMO_MODE:                                        # 모의 게시판은 시연 모드에서만 연다
    app.include_router(mockboard.router)
templates = Jinja2Templates(directory=APP_DIR / "templates")


def _account(request):
    return login_ctl.auto_login(request.cookies.get(COOKIE))


def _render(request, name, account_id=None, **ctx):
    ctx.update(request=request, account_id=account_id, today=config.today(),
               llm_status=llm_client.status_text(), fetch_mode=config.FETCH_MODE, demo_today=bool(config._demo_today),
               demo_mode=config.DEMO_MODE, no_account=Account.count() == 0,
               demo_id=config.DEMO_ID if config.DEMO_MODE else None)
    if account_id:
        ctx.setdefault("login_id", Account.get(account_id)["login_id"])
    return templates.TemplateResponse(request, name, ctx)


def _login_redirect():
    return RedirectResponse("/login", status_code=303)


# ------------------------------------------------------------------ UC1 로그인 (1-1 ~ 1-3)
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse("/notices" if _account(request) else "/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if _account(request):                                   # 대안 1: 자동 로그인
        return RedirectResponse("/notices", status_code=303)
    return _render(request, "login.html")


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, login_id: str = Form(""), password: str = Form(""),
                 auto: Optional[str] = Form(None)):
    ok, token, err, missing = login_ctl.login(login_id, password, bool(auto))
    if not ok:
        return _render(request, "login.html", error=err, missing=missing, login_id_value=login_id, auto=bool(auto))
    resp = RedirectResponse("/notices", status_code=303)
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax",
                    max_age=30 * 24 * 3600 if auto else None)
    return resp


@app.get("/logout")
def logout(request: Request):
    login_ctl.logout(request.cookies.get(COOKIE))
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


# ------------------------------------------------------------------ UC2 프로필 (2-1 ~ 2-5)
@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, first: int = 0):
    aid = _account(request)
    if not aid:
        return _login_redirect()
    prof = profile_ctl.load(aid)
    return _render(request, "profile.html", aid, values=prof or {}, first=bool(first or prof is None),
                   options=profile_ctl)


@app.post("/profile", response_class=HTMLResponse)
def profile_save(request: Request, university: str = Form(""), department: str = Form(""),
                 grade: str = Form(""), status: str = Form("재학"), first: int = Form(0)):
    aid = _account(request)
    if not aid:
        return _login_redirect()
    values = {"university": university, "department": department, "grade": grade, "status": status}
    ok, missing = profile_ctl.save(aid, values)
    if not ok:                                              # 2-2 필수 항목 누락
        return _render(request, "profile.html", aid, values=values, first=bool(first), missing=missing,
                       options=profile_ctl)
    if first:                                               # 2-5 첫 저장 → 메인
        return RedirectResponse("/notices?saved=first", status_code=303)
    return _render(request, "profile.html", aid, values=values, first=False, saved=True,   # 2-4
                   options=profile_ctl)


# ------------------------------------------------------------------ UC3 관심 출처 (3-1 ~ 3-4)
def _sources_page(request, aid, **ctx):
    available, registered = source_ctl.request_list(aid)
    return _render(request, "sources.html", aid, available=available, registered=registered,
                   last_run=collect_ctl.last_run, failures=FailureLog.recent(8),
                   next_run=collect_scheduler.next_run(), interval=config.COLLECT_INTERVAL_MIN,
                   collecting=collect_ctl._lock.locked(), record_info=web_client.record_info(), **ctx)


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, msg: str = "", new: str = ""):
    aid = _account(request)
    if not aid:
        return _login_redirect()
    return _sources_page(request, aid, msg=msg, new_ids={int(x) for x in new.split(",") if x.isdigit()})


@app.post("/sources/register")
def sources_register(request: Request, source_ids: List[int] = Form(default=[])):
    aid = _account(request)
    if not aid:
        return _login_redirect()
    added, refused = [], []
    for sid in source_ids:                                  # 선택한 출처마다 정상 3~5 반복
        ok, why = source_ctl.register(aid, sid)
        (added if ok else refused).append((sid, why))
    if refused:
        names = ", ".join(f"{(Source.get(s) or {}).get('name', s)} ({why})" for s, why in refused)
        return _sources_page(request, aid, register_error=f"등록하지 않은 출처: {names}",
                             new_ids={s for s, _ in added})
    if not source_ids:
        return RedirectResponse("/sources", status_code=303)
    return RedirectResponse(f"/sources?msg=added&new={','.join(map(str, source_ids))}", status_code=303)


@app.post("/sources/release")
def sources_release(request: Request, source_id: int = Form(...)):
    aid = _account(request)
    if not aid:
        return _login_redirect()
    source_ctl.release(aid, source_id)
    return RedirectResponse("/sources?msg=released", status_code=303)


@app.post("/sources/address", response_class=HTMLResponse)
def sources_address(request: Request, address: str = Form("")):
    aid = _account(request)
    if not aid:
        return _login_redirect()
    ok, message, sid = source_ctl.register_address(aid, address)
    if not ok:                                              # 3-3, 3-4 (예외 1·2·3 같은 자리)
        return _sources_page(request, aid, address_error=message, address_value=address, new_ids=set())
    return RedirectResponse(f"/sources?msg=added&new={sid}", status_code=303)


@app.post("/collect")
def collect_now(request: Request):
    """시연용: 수집 주기를 기다리지 않고 수집 스케줄러가 하는 일을 지금 실행한다."""
    if not _account(request):
        return _login_redirect()
    if not collect_ctl._lock.locked():
        threading.Thread(target=collect_ctl.start, daemon=True).start()
    return RedirectResponse("/sources?msg=collecting", status_code=303)


@app.post("/demo/reset")
def demo_reset(request: Request):
    """시연 초기화: 수집한 공지·조건·기록·프로필·관심 출처와 모의 게시판 상태를 지운다 (계정은 유지).
    DB 전체를 지우므로 시연 모드(DEMO_MODE=1)에서만 열린다."""
    if not config.DEMO_MODE:
        return HTMLResponse("Not Found", status_code=404)
    if not _account(request):
        return _login_redirect()
    entity.reset_demo_data()
    mockdata.reset()
    collect_ctl.last_run.update(at=None, result=None)
    return RedirectResponse("/notices", status_code=303)


# ------------------------------------------------------------------ UC5 공고 목록·상세 (5-1 ~ 5-6)
@app.get("/notices", response_class=HTMLResponse)
def notices(request: Request, view: str = "possible", saved: str = "", past: int = 0):
    aid = _account(request)
    if not aid:
        return _login_redirect()
    data = query_ctl.request_list(aid, "all" if view == "all" else "possible", include_past=bool(past and view == "all"))
    if data["profile"] is None:                             # UC5 예외 1 → 2-1
        return RedirectResponse("/profile?first=1", status_code=303)
    return _render(request, "notices.html", aid, data=data, saved=saved, collecting=collect_ctl._lock.locked(),
                   past=bool(past))


@app.get("/notices/{notice_id}", response_class=HTMLResponse)
def notice_detail(request: Request, notice_id: int, back: str = "possible"):
    aid = _account(request)
    if not aid:
        return _login_redirect()
    d = query_ctl.request_detail(aid, notice_id)
    if d is None:
        return RedirectResponse("/notices", status_code=303)
    return _render(request, "detail.html", aid, d=d, back=back)


# ------------------------------------------------------------------ 추출 API 비교 (시연·측정 도구)
@app.get("/compare", response_class=HTMLResponse)
def compare_page(request: Request, show: str = ""):
    if not config.DEMO_MODE:
        return HTMLResponse("Not Found", status_code=404)
    aid = _account(request)
    if not aid:
        return _login_redirect()
    res = evaluation.latest()
    return _render(request, "compare.html", aid, avail=evaluation.availability(), res=res, state=evaluation.state,
                   labels=evaluation.load_labels(), show=show, llm_mode=config.LLM_MODE,
                   targets=evaluation.TARGETS)


@app.post("/compare/run")
def compare_run(request: Request, mode: str = Form("auto")):
    if not config.DEMO_MODE:
        return HTMLResponse("Not Found", status_code=404)
    if not _account(request):
        return _login_redirect()
    evaluation.start_background(mode if mode in ("auto", "replay", "live") else "auto")
    return RedirectResponse("/compare", status_code=303)
