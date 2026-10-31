"""Data saved while rule sets were called profiles (before 0.1.0-beta.11) loads with its rule set."""

from __future__ import annotations

from pathlib import Path

from conftest import plan_for, source

from videoforge.core.config import AppConfig, load_app_config
from videoforge.core.job import JobInputs, JobSpec
from videoforge.core.models import Plan
from videoforge.core.plan_io import from_json, to_json
from videoforge.server.settings import SavedSettings
from videoforge.server.store import Store

ROOT = Path(__file__).resolve().parents[1]


def _as_profile(data: dict) -> dict:
    return {("profile" if k == "rule_set" else k): v for k, v in data.items()}


def test_a_saved_job_and_plan_keep_their_rule_set(tmp_path):
    spec = JobSpec(inputs=JobInputs(tmp_path / "a.mkv"), rule_set="mygroup")
    assert from_json(JobSpec, _as_profile(to_json(spec))) == spec
    plan = plan_for(source())
    plan.rule_set = "mygroup"
    assert from_json(Plan, _as_profile(to_json(plan))).rule_set == "mygroup"


def test_saved_settings_and_videoforge_toml_keep_the_default_rule_set(tmp_path):
    app = load_app_config()
    assert from_json(AppConfig, _as_profile(to_json(app) | {"rule_set": "mygroup"})).rule_set == "mygroup"
    config = tmp_path / "videoforge.toml"
    toml = (ROOT / "videoforge.toml").read_text(encoding="utf-8")
    config.write_text(toml.replace('rule_set = "manual"', 'profile = "mygroup"'), encoding="utf-8")
    assert load_app_config(config).rule_set == "mygroup"
    db = tmp_path / "videoforge.db"
    Store(db).set_setting("profile", "mygroup")
    assert SavedSettings.load(Store(db)).rule_set == "mygroup"
