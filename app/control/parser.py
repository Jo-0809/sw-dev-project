"""<<control>> 응답 해석기 — RSS·목록 HTML에서 게시물 번호를, 상세 HTML에서 제목·본문·첨부 링크를 뽑는다.

해석 규칙은 조원이 만든 수집기 v4(notchilppeon-collector, 2026-10-11 실제 학교 응답으로 검증)의
collector/parser.py 를 그대로 옮겼다. 바뀐 것은 반환 형식(dict)과 함수 이름(클래스 다이어그램 연산)뿐이다.

v4에서 확인한 실제 화면 구조 (경상국립대 게시판)
  상세  .BD_table th.title (제목), .BD_table tr.cont td (본문), th[scope=row] 행 (등록일·부서·연락처)
  목록  .BD_list tbody 의 <a href="javascript:" data-id="번호"> 또는 goTo.view('list','번호',...)
  RSS   <item><link>...selectNttInfo.do?nttSn=번호&mi=..</link>
발견 사항
  - 잘못된 게시판은 HTTP 200 + '시스템안내' 화면 → 상태 코드가 아니라 게시글 영역 유무로 판정
  - 본문에 '첨부파일' 글자가 있어도 본문 → 글자가 아니라 다운로드 링크가 있는 줄만 뺀다
  - 본문이 이미지 한 장인 공지가 있다 → 수집 실패가 아니라 '확인 필요'로 저장한다
"""
import re
from copy import copy
from urllib.parse import parse_qs, urljoin, urlparse

from xml.etree import ElementTree

from bs4 import BeautifulSoup, FeatureNotFound

# ---- 선택자 후보 (앞에서부터, 먼저 맞는 것을 쓴다). 맨 앞은 실제 학교 화면에서 확인한 것 ----
TITLE_SELECTORS = [".BD_table th.title", ".bbs_ViewA h2", ".board_view .title", ".view_title", "#bbs_title", "h2.title"]
DATE_SELECTORS = [".bbs_ViewA .date", ".board_view .date", ".view_info .date", ".write_date"]
BODY_SELECTORS = [".BD_table tr.cont td", ".bbs_ViewA .bbsV_cont", ".board_view .cont", ".view_cont",
                  "#bbs_content", ".bbs_content"]
META_ROW_SELECTOR = ".BD_table tr, .board_view tr"
META_SKIP = ("첨부파일", "첨부")
ATTACH_HREF_MARK = "nttFileDownload.do"          # robots.txt 의 Disallow: /common/ 과 같은 경로
NTT_SN_KEYS = ("nttSn", "nttNo", "bbsNo")
DIGITS = re.compile(r"\d{4,}")
LIST_SCOPE_SELECTORS = [".BD_list tbody", ".board_list tbody", ".bbs_ListA tbody", "table tbody"]
VIEW_CALL = re.compile(r"goTo\.view|fn_?\w*[Vv]iew\w*\s*\(|\bview\s*\(")
DATA_KEYS = ("data-id", "data-ntt-sn", "data-nttsn", "data-sn")

MIN_BODY_CHARS = 80
MAX_LINK_RATIO = 0.4
BLOCK_TAGS = ["div", "td", "article", "section", "dd"]
ERROR_MARKERS = ("시스템안내", "요청하신 페이지를 찾을 수 없")
STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "caption", "form"]
STRIP_WORDS = ("gnb", "lnb", "snb", "nav", "menu", "header", "footer", "skip",
               "util", "breadcrumb", "sitemap", "quick", "search", "visual", "logo")
DATE_RE = re.compile(r"(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})")
IMAGE_ONLY_NOTE = "본문이 이미지라 텍스트를 얻지 못함 (원문에서 직접 확인)"


def ntt_sn_from_url(url):
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
        return [m.strip() for m in re.findall(r"<item\b.*?<link>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</link>",
                                              xml_text, flags=re.S)]


def extract_numbers_from_rss(xml_text):      # 게시물 번호를 추출한다(응답) : 번호 목록  (RSS)
    nums = []
    for link in _rss_links(xml_text):
        n = ntt_sn_from_url(link)
        if n and n not in nums:
            nums.append(n)
    return nums


