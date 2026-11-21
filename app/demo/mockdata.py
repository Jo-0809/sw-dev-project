"""시연용 모의 게시판 데이터.

학교 사이트에 접속하지 않아도 수집·추출·판정 흐름 전체를 보여 줄 수 있도록, 경상국립대 게시판과
같은 주소 구조(/na/ntt/selectNttList.do, selectRssFeed.do, selectNttInfo.do)를 흉내 낸다.
날짜는 '{D+3}'처럼 오늘 기준 상대값으로 적어 두고, 화면에 낼 때 실제 날짜로 바꾼다.
공지 내용은 시연용으로 만든 예시이며 실제 공고가 아니다.
"""
import json
import re
from datetime import timedelta

from .. import config

WEEK = "월화수목금토일"
_PH = re.compile(r"\{D([+-]\d+)(\|iso)?\}")


def render(text, base=None):
    base = base or config.today()

    def rep(m):
        d = base + timedelta(days=int(m.group(1)))
        if m.group(2):
            return d.isoformat()
        return f"{d.year}. {d.month}. {d.day}.({WEEK[d.weekday()]})"
    return _PH.sub(rep, text)


# 모의 게시판 (사이트 경로, mi, bbsId, RSS 제공 여부)
BOARDS = {
    "scholar": {"site": "main", "mi": "1376", "bbs": "1075", "rss": True, "name": "대학 공지 – 장학·학생지원"},
    "external": {"site": "main", "mi": "1132", "bbs": "1033", "rss": True, "name": "대학 공지 – 외부기관"},
    "sw": {"site": "sw", "mi": "2001", "bbs": "3001", "rss": False, "name": "소프트웨어공학과 공지"},
    "edu": {"site": "edu", "mi": "9001", "bbs": "9999", "rss": True, "name": "교육과정 (robots.txt 수집 금지)"},
}

