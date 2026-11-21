"""화면 공통 (설계 외 보조 모듈) — 쿠키로 로그인 확인, 템플릿 그리기, 화면에 끼울 패널·꼬리말 등록.

이 모듈은 사용자 패키지(로그인 제어)와 설정만 부른다. 시연 패널(app/demo)이나 시스템 상태 같은 것은
app/main.py 가 register_* 로 넣는다. 그래서 HCI 계층은 app.demo 를 불러오지 않는다.
"""

from pathlib import Path

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader
from markupsafe import Markup

from .. import config
from ..pd.user import login_ctl

HCI_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = HCI_DIR / "templates"
STATIC_DIR = HCI_DIR / "static"
COOKIE = "nc_session"
AUTO_LOGIN_MAX_AGE = config.AUTO_LOGIN_DAYS * 24 * 3600

templates = Jinja2Templates(directory=TEMPLATE_DIR)
_loaders = [FileSystemLoader(TEMPLATE_DIR)]
templates.env.loader = ChoiceLoader(_loaders)

_panels = {}  # (화면, 자리) → [fn(request, account_id) → HTML]
_footer = []  # [fn() → HTML]
_nav = []  # [(key, href, 글자)]


def add_template_dir(path):
    """다른 폴더의 템플릿도 찾게 한다 (시연 화면 템플릿)."""
    _loaders.append(FileSystemLoader(path))
    templates.env.loader = ChoiceLoader(_loaders)


def register_panel(view, slot, fn):
    """view 화면의 slot('top' 또는 'bottom') 자리에 끼울 HTML을 만드는 함수를 등록한다."""
    _panels.setdefault((view, slot), []).append(fn)


def register_footer(fn):
    _footer.append(fn)


def register_nav(key, href, label):
    _nav.append((key, href, label))


def fragment(name, request, **ctx):
    """패널용: 템플릿 하나를 HTML 문자열로 그린다."""
    return Markup(templates.env.get_template(name).render(request=request, **ctx))


def current_account(request):
    return login_ctl.auto_login(request.cookies.get(COOKIE))


def login_redirect():
    return RedirectResponse("/login", status_code=303)


def redirect(url):
    return RedirectResponse(url, status_code=303)


def render(request, name, account_id=None, **ctx):
    view = name.rsplit(".", 1)[0]
    ctx.update(
        request=request,
        account_id=account_id,
        today=config.today(),
        demo_today=bool(config._demo_today),
        demo_mode=config.DEMO_MODE,
        no_account=not login_ctl.has_accounts(),
        demo_id=config.DEMO_ID if config.DEMO_MODE else None,
        nav_extra=list(_nav),
        footer_items=[Markup(f()) for f in _footer],
    )
    for slot in ("top", "bottom"):
        ctx[f"panel_{slot}"] = [Markup(f(request, account_id)) for f in _panels.get((view, slot), [])]
    if account_id:
        ctx.setdefault("login_id", login_ctl.login_id_of(account_id))
    return templates.TemplateResponse(request, name, ctx)
