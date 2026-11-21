"""게시판 HTML·RSS 읽기 (설계 외 보조 모듈) — 게시물 번호 추출, '시스템안내' 화면 판별.

응답 해석기(공지수집)와 홈페이지 연결(외부)이 함께 쓴다. 출처 등록 때 UC3 예외 3(게시글 목록 없음)을
홈페이지 연결의 '접속을 확인한다'에서 판정하려고 응답 해석기에서 이 부분만 떼어 냈다 (팀 결정 해결안 3).
해석 규칙은 조원이 만든 수집기 v4(2026-10-11 실제 학교 응답으로 검증)의 collector/parser.py 와 같다.
  목록  .BD_list tbody 의 <a href="javascript:" data-id="번호"> 또는 goTo.view('list','번호',...)
  RSS   <item><link>...selectNttInfo.do?nttSn=번호&mi=..</link>
  잘못된 게시판은 HTTP 200 + '시스템안내' 화면 → 상태 코드가 아니라 화면 내용으로 판정
"""

import re
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup, FeatureNotFound

NTT_SN_KEYS = ("nttSn", "nttNo", "bbsNo")
DIGITS = re.compile(r"\d{4,}")
LIST_SCOPE_SELECTORS = [".BD_list tbody", ".board_list tbody", ".bbs_ListA tbody", "table tbody"]
VIEW_CALL = re.compile(r"goTo\.view|fn_?\w*[Vv]iew\w*\s*\(|\bview\s*\(")
DATA_KEYS = ("data-id", "data-ntt-sn", "data-nttsn", "data-sn")
ERROR_MARKERS = ("시스템안내", "요청하신 페이지를 찾을 수 없")
STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "caption", "form"]
STRIP_WORDS = (
    "gnb",
    "lnb",
    "snb",
    "nav",
    "menu",
    "header",
    "footer",
    "skip",
    "util",
    "breadcrumb",
    "sitemap",
    "quick",
    "search",
    "visual",
    "logo",
)


def _ntt_sn_from_url(url):
    q = parse_qs(urlparse(url).query)
    for key in NTT_SN_KEYS:
        if q.get(key):
            return q[key][0]
    return None


# ---------------------------------------------------------------- RSS
def _rss_links(xml_text):
    """RSS의 <item><link> 값들. lxml(BeautifulSoup 'xml' 해석기)이 있으면 그것으로, 없으면 표준 라이브러리로 읽는다.
    lxml이 없는 PC에서 RSS 출처가 조용히 모두 실패하던 문제 대비 (requirements.txt 에도 lxml 넣음)."""
    try:
        soup = BeautifulSoup(xml_text, "xml")
        return [item.link.get_text(strip=True) for item in soup.find_all("item") if item.link]
    except FeatureNotFound:
        pass
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
        return [(item.findtext("link") or "").strip() for item in root.iter("item")]
    except ElementTree.ParseError:
        return [
            m.strip()
            for m in re.findall(r"<item\b.*?<link>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</link>", xml_text, flags=re.S)
        ]


def extract_numbers_from_rss(xml_text):  # 게시물 번호를 추출한다(응답) : 번호 목록  (RSS)
    nums = []
    for link in _rss_links(xml_text):
        n = _ntt_sn_from_url(link)
        if n and n not in nums:
            nums.append(n)
    return nums


# ---------------------------------------------------------------- 목록 HTML (RSS가 없을 때)
def strip_chrome(soup):
    """메뉴·머리말·꼬리말을 지운다. 바깥 칸을 지우면 안쪽도 떨어져 나가므로 살아 있는지 확인하며 돈다."""
    for node in list(soup.find_all(STRIP_TAGS)):
        if getattr(node, "attrs", None) is not None:
            node.decompose()
    for node in list(soup.find_all(True)):
        attrs = getattr(node, "attrs", None)
        if not attrs:
            continue
        cls = attrs.get("class") or []
        if isinstance(cls, str):
            cls = [cls]
        key = (str(attrs.get("id", "")) + " " + " ".join(cls)).lower()
        if any(w in key for w in STRIP_WORDS):
            node.decompose()


def extract_numbers_from_list(html):  # 게시물 번호를 추출한다(응답) : 번호 목록  (목록 HTML 폴백)
    """제목 링크는 href가 아니라 javascript 호출이다. 번호는 data 속성(실제 학과 게시판)이나
    goTo.view 함수 인자에 있다. 메뉴 링크 fn_goMenu('10200') 를 번호로 뽑지 않게 게시판 표 안만 본다."""
    soup = BeautifulSoup(html, "html.parser")
    scope = None
    for sel in LIST_SCOPE_SELECTORS:
        scope = soup.select_one(sel)
        if scope is not None:
            break
    if scope is None:
        strip_chrome(soup)
        scope = soup
    links = scope.select("a")

    def is_view(a):
        if VIEW_CALL.search(f"{a.get('href') or ''} {a.get('onclick') or ''}"):
            return True
        return any((a.get(k) or "").strip().isdigit() and len((a.get(k) or "").strip()) >= 4 for k in DATA_KEYS)

    view_links = [a for a in links if is_view(a)]
    if view_links:
        links = view_links
    nums = []
    for a in links:
        href, onclick = a.get("href") or "", a.get("onclick") or ""
        if not a.get_text(strip=True):
            continue
        n = _ntt_sn_from_url(href) if href.startswith(("http", "/", "?")) else None
        if not n:
            for key in DATA_KEYS:
                v = (a.get(key) or "").strip()
                if v.isdigit() and len(v) >= 4:
                    n = v
                    break
        if not n:
            if "javascript" not in href.lower() and not onclick:
                continue
            found = DIGITS.findall(f"{href} {onclick}")
            if not found:
                continue
            n = max(found, key=len)
        if n not in nums:
            nums.append(n)
    return nums


def is_error_page(html_or_soup):
    """'시스템안내' 화면인지 본다. '오류가 발생' 같은 말은 정상 공지 제목에도 있어서 쓰지 않는다."""
    soup = html_or_soup if isinstance(html_or_soup, BeautifulSoup) else BeautifulSoup(html_or_soup, "html.parser")
    head = soup.title.get_text(strip=True) if soup.title else ""
    if any(m in head for m in ERROR_MARKERS):
        return True
    if any(n.get_text(" ", strip=True) == "시스템안내" for n in soup.find_all(["h1", "h2"])):
        return True
    return "요청하신 페이지를 찾을 수 없" in soup.get_text(" ", strip=True)
