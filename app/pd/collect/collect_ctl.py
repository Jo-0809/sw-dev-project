"""<<control>> 수집 제어 — 등록된 출처마다 새 공지를 찾아 저장하고 조건 추출을 맡긴다 (UC4).
흐름 번호는 LMS 최종본 놓칠뻔_중간발표자료_FINAL.pdf (2026-10-11 23:27) 04-2·09-1 명세서 기준.

정상   1 수집 시작 → 2 RSS 요청 → 3 응답 → 4 신규 선별 후 상세 요청 → 5~7 조건 추출 제어에 넘김
대안 1 RSS가 없으면 목록 HTML을 해석 (RSS 요청이 실패하거나 번호가 없을 때도 같은 길로 간다)
대안 2 신규 공지가 없으면 이 출처의 수집을 종료한다 (_end_source)
예외 1 응답 없음 → 수집 실패 기록 후 다음 출처
예외 3 HTTP 200인데 게시글 영역 없음('시스템안내') → 수집 실패 기록 (목록 단계면 그 출처, 상세 단계면 그 공지)
품질 시나리오 #2 '출처 간 연쇄 중단 0건': 한 출처·한 공지에서 어떤 오류가 나도 기록하고 다음으로 넘어간다.
제약사항 03-2 robots.txt: 요청마다 수집 허용 규칙에 묻고, 금지·확인 불가면 요청하지 않는다.
본문이 이미지뿐인 공지: 글자를 얻을 수 없어(이미지 다운로드 금지) '확인 필요'로 저장한다.

동시에 두 번 돌지 않게 잠금과 마지막 결과(상태)를 들고 있어서 클래스로 둔다. 모듈 안의 collector 하나를 쓴다.
"""

import os
import threading

from ... import config
from ..external import web
from ..notice import notice
from ..source import robots, subscription
from . import extract_ctl, failure, parser

# 처음 등록한 출처에서 한 번에 가져오는 최대 건수 (RSS는 최근 100건을 주므로, 학교 서버 부하를 줄인다)
MAX_NEW_PER_SOURCE = int(os.environ.get("COLLECT_MAX_NEW", "10"))


class SourceSkippedError(Exception):
    """robots.txt 금지·확인 불가로 요청하지 않음."""


class PostAreaMissingError(Exception):
    """HTTP 200인데 게시글 영역이 없음 (예외 3)."""


def _allow(url):
    state = robots.decide(web.read_robots(url), url)  # robots.txt를 읽는다 → 판정한다(규칙, 주소)
    if state == robots.BLOCKED:
        raise SourceSkippedError("robots.txt 금지 경로라 요청하지 않음")
    if state == robots.UNKNOWN:
        raise SourceSkippedError("robots.txt를 확인하지 못해 이번 주기에는 요청하지 않음")


def _numbers(src):
    if src.get("rss") and src.get("mi") and src.get("bbs_id"):
        try:
            _allow(web.rss_url(src))
            nums = parser.extract_numbers_from_rss(web.request_rss(src))
            if nums:
                return nums, "RSS"
        except (web.WebError, SourceSkippedError):
            pass  # RSS가 안 되면 목록 HTML로 (대안 1)
    _allow(web.list_url(src))
    html = web.request_list(src)  # 여기서 WebError면 예외 1
    nums = parser.extract_numbers_from_list(html)
    if not nums and parser.is_error_page(html):  # 예외 3 (목록 단계): 잘못된 게시판은 HTTP 200 + '시스템안내'
        raise PostAreaMissingError("HTTP 200이지만 번호 없음 ('시스템안내' 화면 · 게시판 주소 확인 필요)")
    return nums, "목록 HTML"


def _new_only(numbers, saved):  # 신규만 선별한다(번호 목록, 저장된 번호) : 신규 번호
    new = [n for n in numbers if n not in saved]
    if not saved:
        new = new[:MAX_NEW_PER_SOURCE]
    return new


def _empty_result(src, replay=False, error=None):
    return {
        "source": src["name"],
        "new": 0,
        "failed": 0,
        "review": 0,
        "out_of_range": 0,
        "path": None,
        "error": error,
        "replay": replay,
        "ended": None,
    }


