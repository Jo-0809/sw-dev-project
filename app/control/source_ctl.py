"""<<control>> 출처 등록 제어 — 관심 출처 조회·등록·해제, 직접 입력한 주소 확인 (UC3).
흐름 번호는 LMS 최종본 놓칠뻔_중간발표자료_FINAL.pdf (2026-10-11 23:27) 04-2·09-1 명세서 기준 (README 참고).

정상 3~5 목록에서 고른 출처 등록 (robots.txt로 금지된 게시판이면 등록하지 않음, 제약사항 03-2)
대안 1   목록에 없는 주소 직접 입력 → 접속 확인 → robots.txt 확인 → 게시글 목록 확인 → 출처 추가
예외 1   접속 불가 → '해당 주소에 접속할 수 없습니다'
예외 2   robots.txt 금지 → '수집이 허용되지 않는 게시판입니다'
예외 3   HTTP 200인데 게시글 목록이 없음(게시판 번호 오타 → '시스템안내') → '공지를 가져올 수 없는 주소입니다'
         수집 때와 같은 해석 규칙(응답 해석기)으로 RSS → 목록 HTML 순서로 게시물 번호를 찾아 본다.
         (출처 등록 제어 → 응답 해석기: 클래스 다이어그램 v4에 없는, 구현 단계에서 추가된 의존)
(명세 밖) robots.txt 를 읽지 못함 → 등록 보류 메시지 (UC3에 없는 경우)
"""
from urllib.parse import parse_qs, urlparse

from .. import config
from ..boundary import web_client
from ..entity import Source, Subscription
from . import parser, robots_rule


DEMO_KINDS = ("mock", "test")               # 모의 게시판·실패 확인 출처 (시연 모드에서만 보임)


def usable(source):
    return config.DEMO_MODE or source["kind"] not in DEMO_KINDS


def request_list(account_id):                # 목록을 요청한다(계정) : 출처 목록, 등록 목록
    registered = [s for s in Subscription.find(account_id) if usable(s)]
    reg_ids = {s["id"] for s in registered}
    available = [s for s in Source.all() if s["id"] not in reg_ids and usable(s)]
    return available, registered


MSG_BLOCKED = "수집이 허용되지 않는 게시판입니다"
MSG_UNKNOWN = "robots.txt를 확인하지 못해 등록을 보류했습니다. 잠시 후 다시 시도하세요"
MSG_UNREACHABLE = "해당 주소에 접속할 수 없습니다"
MSG_NO_POSTS = "공지를 가져올 수 없는 주소입니다"


def _has_posts(candidate):                   # 게시글 목록이 있는지 (수집 제어와 같은 해석 규칙)
    """RSS → 목록 HTML 순서로 게시물 번호를 찾는다. 응답이 없으면 WebError."""
    if candidate.get("rss") and candidate.get("mi") and candidate.get("bbs_id"):
        try:
            if parser.extract_numbers_from_rss(web_client.request_rss(candidate)):
                return True
        except web_client.WebError:
            pass                             # RSS가 안 되면 목록 HTML로 (UC4 대안 1과 같은 길)
    return bool(parser.extract_numbers_from_list(web_client.request_list(candidate)))


def _board_urls(source):
    urls = [web_client.list_url(source)]
    if source.get("rss") and source.get("mi") and source.get("bbs_id"):
        urls.append(web_client.rss_url(source))
    return urls


def _robots_verdict(urls):
    """금지가 하나라도 있으면 금지, 확인 불가가 있으면 확인 불가, 아니면 허용."""
    states = [robots_rule.decide(web_client.read_robots(u), u) for u in urls]   # robots.txt를 읽는다 → 판정한다
    if robots_rule.BLOCKED in states:
        return robots_rule.BLOCKED
    if robots_rule.UNKNOWN in states:
        return robots_rule.UNKNOWN
    return robots_rule.ALLOWED


def register(account_id, source_id):         # 등록한다(계정, 출처) : (성공 여부, 메시지)
    source = Source.get(source_id)
    if not source or not usable(source):
        return False, "없는 출처입니다"
    verdict = _robots_verdict(_board_urls(source))
    if verdict == robots_rule.BLOCKED:
        return False, MSG_BLOCKED
    if verdict == robots_rule.UNKNOWN:
        return False, MSG_UNKNOWN
    Subscription.save(account_id, source_id)
    return True, None


def release(account_id, source_id):          # 해제한다(계정, 출처)
    Subscription.remove(account_id, source_id)


def _parse_board_url(url):
    """{사이트}/na/ntt/selectNttList.do?mi=..&bbsId=.. 형태면 (사이트, mi, bbsId)."""
    p = urlparse(url)
    if "/na/ntt/" in p.path:
        q = parse_qs(p.query)
        site = f"{p.scheme}://{p.netloc}{p.path.split('/na/ntt/')[0]}"
        mi, bbs = q.get("mi", [None])[0], q.get("bbsId", [None])[0]
        if mi and bbs:
            return site, mi, bbs
    return None


def register_address(account_id, url):       # 주소를 등록한다(계정, 주소)
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return False, "주소는 http:// 또는 https:// 로 시작해야 합니다", None
    if not web_client.check_reachable(url):                       # 접속을 확인한다(주소)
        return False, MSG_UNREACHABLE, None                       # 예외 1
    board = _parse_board_url(url)
    targets = [url]
    if board:
        site, mi, bbs = board
        targets.append(f"{site}/na/ntt/selectRssFeed.do?mi={mi}&bbsId={bbs}")
    verdict = _robots_verdict(targets)                            # robots.txt를 읽고 판정한다
    if verdict == robots_rule.BLOCKED:
        return False, MSG_BLOCKED, None                           # 예외 2
    if verdict == robots_rule.UNKNOWN:
        return False, MSG_UNKNOWN, None                           # 명세 밖: 규칙을 모르면 등록하지 않음
    p = urlparse(url)
    if board:
        site, mi, bbs = board
        candidate = {"site_url": site, "mi": mi, "bbs_id": bbs, "rss": 1, "list_url": None}
    else:
        candidate = {"site_url": f"{p.scheme}://{p.netloc}", "mi": None, "bbs_id": None, "rss": 0, "list_url": url}
    try:
        if not _has_posts(candidate):                             # 게시글 목록을 확인한다(주소)
            return False, MSG_NO_POSTS, None                      # 예외 3
    except web_client.WebError:
        return False, MSG_UNREACHABLE, None                       # 목록 응답이 없으면 예외 1과 같게
    if board:
        sid = Source.add(f"직접 입력 · {p.netloc}{p.path.split('/na/ntt/')[0]} (게시판 {bbs})",
                         site, mi=mi, bbs_id=bbs, rss=1, kind="custom")
    else:
        sid = Source.add(f"직접 입력 · {p.netloc}{p.path}", f"{p.scheme}://{p.netloc}", rss=0,
                         list_url=url, kind="custom")
    Subscription.save(account_id, sid)
    return True, "다음 수집부터 이 출처의 공지를 모아요", sid