# ---------------------------------------------------------------- 목록 HTML (RSS가 없을 때)
def _strip_chrome(soup):
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


def extract_numbers_from_list(html):         # 게시물 번호를 추출한다(응답) : 번호 목록  (목록 HTML 폴백)
    """제목 링크는 href가 아니라 javascript 호출이다. 번호는 data 속성(실제 학과 게시판)이나
    goTo.view 함수 인자에 있다. 메뉴 링크 fn_goMenu('10200') 를 번호로 뽑지 않게 게시판 표 안만 본다."""
    soup = BeautifulSoup(html, "html.parser")
    scope = None
    for sel in LIST_SCOPE_SELECTORS:
        scope = soup.select_one(sel)
        if scope is not None:
            break
    if scope is None:
        _strip_chrome(soup)
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
        n = ntt_sn_from_url(href) if href.startswith(("http", "/", "?")) else None
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


# ---------------------------------------------------------------- 상세 HTML
def _first_text(soup, selectors):
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            text = node.get_text(" ", strip=True)
            if text:
                return text
    return None


def _first_node(soup, selectors):
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            return node
    return None


def is_error_page(html_or_soup):
    """'시스템안내' 화면인지 본다. '오류가 발생' 같은 말은 정상 공지 제목에도 있어서 쓰지 않는다."""
    soup = html_or_soup if isinstance(html_or_soup, BeautifulSoup) else BeautifulSoup(html_or_soup, "html.parser")
    head = soup.title.get_text(strip=True) if soup.title else ""
    if any(m in head for m in ERROR_MARKERS):
        return True
    if any(n.get_text(" ", strip=True) == "시스템안내" for n in soup.find_all(["h1", "h2"])):
        return True
    return "요청하신 페이지를 찾을 수 없" in soup.get_text(" ", strip=True)


def _link_ratio(node):
    text = node.get_text(" ", strip=True)
    if not text:
        return 1.0
    return sum(len(a.get_text(" ", strip=True)) for a in node.find_all("a")) / len(text)


def _guess_body(soup):
    best, best_score = None, 0.0
    for node in soup.find_all(BLOCK_TAGS):
        text = node.get_text(" ", strip=True)
        if len(text) < MIN_BODY_CHARS:
            continue
        ratio = _link_ratio(node)
        if ratio > MAX_LINK_RATIO:
            continue
        score = len(text) * (1 - ratio)
        if score > best_score:
            best, best_score = node, score
    if best is None:
        return None
    for _ in range(6):                                   # 껍데기만 두른 바깥 칸이면 안쪽으로
        outer = len(best.get_text(" ", strip=True))
        inner = None
        for child in best.find_all(BLOCK_TAGS, recursive=False):
            t = len(child.get_text(" ", strip=True))
            if t >= outer * 0.9 and t >= MIN_BODY_CHARS:
                inner = child
                break
        if inner is None:
            break
        best = inner
    return best


def _guess_title(soup):
    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content", "").strip():
        return og["content"].strip()
    for tag in ("h1", "h2", "h3", "h4"):
        for node in soup.find_all(tag):
            t = node.get_text(" ", strip=True)
            if 5 <= len(t) <= 120 and _link_ratio(node) < 0.5:
                return t
    if soup.title and soup.title.get_text(strip=True):
        parts = [s.strip() for s in re.split(r"[|>\-–]", soup.title.get_text(strip=True)) if len(s.strip()) >= 5]
        if parts:
            return max(parts, key=len)
    return None


