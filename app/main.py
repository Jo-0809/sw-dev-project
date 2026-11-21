"""놓칠뻔 — 앱 조립만 한다 (화면 라우터 연결, 정적 파일, 시작·종료 처리).

계층: HCI(app/hci) → PD(app/pd) → DM(app/dm)   (ch11 36~37쪽)
시연 모드(DEMO_MODE=1)일 때만 app/demo 를 불러와 모의 게시판·시연 패널·대체 추출 결과를 넣는다.
이 파일은 계층 규칙 검사에서 빠진다 (모든 것을 조립하는 자리).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from markupsafe import escape

from . import config
from .dm import db
from .hci import common, detail_view, list_view, login_view, main_view, profile_view, source_view
from .pd.collect.collect_scheduler import scheduler
from .pd.external import llm_client, web
from .pd.source import presets
from .pd.user import account

FETCH_TEXT = {"replay": "저장된 실제 응답 재생", "live": "실제 요청", "record": "실제 요청 + 저장"}


def seed():
    db.init_db()
    presets.seed()
    if config.DEMO_MODE:
        from .demo import seed as demo_seed

        demo_seed.run()
    elif account.count() == 0:
        logging.getLogger("uvicorn").warning(
            "[놓칠뻔] 로그인할 계정이 없습니다. 'python tools/create_account.py 아이디' 로 만드세요 "
            "(시연이면 .env 에 DEMO_MODE=1)."
        )


@asynccontextmanager
async def lifespan(app):
    seed()
    scheduler.start()
    yield
    scheduler.stop()


def _status_footer():
    return (
        f"조건 추출: {escape(llm_client.status_text())} · "
        f"학교 사이트: {escape(FETCH_TEXT.get(config.FETCH_MODE, config.FETCH_MODE))}"
    )


def _fetch_banner(request, account_id):
    return common.fragment(
        "fetch_banner.html",
        request,
        fetch_mode=config.FETCH_MODE,
        record_info=web.record_info(),
        demo_mode=config.DEMO_MODE,
    )


app = FastAPI(title="놓칠뻔", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=common.STATIC_DIR), name="static")
for view in (main_view, login_view, profile_view, source_view, list_view, detail_view):
    app.include_router(view.router)
common.register_footer(_status_footer)
common.register_panel("source_view", "top", _fetch_banner)
if config.DEMO_MODE:
    from .demo import demo_routes

    demo_routes.install(app)
