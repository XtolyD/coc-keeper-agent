# -*- coding: utf-8 -*-
import time

from coc_keeper.web_jobs import JobManager


def _wait(jobs, job_id):
    for _ in range(200):
        payload = jobs.get(job_id)
        if payload["status"] != "running":
            return payload
        time.sleep(0.01)
    return payload


def test_job_manager_reports_success_and_stage():
    jobs = JobManager(max_workers=1)
    job_id = jobs.submit("test", lambda report: (report("中间"), {"ok": True})[1])
    payload = _wait(jobs, job_id)
    assert payload["status"] == "completed"
    assert payload["stage"] == "完成"
    assert payload["result"] == {"ok": True}


def test_job_manager_reports_failure_without_raising():
    jobs = JobManager(max_workers=1)

    def fail(_report):
        raise RuntimeError("boom")

    payload = _wait(jobs, jobs.submit("test", fail))
    assert payload["status"] == "failed"
    assert "boom" in payload["error"]