POSTS = [
    {"ntt": "8800101", "board": "scholar", "dept": "SW중심대학사업단", "posted": -6, "published": True,
     "title": "2026 GNU SW 해커톤 참가자 모집",
     "attachments": ["2026_SW해커톤_참가신청서.hwp"],
     "body": """경상국립대학교 SW중심대학사업단에서 '2026 GNU SW 해커톤' 참가자를 모집합니다.
1. 행사 개요
- 일시: {D+10} 09:00 ~ 다음 날 18:00 (무박 2일)
- 장소: 가좌캠퍼스 공학관
2. 참가 대상
- 본교 학부 재학생 1~3학년 (전공 무관)
- 2~4인 팀 구성 (개인 신청 시 팀 매칭)
3. 신청 기간: {D-6} ~ {D+2} 23:59까지
4. 신청 방법: 첨부한 신청서를 작성하여 이메일 제출
5. 시상: 대상 1팀(상금 200만 원) 외
※ 자세한 내용은 첨부파일을 참고하시기 바랍니다."""},
    {"ntt": "8800102", "board": "scholar", "dept": "국제교류본부", "posted": -5, "published": True,
     "title": "2026 동계 해외 단기연수 프로그램 참가자 모집",
     "attachments": ["해외단기연수_지원서.hwp"],
     "body": """국제교류본부에서 2026 동계 해외 단기연수 참가자를 모집합니다.
□ 연수 기간: 2027. 1. 4.(월) ~ 1. 22.(금), 3주
□ 연수 기관: 미국 ○○대학교 어학원
□ 지원 자격
- 본교 재학생으로 2학년 이상인 자
- 휴학생은 지원할 수 없음
□ 지원 서류: 지원서 1부, 성적증명서 1부
□ 접수 마감: {D+4} 18:00까지 국제교류본부 방문 제출
□ 지원 내용: 항공료 및 수업료 일부 지원"""},
    {"ntt": "8800103", "board": "external", "dept": "현장실습지원센터", "posted": -4, "published": True,
     "title": "2026 동계 산학협력 현장실습(인턴십) 참여 학생 모집",
     "attachments": ["참여기업_목록.pdf"],
     "body": """동계 방학 산학협력 현장실습(인턴십) 참여 학생을 모집합니다.
□ 모집 대상: 공과대학 소속 4학년 재학생
□ 실습 기간: 2027. 1. 2. ~ 2. 27. (8주)
□ 참여 기업: 첨부 목록 참고
□ 신청 기한: {D+3} 17:00
□ 신청 방법: 현장실습지원센터 누리집 온라인 신청"""},
    {"ntt": "8800104", "board": "external", "dept": "대외협력과", "posted": -3, "published": True,
     "title": "대학 홍보 서포터즈 '경상누리' 7기 모집",
     "attachments": ["경상누리7기_모집요강.pdf", "지원서.hwp"],
     "body": """대학 홍보 서포터즈 '경상누리' 7기를 모집합니다.
- 활동 기간: 2027년 3월 ~ 12월
- 활동 내용: 대학 SNS 콘텐츠 제작, 행사 취재
- 지원 자격 및 우대 사항: 첨부한 모집 요강을 확인하세요.
- 서류 마감: {D+5} 17:00
- 문의: 대외협력과"""},
    {"ntt": "8800105", "board": "scholar", "dept": "국제교류본부", "posted": -2, "published": True,
     "title": "2027학년도 1학기 교환학생 선발 공고",
     "attachments": ["교환학생_지원서.hwp", "파견대학_목록.xlsx"],
     "body": """2027학년도 1학기 교환학생을 다음과 같이 선발합니다.
1. 지원 자격
가. 본교 재학생 (휴학생 포함, 단 파견 학기에 복학 가능한 자)
나. 2학년 이상 (지원 시점 기준)
다. 전 학과 지원 가능
2. 모집 인원: 30명 내외
3. 접수 기간: {D-2} ~ {D+9} 16:00
4. 제출 서류: 지원서, 수학계획서, 어학 성적표(해당자)"""},
    {"ntt": "8800106", "board": "external", "dept": "교수학습지원센터", "posted": -2, "published": True,
     "title": "2027학년도 1학기 학습 튜터링 튜터 모집",
     "attachments": [],
     "body": """학습 튜터링 프로그램의 튜터를 모집합니다.
□ 지원 자격
- 본교 2~4학년 재학생
- 직전 학기 평점 평균 3.5 이상인 자
□ 활동 기간: 2027. 3. ~ 6. (15주)
□ 활동비: 시간당 15,000원
□ 신청 마감: {D+7} 23:59
□ 신청 방법: 교수학습지원센터 누리집"""},
    {"ntt": "8800107", "board": "scholar", "dept": "학생지원과", "posted": -1, "published": True,
     "title": "2026학년도 2학기 국가근로장학생 선발 명단 안내",
     "attachments": ["선발명단.pdf"],
     "body": """2026학년도 2학기 국가근로장학생 선발 결과를 다음과 같이 안내합니다.
- 선발 명단: 첨부파일 참고 (학번 일부 비공개)
- 근무 시작일: {D+1}
- 근로지 배정 문의: 학생지원과"""},
    {"ntt": "8800110", "board": "external", "dept": "-", "posted": -1, "published": True, "broken": True,
     "title": "(게시판 오류로 열리지 않는 글)", "attachments": [], "body": ""},
    # ---- '새 공지 게시' 버튼으로 시연 중에 올리는 글
    {"ntt": "8800108", "board": "scholar", "dept": "SW중심대학사업단", "posted": 0, "published": False,
     "title": "SW중심대학 생성형 AI 프로젝트 공모전 참가 안내",
     "attachments": ["공모전_요강.pdf"],
     "body": """SW중심대학사업단에서 생성형 AI 프로젝트 공모전을 엽니다.
□ 참가 대상: 경상국립대학교 학부 재학생 누구나 (전공·학년 무관)
□ 공모 주제: 생성형 AI를 활용한 캠퍼스 문제 해결
□ 접수 기간: {D+0} ~ {D+6} 18:00
□ 시상: 최우수상 100만 원 외"""},
    {"ntt": "8800109", "board": "external", "dept": "학생지원과", "posted": 0, "published": False,
     "title": "○○장학재단 2027년도 장학생 모집",
     "attachments": ["장학생_모집요강.hwp"],
     "body": """○○장학재단에서 2027년도 장학생을 모집합니다.
1. 지원 자격
- 국내 4년제 대학 재학생
- 학자금 지원 구간 8구간 이하
- 직전 학기 12학점 이상 이수, 평점 3.0 이상
2. 장학 금액: 학기당 등록금 전액
3. 접수 마감: {D+8}
4. 제출: 학생지원과 방문"""},
    # ---- 소프트웨어공학과 게시판 (RSS 없음 → 목록 HTML 폴백)
    {"ntt": "8800201", "board": "sw", "dept": "소프트웨어공학과", "posted": -3, "published": True,
     "title": "소프트웨어공학과 캡스톤디자인 경진대회 참가팀 모집",
     "attachments": ["참가신청서.hwp"],
     "body": """□ 참가 대상: 소프트웨어공학과 3~4학년 재학생
□ 팀 구성: 3~5인
□ 신청 마감: {D+5} 18:00
□ 제출물: 참가 신청서, 프로젝트 요약서"""},
    {"ntt": "8800202", "board": "sw", "dept": "소프트웨어공학과", "posted": -1, "published": True,
     "title": "소프트웨어공학과 전공 멘토링 멘티 모집",
     "attachments": [],
     "body": """선배 멘토와 함께하는 전공 멘토링 멘티를 모집합니다.
□ 대상: 소프트웨어공학과 1~2학년 재학생
□ 내용: 선배 멘토와 주 1회 전공 학습
□ 신청: {D+1} 18:00까지 학과 사무실 방문 신청"""},
    {"ntt": "8800301", "board": "edu", "dept": "교무과", "posted": -1, "published": True,
     "title": "2027학년도 교육과정 안내", "attachments": [], "body": "교육과정 안내 (수집 금지 게시판 예시)"},
]


def _state_path():
    return config.DB_PATH.parent / "mock_state.json"


def published():
    p = _state_path()
    if p.exists():
        return set(json.loads(p.read_text(encoding="utf-8")))
    return {x["ntt"] for x in POSTS if x["published"]}


def publish(ntt):
    s = published()
    s.add(ntt)
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(sorted(s)), encoding="utf-8")


def reset():
    if _state_path().exists():
        _state_path().unlink()


def board_key(site, mi, bbs):
    for k, b in BOARDS.items():
        if b["site"] == site and b["mi"] == mi and b["bbs"] == bbs:
            return k
    return None


def posts_of(board):
    pub = published()
    rows = [p for p in POSTS if p["board"] == board and p["ntt"] in pub]
    return sorted(rows, key=lambda p: p["ntt"], reverse=True)


def post(ntt):
    for p in POSTS:
        if p["ntt"] == ntt and p["ntt"] in published():
            return p
    return None
