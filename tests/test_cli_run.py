"""`videoforge run` reads plan.json and runs each plan through the executor."""

from __future__ import annotations

from pathlib import Path

from conftest import audio, plan_for, source

from videoforge import cli
from videoforge.core.job import JobResult, JobStatus
from videoforge.core.models import AudioCodec as C
from videoforge.core.models import Issue, Severity
from videoforge.core.plan_io import dump_plans


def plans():
    ok = plan_for(source([audio(C.AC3, "5.1")], name="A.mkv"), source(name="A_job.h264"))
    blocked = plan_for(source([audio(C.AC3, "5.1")], name="B.mkv"), None)
    return [ok, blocked]


def test_run_reads_plan_json_and_reports(tmp_path, monkeypatch):
    path = tmp_path / "plan.json"
    dump_plans(plans(), path)
    seen = []

    def fake_run_plan(plan, out_dir, *_args, **kwargs):
        seen.append((plan.source.name, out_dir))
        if plan.blocked:
            return JobResult(plan, JobStatus.SKIPPED, error="blocked")
        return JobResult(plan, JobStatus.DONE, out_dir / "A.mkv", [Issue(Severity.WARN, "audio.ac3", "AC-3")])

    monkeypatch.setattr("videoforge.core.pipeline.run.run_plan", fake_run_plan)
    code = cli.main(["run", str(path), "--out-dir", str(tmp_path / "out")])
    assert seen == [("A.mkv", tmp_path / "out"), ("B.mkv", tmp_path / "out")]
    assert code == 1  # one skipped


def test_run_only_filter(tmp_path, monkeypatch):
    path = tmp_path / "plan.json"
    dump_plans(plans(), path)
    seen = []
    monkeypatch.setattr(
        "videoforge.core.pipeline.run.run_plan",
        lambda plan, out_dir, *a, **k: seen.append(plan.source.name) or JobResult(plan, JobStatus.DONE, Path("x")),
    )
    assert cli.main(["run", str(path), "--out-dir", str(tmp_path), "--only", "A."]) == 0
    assert seen == ["A.mkv"]
