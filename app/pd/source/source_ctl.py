"""<<control>> 출처 등록 제어 — 관심 출처 조회·등록·해제, 직접 입력한 주소 확인 (UC3).
흐름 번호는 LMS 최종본 놓칠뻔_중간발표자료_FINAL.pdf (2026-10-11 23:27) 04-2·09-1 명세서 기준.

정상 3~5 목록에서 고른 출처 등록 (robots.txt로 금지된 게시판이면 등록하지 않음, 제약사항 03-2)
대안 1   목록에 없는 주소 직접 입력. 순서:
           1) robots.txt 를 읽는다  — 응답이 아예 없으면 예외 1 (사이트에 접속할 수 없음)
           2) 판정한다            — 금지면 예외 2, 5xx로 규칙을 모르면 등록 보류 (명세 밖)
           3) 접속을 확인한다      — 홈페이지 연결이 목록(·RSS)을 받아 게시물 번호가 있는지까지 본다
                                     접속 불가면 예외 1, HTTP 200인데 게시글 목록이 없으면 예외 3
           4) 출처를 추가하고 관심 출처로 저장한다
예외 1   '해당 주소에 접속할 수 없습니다'
예외 2   '수집이 허용되지 않는 게시판입니다'
예외 3   '공지를 가져올 수 없는 주소입니다' (게시판 번호 오타 → HTTP 200 '시스템안내' 화면)
게시글 목록 확인은 홈페이지 연결(외부 패키지)이 한다 (팀 결정 해결안 3). 그래서 관심출처 → 공지수집 의존이 없다.
"""

from urllib.parse import parse_qs, urlparse

from ..external import web
from . import robots, source, subscription

MSG_BLOCKED = "수집이 허용되지 않는 게시판입니다"
MSG_UNKNOWN = "robots.txt를 확인하지 못해 등록을 보류했습니다. 잠시 후 다시 시도하세요"
MSG_UNREACHABLE = "해당 주소에 접속할 수 없습니다"
MSG_NO_POSTS = "공지를 가져올 수 없는 주소입니다"
MSG_ADDED = "다음 수집부터 이 출처의 공지를 모아요"


def request_list(account_id):  # 목록을 요청한다(계정) : 출처 목록, 등록 목록
    registered = subscription.find(account_id)
    reg_ids = {s["id"] for s in registered}
    available = [s for s in source.all() if s["id"] not in reg_ids]
    return available, registered


def name_of(source_id):  # 설계 외: 등록 거절 메시지용 이름
    s = source.get(source_id)
    return s["name"] if s else str(source_id)


def _board_urls(src):
    urls = [web.list_url(src)]
    if source.has_rss(src):
        urls.append(web.rss_url(src))
    return urls


def _robots_verdict(urls):
    """금지가 하나라도 있으면 금지, 확인 불가가 있으면 확인 불가, 아니면 허용.
    응답이 아예 없었던 주소가 있으면 '응답 없음'도 함께 돌려준다 (대안 1에서 예외 1로 쓴다)."""
    read = [web.read_robots(u) for u in urls]  # robots.txt를 읽는다(주소)
    no_answer = any(r[0] is None for r in read)
    states = [robots.decide(r, u) for r, u in zip(read, urls, strict=True)]  # 판정한다(규칙, 주소)
    if robots.BLOCKED in states:
        return robots.BLOCKED, no_answer
    if robots.UNKNOWN in states:
        return robots.UNKNOWN, no_answer
    return robots.ALLOWED, no_answer


def register(account_id, source_id):  # 등록한다(계정, 출처) : (성공 여부, 메시지)
    src = source.get(source_id)
    if not src or not source.visible(src):
        return False, "없는 출처입니다"
    verdict, _ = _robots_verdict(_board_urls(src))
    if verdict == robots.BLOCKED:
        return False, MSG_BLOCKED
    if verdict == robots.UNKNOWN:
        return False, MSG_UNKNOWN
    subscription.save(account_id, source_id)
    return True, None


def register_many(account_id, source_ids):  # 설계 외: 여러 개 선택 등록 (정상 3~5 반복)
    """선택한 출처마다 정상 3~5를 반복한다. (등록한 번호 목록, [(이름, 사유)])"""
    added, refused = [], []
    for sid in source_ids:
        ok, why = register(account_id, sid)
        if ok:
            added.append(sid)
        else:
            refused.append((name_of(sid), why))
    return added, refused


def release(account_id, source_id):  # 해제한다(계정, 출처)
    subscription.remove(account_id, source_id)


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


def register_address(account_id, url):  # 주소를 등록한다(계정, 주소) : (성공 여부, 메시지, 출처 번호)
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return False, "주소는 http:// 또는 https:// 로 시작해야 합니다", None
    board = _parse_board_url(url)
    candidate = (
        {"site_url": board[0], "mi": board[1], "bbs_id": board[2], "rss": 1, "list_url": None} if board else None
    )
    rss = web.rss_url(candidate) if candidate else None
    verdict, no_answer = _robots_verdict([url] + ([rss] if rss else []))  # 1) 2)
    if no_answer:
        return False, MSG_UNREACHABLE, None  # 예외 1
    if verdict == robots.BLOCKED:
        return False, MSG_BLOCKED, None  # 예외 2
    if verdict == robots.UNKNOWN:
        return False, MSG_UNKNOWN, None  # 명세 밖: 규칙을 모르면 등록하지 않음
    state = web.check_reachable(url, rss)  # 3) 접속을 확인한다(주소)
    if state == web.UNREACHABLE:
        return False, MSG_UNREACHABLE, None  # 예외 1
    if state == web.NO_POSTS:
        return False, MSG_NO_POSTS, None  # 예외 3
    p = urlparse(url)
    if board:  # 4) 추가한다(주소)
        site, mi, bbs = board
        sid = source.add(
            f"직접 입력 · {p.netloc}{p.path.split('/na/ntt/')[0]} (게시판 {bbs})", site, mi=mi, bbs_id=bbs, rss=1
        )
    else:
        sid = source.add(f"직접 입력 · {p.netloc}{p.path}", f"{p.scheme}://{p.netloc}", rss=0, list_url=url)
    subscription.save(account_id, sid)
    return True, MSG_ADDED, sid
