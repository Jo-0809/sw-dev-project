"""<<control>> 수집 스케줄러 — 수집 주기(기본 30분)마다 수집 제어를 시작한다 (APScheduler, 기술 선정 06-1)."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .. import config
from . import collect_ctl

_scheduler = None


def start():
    global _scheduler
    if _scheduler or not config.SCHEDULER_ENABLED:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    _scheduler.add_job(collect_ctl.start, "interval", minutes=config.COLLECT_INTERVAL_MIN,
                       id="collect", max_instances=1, coalesce=True)
    _scheduler.start()
    logging.getLogger("uvicorn").info("수집 스케줄러 시작: %s분 주기", config.COLLECT_INTERVAL_MIN)


def next_run():
    if not _scheduler:
        return None
    job = _scheduler.get_job("collect")
    return job.next_run_time.strftime("%H:%M") if job and job.next_run_time else None


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
