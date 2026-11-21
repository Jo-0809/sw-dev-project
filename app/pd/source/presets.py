"""처음부터 넣어 두는 실제 경상국립대 게시판 (설계 외 보조 모듈).

수집기 v4(sources.json)와 같은 값이고, 2026-10-11에 저장한 실제 응답이 recordings/web/ 에 있다.
(이름, 사이트, mi, bbsId, RSS 사용)  산업시스템공학부는 목록 HTML 경로를 보이려고 v4처럼 RSS를 끔.
"""

from . import source

REAL_SOURCES = [
    ("경상국립대 대학 공지 – 장학", "https://www.gnu.ac.kr/main", "1376", "1075", 1),
    ("경상국립대 대학 공지 – 학사", "https://www.gnu.ac.kr/main", "1127", "1029", 1),
    ("경상국립대 대학 공지 – 외부기관", "https://www.gnu.ac.kr/main", "1132", "1033", 1),
    ("경상국립대 산업시스템공학부 – 장학정보", "https://www.gnu.ac.kr/ise", "3003", "1374", 0),
]


def seed():
    for name, site, mi, bbs, rss in REAL_SOURCES:
        source.seed("preset", name, site, mi, bbs, rss)
