"""구조 규칙 검사 — 계층(HCI → PD → DM), 패키지 의존(패키지 다이어그램 10개), 화면별 패키지, app.demo 분리.

import 문을 읽어(ast) 검사한다. 예외로 두는 것(TEMPORARY_EXCEPTIONS)은 없다.
  app/main.py : 조립 자리라 검사하지 않는다 (app.demo 도 여기서만 부른다)
  app/hci/common.py : 화면 공통(설계 외 보조 모듈). 사용자 패키지와 설정만 쓸 수 있다
  app/config.py : 모든 계층이 쓸 수 있다
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

LAYER_FORBIDDEN = {"hci": {"dm"}, "pd": {"hci"}, "dm": {"hci", "pd"}}
PACKAGE_ALLOWED = {
    "collect": {"source", "notice", "external"},
    "notify": {"notice", "user", "external"},
    "notice": {"source", "user"},
    "source": {"user", "external"},
    "user": set(),
    "external": set(),
}
HCI_PACKAGE = {
    "login_view": "user",
    "main_view": "user",
    "profile_view": "user",
    "source_view": "source",
    "list_view": "notice",
    "detail_view": "notice",
}
HCI_COMMON_ALLOWED = {"user"}


def _modules():
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP.parent).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        yield path, ".".join(parts)


def _imports(path, modname):
    """이 파일이 불러오는 app 안의 모듈 이름들 (상대 import 는 절대 이름으로 바꿈)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    is_pkg = path.name == "__init__.py"
    base = modname.split(".") if is_pkg else modname.split(".")[:-1]
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                root = base[: len(base) - (node.level - 1)]
                mod = ".".join(root + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            out.append(mod)
            out += [f"{mod}.{a.name}" for a in node.names]  # from ..pd import user 같은 경우
    return [m for m in out if m == "app" or m.startswith("app.")]


def _layer(mod):
    parts = mod.split(".")
    return parts[1] if len(parts) > 1 and parts[1] in ("hci", "pd", "dm", "demo") else None


def _pd_package(mod):
    parts = mod.split(".")
    return parts[2] if len(parts) > 2 and parts[1] == "pd" else None


def _violations():
    found = []
    for path, mod in _modules():
        if mod in ("app.main", "app.config", "app"):
            continue
        layer = _layer(mod)
        if layer == "demo":
            continue  # 시연 코드는 계층 밖 (아래 계층을 불러 쓰는 쪽)
        for target in _imports(path, mod):
            t_layer = _layer(target)
            if t_layer == "demo":
                found.append(f"{mod} → {target}: 운영 코드가 app.demo 를 불러옴")
                continue
            if t_layer in LAYER_FORBIDDEN.get(layer, set()):
                found.append(f"{mod} → {target}: {layer} 계층은 {t_layer} 계층을 쓸 수 없음")
            src_pkg, dst_pkg = _pd_package(mod), _pd_package(target)
            if layer == "pd" and dst_pkg and src_pkg != dst_pkg:
                if src_pkg not in PACKAGE_ALLOWED:
                    found.append(f"{mod}: 패키지 다이어그램에 없는 패키지 {src_pkg}")
                elif dst_pkg not in PACKAGE_ALLOWED[src_pkg]:
                    found.append(f"{mod} → {target}: {src_pkg} → {dst_pkg} 의존은 패키지 다이어그램에 없음")
            if layer == "hci" and dst_pkg:
                view = mod.split(".")[-1]
                if view == "common":
                    allowed = HCI_COMMON_ALLOWED
                elif view in HCI_PACKAGE:
                    allowed = {HCI_PACKAGE[view]}
                elif mod == "app.hci":
                    allowed = set()
                else:
                    found.append(f"{mod}: HCI_PACKAGE 에 없는 화면")
                    continue
                if dst_pkg not in allowed:
                    found.append(f"{mod} → {target}: 이 화면은 {sorted(allowed)} 패키지만 부를 수 있음")
        if layer == "hci" and mod not in ("app.hci", "app.hci.common") and mod.split(".")[-1] not in HCI_PACKAGE:
            found.append(f"{mod}: HCI_PACKAGE 에 없는 화면")  # import 가 없어도 표에 없으면 위반
        if layer == "pd":
            pkg = _pd_package(mod)
            if pkg is not None and pkg not in PACKAGE_ALLOWED:
                found.append(f"{mod}: 패키지 다이어그램에 없는 패키지 {pkg}")
    return sorted(set(found))


def test_layers_packages_and_demo_separation():
    assert _violations() == []


def test_package_diagram_has_10_acyclic_dependencies():
    edges = [(a, b) for a, bs in PACKAGE_ALLOWED.items() for b in bs]
    assert len(edges) == 10
    seen, stack = set(), set()

    def visit(n):
        assert n not in stack, f"순환 의존: {n}"
        if n in seen:
            return
        stack.add(n)
        for m in PACKAGE_ALLOWED[n]:
            visit(m)
        stack.discard(n)
        seen.add(n)

    for n in PACKAGE_ALLOWED:
        visit(n)


def test_pd_packages_match_folders():
    folders = {p.name for p in (APP / "pd").iterdir() if p.is_dir() and not p.name.startswith("_")}
    assert folders == set(PACKAGE_ALLOWED)
    views = {p.stem for p in (APP / "hci").glob("*_view.py")}
    assert views == set(HCI_PACKAGE)


def test_checker_catches_violations(tmp_path, monkeypatch):
    """검사기 자체 확인: 금지된 import 를 넣은 가짜 모듈을 만들면 잡아낸다."""
    import shutil

    fake = tmp_path / "app"
    shutil.copytree(APP, fake, ignore=shutil.ignore_patterns("__pycache__", "static", "templates", "fixtures"))
    (fake / "pd" / "source" / "bad.py").write_text("from ..collect import parser\n", encoding="utf-8")
    (fake / "hci" / "list_view.py").write_text("from ..pd.user import account\nfrom ..dm import db\n", encoding="utf-8")
    (fake / "pd" / "notice" / "bad2.py").write_text("from ...demo import examples\n", encoding="utf-8")
    (fake / "hci" / "new_view.py").write_text("x = 1\n", encoding="utf-8")  # 표에 없는 새 화면 (import 없음)
    (fake / "hci" / "common.py").write_text("from ..pd.collect import collect_ctl\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "APP", fake)
    v = "\n".join(_violations())
    assert "source → collect" in v and "dm 계층" in v and "['notice'] 패키지만" in v and "app.demo" in v
    assert "app.hci.new_view: HCI_PACKAGE 에 없는 화면" in v
    assert "app.hci.common → app.pd.collect" in v  # common.py 는 사용자 패키지만
