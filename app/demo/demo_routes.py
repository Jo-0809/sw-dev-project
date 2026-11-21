"""시연 화면·패널 (시연 모드 전용) — 지금 수집, 시연 초기화, 추출 API 비교, 수집 상태 패널.

install(app) 을 app/main.py 가 DEMO_MODE=1 일 때만 부른다. 화면 공통(app/hci/common.py)의 등록 함수로
관심 출처 화면·공고 목록 화면에 패널을 끼운다. 그래서 HCI·PD 계층은 이 모듈을 모른다.
"""

import threading
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from .. import config
from ..hci import common
from ..pd.collect import extract_ctl, failure
from ..pd.collect.collect_ctl import collector
from ..pd.collect.collect_scheduler import INTERVAL_MIN, scheduler
from . import evaluation, examples, mockboard, seed

router = APIRouter()


@router.post("/collect")
def collect_now(request: Request):
    """수집 주기를 기다리지 않고 수집 스케줄러가 하는 일을 지금 실행한다."""
    if not common.current_account(request):
        return common.login_redirect()
    if not collector.is_running():
        threading.Thread(target=collector.start, daemon=True).start()
    return common.redirect("/sources?msg=collecting")


@router.post("/demo/reset")
def demo_reset(request: Request):
    """수집한 공지·조건·기록·프로필·관심 출처와 모의 게시판 상태를 지운다 (계정은 유지)."""
    if not config.DEMO_MODE:
        return HTMLResponse("Not Found", status_code=404)
    if not common.current_account(request):
        return common.login_redirect()
    seed.reset_demo_data()
    collector.reset_last_run()
    return common.redirect("/notices")


@router.get("/compare", response_class=HTMLResponse)
def compare_page(request: Request, show: str = ""):
    if not config.DEMO_MODE:
        return HTMLResponse("Not Found", status_code=404)
    aid = common.current_account(request)
    if not aid:
        return common.login_redirect()
    return common.render(
        request,
        "compare.html",
        aid,
        avail=evaluation.availability(),
        res=evaluation.latest(),
        state=evaluation.state,
        labels=evaluation.load_labels(),
        show=show,
        llm_mode=config.LLM_MODE,
        targets=evaluation.TARGETS,
    )


@router.post("/compare/run")
def compare_run(request: Request, mode: str = Form("auto")):
    if not config.DEMO_MODE:
        return HTMLResponse("Not Found", status_code=404)
    if not common.current_account(request):
        return common.login_redirect()
    evaluation.start_background(mode if mode in ("auto", "replay", "live") else "auto")
    return common.redirect("/compare")


def _source_panel(request, account_id):
    return common.fragment(
        "source_panel.html",
        request,
        last_run=collector.last_run,
        failures=failure.recent(8),
        next_run=scheduler.next_run(),
        interval=INTERVAL_MIN,
        collecting=collector.is_running(),
        msg=request.query_params.get("msg", ""),
    )


def _list_panel(request, account_id):
    return common.fragment("list_panel.html", request, collecting=collector.is_running())


def install(app):
    common.add_template_dir(Path(__file__).resolve().parent / "templates")
    app.include_router(mockboard.router)
    app.include_router(router)
    common.register_nav("compare", "/compare", "추출 API 비교")
    common.register_footer(lambda: '시연 모드 · <a href="/mock/admin" target="_blank">모의 게시판 관리</a>')
    common.register_panel("source_view", "bottom", _source_panel)
    common.register_panel("list_view", "top", _list_panel)
    extract_ctl.set_example_provider(examples.fallback)  # 키·녹화가 없을 때: 예시 결과 → 규칙 기반
