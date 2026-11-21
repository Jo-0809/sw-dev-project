"""<<control>> 수집 스케줄러 — 수집 주기(기본 30분)마다 수집 제어를 시작한다 (APScheduler, 기술 선정 06-1).

서버를 켜면 한 번 바로 수집하고, 그 뒤로 주기마다 수집한다. 바로 수집하지 않으면 운영 모드('지금 수집' 없음)에서
첫 수집이 30분 뒤가 되고, 30분 안에 서버를 다시 켜면 수집이 계속 미뤄진다.
상태(스케줄러 객체)를 들고 있어서 클래스로 둔다. 모듈 안의 scheduler 하나를 앱이 시작·종료한다.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from ... import config
from .collect_ctl import collector

INTERVAL_MIN = config.COLLECT_INTERVAL_MIN  # -수집 주기 (분)
TIMEZONE = ZoneInfo("Asia/Seoul")
JOB_ID = "collect"


class CollectScheduler:
    def __init__(self):
        self._scheduler = None

    def start(self):  # 설계 외: 앱 시작 때 스케줄러를 켠다
        if self._scheduler or not config.SCHEDULER_ENABLED:
            return
        self._scheduler = BackgroundScheduler(timezone=TIMEZONE)
        self._scheduler.add_job(
            collector.start,  # 수집을 시작한다()
            "interval",
            minutes=INTERVAL_MIN,
            id=JOB_ID,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(TIMEZONE),  # 서버를 켜면 한 번 바로 수집
        )
        self._scheduler.start()
        logging.getLogger("uvicorn").info("수집 스케줄러 시작: 지금 한 번, 이후 %s분 주기", INTERVAL_MIN)

    def next_run(self):  # 설계 외: 시연 패널의 '다음 자동 수집' 표시
        if not self._scheduler:
            return None
        job = self._scheduler.get_job(JOB_ID)
        return job.next_run_time.strftime("%H:%M") if job and job.next_run_time else None

    def stop(self):  # 설계 외: 앱 종료 때 끈다
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None


scheduler = CollectScheduler()