class CollectCtl:
    def __init__(self):
        self._lock = threading.Lock()
        self.last_run = {"at": None, "result": None}

    def is_running(self):  # 설계 외: 시연 패널의 '수집 중' 표시
        return self._lock.locked()

    def reset_last_run(self):  # 설계 외: 시연 초기화
        self.last_run.update(at=None, result=None)

    def _end_source(self, result, why):  # 이 출처의 수집을 종료한다() (대안 2)
        result["ended"] = why
        return result

    def collect_source(self, src):  # 설계 외: 출처 1곳 처리 (출처마다 try 로 감싸려고 나눔)
        result = _empty_result(src, replay=web.replaying(web.list_url(src)))
        try:
            numbers, path = _numbers(src)
            result["path"] = path
        except (web.WebError, PostAreaMissingError) as e:  # 예외 1 (응답 없음) / 예외 3 (목록 단계)
            failure.record(src["id"], str(e), stage="번호 확보")
            result["error"] = str(e)
            return result
        except SourceSkippedError as e:  # robots.txt (제약사항 03-2)
            failure.record(src["id"], str(e), stage="robots.txt")
            result["error"] = str(e)
            return result
        if result["replay"]:
            # 저장해 둔 응답만 재생할 수 있다. 저장 범위 밖의 번호는 요청하지 않는다 (실패로 세지 않음)
            saved = [n for n in numbers if web.has_saved(web.detail_url(src, n))]
            result["out_of_range"] = len(numbers) - len(saved)
            numbers = saved
        new = _new_only(numbers, notice.saved_numbers(src["id"]))
        if not new:
            return self._end_source(result, "새 공지 없음")
        for ntt in new:
            self._collect_one(src, ntt, result)
        return result

    def _collect_one(self, src, ntt, result):
        try:
            _allow(web.detail_url(src, ntt))
            html = web.request_detail(src, ntt)
        except (web.WebError, SourceSkippedError) as e:
            failure.record(src["id"], str(e), ntt_sn=ntt, stage="상세")
            result["failed"] += 1
            return
        if not parser.check_post_area(html):  # 예외 3 (상세 단계)
            failure.record(src["id"], "HTTP 200이지만 게시글 영역 없음 ('시스템안내' 화면)", ntt_sn=ntt, stage="상세")
            result["failed"] += 1
            return
        parsed = parser.parse_detail(html, web.detail_url(src, ntt), ntt)
        if parsed is None:
            failure.record(src["id"], "본문을 뽑지 못함", ntt_sn=ntt, stage="본문 해석")
            result["failed"] += 1
            return
        nid = notice.insert(src["id"], parsed)
        if not nid:
            return
        result["new"] += 1
        if parsed["needs_review"]:
            # 포스터 이미지 한 장뿐인 공지. 공지는 가져왔으므로 수집 실패가 아니라 확인 필요
            notice.save_result(nid, notice.CHECK, method="수집 단계 (추출 안 함)", note=parsed["review_reason"])
            result["review"] += 1
            return
        try:
            extract_ctl.extract(nid)  # 추출한다(공지)
        except Exception as e:  # 한 공지의 오류가 다음 공지를 막지 않게
            notice.save_result(
                nid, notice.CHECK, method="추출 중 오류", note=f"조건 추출 중 오류 ({e.__class__.__name__}) — 원문 확인"
            )
            failure.record(src["id"], f"추출 오류 {e.__class__.__name__}: {e}", ntt_sn=ntt, stage="추출")
            result["extract_error"] = result.get("extract_error", 0) + 1

    def start(self):  # 수집을 시작한다()
        if not self._lock.acquire(blocking=False):
            return {"busy": True}
        try:
            results = []
            for s in subscription.registered_sources():  # 시연 모드가 아니면 모의·실패 확인 출처는 빠져 있음
                try:
                    results.append(self.collect_source(s))
                except Exception as e:  # 품질 시나리오 #2: 다른 출처 수집은 계속
                    msg = f"예상하지 못한 오류 {e.__class__.__name__}: {e}"
                    failure.record(s["id"], msg, stage="출처")
                    results.append(_empty_result(s, error=msg))
            self.last_run["at"] = config.now().strftime("%Y-%m-%d %H:%M:%S")
            self.last_run["result"] = results
            return {"busy": False, "results": results}
        finally:
            self._lock.release()


collector = CollectCtl()
