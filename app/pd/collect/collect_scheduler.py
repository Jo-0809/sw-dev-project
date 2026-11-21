"""<<control>> 수집 스케줄러 — 수집 주기(기본 30분)마다 수집 제어를 시작한다 (APScheduler, 기술 선정 06-1).

상태(스케줄러 객체)를 들고 있어서 클래스로 둔다. 모듈 안의 scheduler 하나를 앱이 시작·종료한다.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from ... import config
from .collect_ctl import collector


class CollectScheduler:
    INTERVAL_MIN = config.COLLECT_INTERVAL_MIN  # 수집 주기 (분)
    JOB_ID = "collect"

    def __init__(self):
        self._scheduler = None

    def start(self):
        if self._scheduler or not config.SCHEDULER_ENABLED:
            return
        self._scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        self._scheduler.add_job(
            collector.start, "interval", minutes=self.INTERVAL_MIN, id=self.JOB_ID, max_instances=1, coalesce=True
        )
        self._scheduler.start()
        logging.getLogger("uvicorn").info("수집 스케줄러 시작: %s분 주기", self.INTERVAL_MIN)

    def next_run(self):
        if not self._scheduler:
            return None
        job = self._scheduler.get_job(self.JOB_ID)
        return job.next_run_time.strftime("%H:%M") if job and job.next_run_time else None

    def stop(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None


scheduler = CollectScheduler()
