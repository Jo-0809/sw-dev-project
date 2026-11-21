"""모의 게시판 서버 — 경상국립대 게시판과 같은 주소 구조로 응답한다 (시연·테스트용).

/mock/{사이트}/na/ntt/selectNttList.do?mi=&bbsId=   목록 (제목 링크가 javascript 함수 호출)
/mock/{사이트}/na/ntt/selectRssFeed.do?mi=&bbsId=   RSS (RSS 없는 게시판은 404)
/mock/{사이트}/na/ntt/selectNttInfo.do?nttSn=       상세 (없는 글·오류 글은 HTTP 200 '시스템안내')
/robots.txt                                          /mock/common/, /mock/edu/ 금지
/mock/admin                                          시연 중 '새 공지 게시' 버튼
"""

from datetime import timedelta
from html import escape

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from .. import config
from . import mockdata

router = APIRouter()

ROBOTS = """User-agent: *
Disallow: /mock/common/
Disallow: /mock/edu/
"""

PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:sans-serif;max-width:900px;margin:20px auto;color:#222}}
.gnb{{background:#1f3c88;color:#fff;padding:10px}} .gnb a{{color:#fff;margin-right:12px}}
table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid #ddd;padding:8px}}
.mock-note{{background:#fff3cd;padding:6px 10px;font-size:13px}}</style></head><body>
<div class="mock-note">시연용 모의 게시판입니다 (실제 경상국립대 홈페이지가 아님).</div>
<div class="gnb"><a href="javascript:fn_goMenu('10200','1');">대학소개</a><a href="#">입학</a><a href="#">학사</a><a href="#">대학생활</a><a href="#">알림마당</a></div>
{content}</body></html>"""


def _date(offset):
    return (config.today() + timedelta(days=offset)).isoformat()


def _board_or_404(site, mi, bbs):
    return mockdata.board_key(site, mi, bbs)


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return ROBOTS


@router.get("/mock/{site}/na/ntt/selectNttList.do", response_class=HTMLResponse)
def ntt_list(site: str, mi: str = "", bbsId: str = ""):
    key = _board_or_404(site, mi, bbsId)
    if key is None:
        return HTMLResponse(
            PAGE.format(title="시스템안내", content="<h2>시스템안내</h2><p>요청하신 정보가 없습니다.</p>")
        )
    b = mockdata.BOARDS[key]
    # 실제 학교 목록과 같은 모양: 제목 링크는 javascript 호출, 번호는 data-id 속성 (v4에서 확인한 학과 게시판 형식)
    rows = "".join(
        f"<tr><td class='BD_tm_none'>{p['ntt'][-3:]}</td><td class='ta_l'>"
        f'<a href="javascript:" data-id="{p["ntt"]}" class="nttInfoBtn">{escape(p["title"])}</a></td>'
        f"<td>{escape(p['dept'])}</td><td>{_date(p['posted']).replace('-', '.')}</td></tr>"
        for p in mockdata.posts_of(key)
    )
    rss = f"<a class='rss' href='selectRssFeed.do?mi={mi}&bbsId={bbsId}'>RSS</a>" if b["rss"] else ""
    content = (
        f"<h2>{escape(b['name'])}</h2>{rss}<div class='BD_list'><table><thead><tr><th>번호</th><th>제목</th>"
        f"<th>작성자</th><th>등록일</th></tr></thead><tbody>{rows}</tbody></table></div>"
        '<div class=\'paging\'><a href="javascript:" onclick="goPaging(2)">2</a></div>'
    )
    return HTMLResponse(PAGE.format(title=b["name"], content=content))


@router.get("/mock/{site}/na/ntt/selectRssFeed.do")
def ntt_rss(request: Request, site: str, mi: str = "", bbsId: str = ""):
    key = _board_or_404(site, mi, bbsId)
    if key is None or not mockdata.BOARDS[key]["rss"]:
        return Response(status_code=404)
    b = mockdata.BOARDS[key]
    base = str(request.base_url).rstrip("/")
    items = "".join(
        f"<item><title>{escape(p['title'])}</title>"
        f"<link>{base}/mock/{site}/na/ntt/selectNttInfo.do?mi={mi}&amp;nttSn={p['ntt']}</link>"
        f"<pubDate>{_date(p['posted'])}</pubDate></item>"
        for p in mockdata.posts_of(key)
    )
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{escape(b["name"])}</title>'
        f"{items}</channel></rss>"
    )
    return Response(xml, media_type="application/rss+xml; charset=utf-8")


@router.get("/mock/{site}/na/ntt/selectNttInfo.do", response_class=HTMLResponse)
def ntt_info(site: str, nttSn: str = "", mi: str = ""):
    p = mockdata.post(nttSn)
    if p is None or p.get("broken") or mockdata.BOARDS[p["board"]]["site"] != site:
        return HTMLResponse(
            PAGE.format(title="시스템안내", content="<h2>시스템안내</h2><p>요청하신 정보가 없습니다.</p>")
        )
    # 실제 학교 상세와 같은 모양: .BD_table th.title / th[scope=row] 머리말 / tr.cont td 본문 / 첨부 줄
    body = "".join(
        f"<p>{escape(line) if line.strip() else '&nbsp;'}</p>" for line in mockdata.render(p["body"]).splitlines()
    )
    files = "".join(
        f"<li><a href='/mock/common/nttFileDownload.do?fileKey={p['ntt']}{i}'>{escape(n)} "
        f"<strong> (다운로드 : 0회)</strong></a></li>"
        for i, n in enumerate(p["attachments"])
    )
    content = (
        "<div class='BD_table'><table><tbody>"
        f"<tr><th class='title' colspan='2' scope='col'>{escape(p['title'])}</th></tr>"
        f"<tr><th scope='row'>등록일</th><td>{_date(p['posted']).replace('-', '.')}</td></tr>"
        f"<tr><th scope='row'>부서</th><td>{escape(p['dept'])}</td></tr>"
        f"<tr class='cont'><td colspan='2'>{body}</td></tr>"
        + (f"<tr><th scope='row'>첨부파일</th><td><ul class='file'>{files}</ul></td></tr>" if files else "")
        + "</tbody></table></div>"
    )
    return HTMLResponse(PAGE.format(title=p["title"], content=content))


@router.get("/mock/admin", response_class=HTMLResponse)
def admin():
    pub = mockdata.published()
    rows = ""
    for p in mockdata.POSTS:
        b = mockdata.BOARDS[p["board"]]
        url = f"/mock/{b['site']}/na/ntt/selectNttList.do?mi={b['mi']}&bbsId={b['bbs']}"
        state = (
            "게시됨"
            if p["ntt"] in pub
            else (
                f"<form method='post' action='/mock/admin/publish' style='margin:0'><input type='hidden' name='ntt' "
                f"value='{p['ntt']}'><button>새 공지로 게시</button></form>"
            )
        )
        rows += (
            f"<tr><td>{p['ntt']}</td><td><a href='{url}'>{escape(b['name'])}</a></td>"
            f"<td>{escape(p['title'])}</td><td>{state}</td></tr>"
        )
    content = (
        "<h2>모의 게시판 관리 (시연용)</h2><p>'새 공지로 게시'를 누른 뒤 놓칠뻔에서 '지금 수집'을 누르면 "
        "새 공지 1건만 저장되는지(중복 없음) 확인할 수 있다.</p>"
        f"<table><tr><th>번호</th><th>게시판</th><th>제목</th><th>상태</th></tr>{rows}</table>"
        "<p><a href='/'>← 놓칠뻔으로</a></p>"
    )
    return HTMLResponse(PAGE.format(title="모의 게시판 관리", content=content))


@router.post("/mock/admin/publish")
def admin_publish(ntt: str = Form(...)):
    mockdata.publish(ntt)
    return RedirectResponse("/mock/admin", status_code=303)
