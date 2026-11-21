"""<<control>> 수집 허용 규칙 — robots.txt 규칙으로 주소의 수집 허용 여부를 판정한다.

쓰는 곳
  - 출처 등록 (UC3 예외 2, 제약사항 03-2 'robots.txt 금지 게시판은 출처로 등록하지 못하게')
  - 수집할 때 RSS·목록·상세 요청 앞 (요청마다, 처음부터 넣어 둔 출처도 포함)

robots.txt 를 읽은 결과 (RFC 9309 2.3.1 기준)
  200          : 규칙대로 판정
  4xx (없음)   : 금지 규칙이 없다 → 허용
  5xx·응답 없음 : 규칙을 알 수 없다 → 허용하지 않음 (등록 보류, 이번 수집 건너뜀)
  * 수집기 v4는 4xx도 '읽지 못함'으로 보고 등록을 보류했다. 여기서는 RFC를 따라 4xx는 허용한다.
robots.txt 는 부르는 쪽(출처 등록 제어·수집 제어)이 홈페이지 연결로 읽어 넘긴다.
클래스 다이어그램처럼 이 클래스는 홈페이지 연결에 의존하지 않는다. 같은 사이트는 홈페이지 연결이 1시간 기억한다.
"""
from urllib.robotparser import RobotFileParser

from .. import config

ALLOWED, BLOCKED, UNKNOWN = "허용", "금지", "확인 불가"


def judge(rules_text, url):                  # 판정한다(규칙, 주소) : 허용 여부
    rp = RobotFileParser()
    rp.parse((rules_text or "").splitlines())
    return rp.can_fetch(config.USER_AGENT, url)


def decide(robots, url):                     # 판정한다(규칙, 주소) : 허용 / 금지 / 확인 불가
    """robots = 홈페이지 연결이 읽어 온 (상태 코드, 본문). 이 클래스는 요청하지 않고 판정만 한다."""
    status, text = robots
    if status is None or status >= 500:
        return UNKNOWN
    if status >= 400:
        return ALLOWED
    return ALLOWED if judge(text, url) else BLOCKED
