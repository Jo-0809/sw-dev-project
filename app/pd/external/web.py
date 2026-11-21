"""<<boundary>> 홈페이지 연결 — 학교·외부 기관 홈페이지에 HTTP 요청을 보낸다 (외부 패키지, PD 계층).

경상국립대 게시판은 본부와 학과·기관 사이트가 같은 시스템을 쓴다 (기술 조사 2-2).
  목록  {사이트}/na/ntt/selectNttList.do?mi={mi}&bbsId={bbsId}
  RSS   {사이트}/na/ntt/selectRssFeed.do?mi={mi}&bbsId={bbsId}
  상세  {사이트}/na/ntt/selectNttInfo.do?nttSn={번호}   (mi는 넣지 않는다: 틀린 mi는 '시스템안내' 화면이 됨)
첨부 파일은 robots.txt(/common/ 금지) 때문에 내려받지 않고 링크만 저장한다.

요청 방식 (.env 의 FETCH_MODE, 학교 사이트처럼 이 PC 밖의 주소에만 적용. 모의 게시판은 항상 실제 요청)
  replay : recordings/web/ 에 저장해 둔 실제 응답을 돌려준다. 네트워크 없이 발표할 때 (기본값)
  live   : 실제로 요청한다
  record : 실제로 요청하고 응답을 recordings/web/ 에 저장한다 (발표 전에 학교 네트워크에서 한 번)
저장 형식은 수집기 v4의 fixtures 와 같다 (주소의 sha1 앞 16자리 .json). v4가 저장한 파일을 그대로 쓴다.
"""

import hashlib
import json
import time
from datetime import datetime
from urllib.parse import urlparse

import requests

from ... import config
from . import board_html


class WebError(Exception):
    """응답 없음(접속 실패, 시간 초과, 5xx 등) 또는 재생할 응답 없음."""


_last_request = {}


def _is_local(url):
    return urlparse(url).netloc.split(":")[0] in ("127.0.0.1", "localhost")


def _polite_wait(url):
    """같은 호스트에 1초에 1번 이하로 요청한다 (학교 서버 부하 최소화)."""
    host = urlparse(url).netloc
    gap = time.time() - _last_request.get(host, 0)
    if gap < 1.0:
        time.sleep(1.0 - gap)
    _last_request[host] = time.time()


# ---------------------------------------------------------------- 저장된 응답
def _record_path(url):
    return config.WEB_RECORD_DIR / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}.json"


def has_saved(url):
    return _record_path(url).exists()


def record_info():
    meta = config.WEB_RECORD_DIR / "_meta.json"
    if not meta.exists():
        return {}
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _load(url):
    path = _record_path(url)
    if not path.exists():
        raise WebError("저장된 응답 없음 (재생 범위 밖)")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["status"], data["text"]


def _store(url, status, text):
    config.WEB_RECORD_DIR.mkdir(parents=True, exist_ok=True)
    _record_path(url).write_text(
        json.dumps({"url": url, "status": status, "text": text}, ensure_ascii=False), encoding="utf-8"
    )
    (config.WEB_RECORD_DIR / "_meta.json").write_text(
        json.dumps(
            {
                "origin": "captured",
                "capturedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "note": "실제 학교 서버에서 받은 응답이다 (놓칠뻔 데모 FETCH_MODE=record).",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def replaying(url=None):
    return config.FETCH_MODE == "replay" and (url is None or not _is_local(url))


def _fetch(url):
    """(상태 코드, 본문). 응답이 없으면 WebError."""
    if replaying(url):
        return _load(url)
    else:
        if not _is_local(url):
            _polite_wait(url)
        try:
            r = requests.get(url, timeout=config.HTTP_TIMEOUT, headers={"User-Agent": config.USER_AGENT})
        except requests.RequestException as e:
            raise WebError(f"응답 없음: {e.__class__.__name__}") from e
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        status, text = r.status_code, r.text
        if config.FETCH_MODE == "record" and not _is_local(url):
            _store(url, status, text)
        return status, text


def _get(url):
    status, text = _fetch(url)
    if status >= 400:
        raise WebError(f"HTTP {status}")
    return text


def list_url(source):
    if source.get("list_url"):
        return source["list_url"]
    return f"{source['site_url']}/na/ntt/selectNttList.do?mi={source['mi']}&bbsId={source['bbs_id']}"


def rss_url(source):
    return f"{source['site_url']}/na/ntt/selectRssFeed.do?mi={source['mi']}&bbsId={source['bbs_id']}"


def detail_url(source, ntt_sn):
    return f"{source['site_url']}/na/ntt/selectNttInfo.do?nttSn={ntt_sn}"


# ---- 클래스 다이어그램의 연산 ----------------------------------------------
OK, UNREACHABLE, NO_POSTS = "ok", "unreachable", "no_posts"


def check_reachable(url, rss=None):  # 접속을 확인한다(주소) : 접속 가능 여부
    """출처 등록(UC3 대안 1) 때 쓴다. 접속만 보지 않고 게시글 목록이 있는지까지 본다 (해결안 3).
      ok          : RSS 또는 목록 HTML에 게시물 번호가 있음
      unreachable : 목록 주소가 응답하지 않음 (예외 1)
      no_posts    : HTTP 200인데 게시물 번호가 없음 ('시스템안내' 화면 등, 예외 3)
    rss 주소가 있으면 먼저 보고(UC4 정상 2와 같은 순서), 안 되면 목록 HTML을 본다."""
    if rss:
        try:
            if board_html.extract_numbers_from_rss(_get(rss)):
                return OK
        except WebError:
            pass
    try:
        html = _get(url)
    except WebError:
        return UNREACHABLE
    return OK if board_html.extract_numbers_from_list(html) else NO_POSTS


ROBOTS_CACHE_SEC = 3600
_robots_cache = {}


def read_robots(url):  # robots.txt를 읽는다(주소) : 규칙
    """(상태 코드, 본문). 응답이 없으면 (None, ""). 해석·판정은 수집 허용 규칙이 한다.
    같은 사이트는 1시간 동안 다시 요청하지 않는다 (응답이 없었던 경우는 기억하지 않음)."""
    p = urlparse(url)
    origin = f"{p.scheme}://{p.netloc}"
    hit = _robots_cache.get(origin)
    if hit and time.time() - hit[0] < ROBOTS_CACHE_SEC:
        return hit[1]
    try:
        res = _fetch(f"{origin}/robots.txt")
    except WebError:
        return None, ""
    if res[0] < 500:
        _robots_cache[origin] = (time.time(), res)
    return res


def clear_robots_cache():
    _robots_cache.clear()


def request_rss(source):  # RSS 피드를 요청한다(출처) : 응답
    return _get(rss_url(source))


def request_list(source):  # 목록 페이지를 요청한다(출처) : 응답
    return _get(list_url(source))


def request_detail(source, ntt_sn):  # 상세 페이지를 요청한다(번호) : 상세 HTML
    return _get(detail_url(source, ntt_sn))