def _block_text(node):
    """본문을 문단 단위로 합친다. 한글에서 붙여넣은 HTML은 한 문장이 span 여러 개로 쪼개져 있어서
    줄바꿈은 블록 태그에서만 넣는다 ('학생과 - 10381' 처럼 벌어지는 것 방지)."""
    node = copy(node)
    for br in node.find_all("br"):
        br.replace_with("\n")
    for block in node.find_all(["p", "div", "li", "tr", "table", "h1", "h2", "h3", "h4"]):
        block.insert_after("\n")
    text = re.sub(r"[ \t ]+", " ", node.get_text(""))
    text = "\n".join(line.strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def read_meta(soup):
    """상세 표의 머리말 행 (등록일, 구분, 부서, 연락처 등)."""
    out = {}
    for tr in soup.select(META_ROW_SELECTOR):
        th, td = tr.find("th"), tr.find("td")
        if not th or not td:
            continue
        key = th.get_text(strip=True)
        if th.get("scope") != "row" and (th.get("colspan") or len(key) > 8):
            continue
        if not key or key in META_SKIP:
            continue
        val = td.get_text(" ", strip=True)
        if val:
            out[key] = val
    return out


def _locate(soup):
    """(제목, 본문 칸, 등록일, 찾은 방법). 선택자로 먼저 찾고, 못 찾았을 때만 '시스템안내'인지 본다."""
    title = _first_text(soup, TITLE_SELECTORS)
    body = _first_node(soup, BODY_SELECTORS)
    meta_date = read_meta(soup).get("등록일")       # 폴백이 머리말 칸을 지우기 전에 먼저 읽는다
    found = bool(title) and body is not None and bool(body.get_text(strip=True))
    if not found and is_error_page(soup):
        return None, None, "", "안내 화면"
    how = "선택자"
    if not title:
        title, how = _guess_title(soup), "폴백"
    if body is None or not body.get_text(strip=True):
        kept = str(body) if body is not None else None    # 칸은 찾았는데 글자가 없음 = 이미지 한 장 공지
        try:
            _strip_chrome(soup)
            guessed = _guess_body(soup)
        except Exception:
            guessed = None
        if guessed is not None and len(guessed.get_text(" ", strip=True)) >= MIN_BODY_CHARS:
            body, how = guessed, "폴백"
        elif kept is not None:
            body, how = BeautifulSoup(kept, "html.parser"), "선택자"
        else:
            body = None
    date = meta_date or _first_text(soup, DATE_SELECTORS) or ""
    m = DATE_RE.search(date) or DATE_RE.search(soup.get_text(" ", strip=True))
    date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None
    return title, body, date, how


def check_post_area(html):                   # 게시글 영역을 확인한다(상세 HTML) : 게시글 영역 여부
    """HTTP 200이어도 '시스템안내' 화면이면 실패. 제목과 본문 칸이 모두 있을 때만 성공."""
    title, body, _, _ = _locate(BeautifulSoup(html, "html.parser"))
    return bool(title) and body is not None


def parse_detail(html, url, ntt_sn):         # 상세를 해석한다(상세 HTML) : 공지
    soup = BeautifulSoup(html, "html.parser")
    title, body_node, posted_at, how = _locate(soup)
    if not title or body_node is None:
        return None

    attachments = []                                     # 첨부는 링크만 (파일은 받지 않음)
    for a in soup.select("a[href]"):
        if ATTACH_HREF_MARK not in a["href"]:
            continue
        name = a.get_text(" ", strip=True) or a["href"].rsplit("/", 1)[-1]
        name = re.sub(r"\s*\(다운로드\s*:[^)]*\)\s*$", "", name).strip()
        href = urljoin(url, a["href"])
        if href not in [x["url"] for x in attachments]:
            attachments.append({"name": name, "url": href})

    for link in body_node.select(f'a[href*="{ATTACH_HREF_MARK}"]'):   # 본문 안 다운로드 줄 통째로 제외
        cell = link.find_parent(["td", "th", "li", "dd"])
        target = (cell.find_parent("tr") if cell else None) or cell or link
        target.decompose()
    body = _block_text(body_node)

    needs_review = len(body) < 30 and bool(body_node.find_all("img"))
    meta = {k: v for k, v in read_meta(soup).items() if k != "등록일"}
    return {"ntt_sn": str(ntt_sn), "title": title, "body": body, "url": url, "attachments": attachments,
            "posted_at": posted_at, "extracted_by": how, "meta": meta,
            "needs_review": needs_review, "review_reason": IMAGE_ONLY_NOTE if needs_review else None}
