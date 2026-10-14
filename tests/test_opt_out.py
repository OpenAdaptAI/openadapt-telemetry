"""One opt-out rule covers error reports and usage events."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import openadapt_telemetry.config as config
import openadapt_telemetry.posthog as posthog
from openadapt_telemetry import TelemetryClient, is_telemetry_allowed

TELEMETRY_ENV = (
    "DO_NOT_TRACK",
    "OPENADAPT_TELEMETRY_ENABLED",
    "OPENADAPT_TELEMETRY_IN_CI",
    "CI",
    "CONTINUOUS_INTEGRATION",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "JENKINS_URL",
    "TRAVIS",
    "CIRCLECI",
    "BUILDKITE",
    "AZURE_PIPELINES",
    "TF_BUILD",
    "CODEBUILD_BUILD_ID",
    "TEAMCITY_VERSION",
    "BITBUCKET_BUILD_NUMBER",
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Run from an empty project directory with no telemetry variables set."""
    for name in TELEMETRY_ENV:
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.chdir(root)
    return root


def _write_pyproject(root, telemetry):
    value = "true" if telemetry else "false"
    (root / "pyproject.toml").write_text(f"[tool.openadapt]\ntelemetry = {value}\n")


def _write_config_file(enabled):
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config.CONFIG_FILE.write_text(json.dumps({"enabled": enabled}))


def _paths_enabled() -> tuple[bool, bool]:
    """Return (error reports enabled, usage events enabled)."""
    TelemetryClient.reset_instance()
    return TelemetryClient.get_instance().enabled, posthog._usage_enabled()


def test_enabled_by_default(project):
    assert is_telemetry_allowed() is True
    assert _paths_enabled() == (True, True)


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
def test_do_not_track_turns_off_both_paths(project, monkeypatch, value):
    monkeypatch.setenv("DO_NOT_TRACK", value)
    assert _paths_enabled() == (False, False)


def test_do_not_track_beats_explicit_enable(project, monkeypatch):
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    monkeypatch.setenv("OPENADAPT_TELEMETRY_ENABLED", "true")
    assert _paths_enabled() == (False, False)


def test_pyproject_opt_out_turns_off_both_paths(project):
    _write_pyproject(project, telemetry=False)
    assert _paths_enabled() == (False, False)


def test_pyproject_opt_out_found_from_subdirectory(project, monkeypatch):
    _write_pyproject(project, telemetry=False)
    sub = project / "src" / "pkg"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert _paths_enabled() == (False, False)


def test_pyproject_telemetry_true_keeps_defaults(project):
    _write_pyproject(project, telemetry=True)
    assert _paths_enabled() == (True, True)


def test_explicit_env_enable_overrides_pyproject(project, monkeypatch):
    _write_pyproject(project, telemetry=False)
    monkeypatch.setenv("OPENADAPT_TELEMETRY_ENABLED", "true")
    assert _paths_enabled() == (True, True)


def test_config_file_opt_out_turns_off_both_paths(project):
    _write_config_file(False)
    assert _paths_enabled() == (False, False)


def test_config_file_string_false_is_an_opt_out(project):
    _write_config_file("false")
    assert _paths_enabled() == (False, False)


def test_usage_events_stay_off_in_ci_by_default(project, monkeypatch):
    monkeypatch.setenv("CI", "true")
    assert _paths_enabled() == (True, False)
    monkeypatch.setenv("OPENADAPT_TELEMETRY_IN_CI", "true")
    assert posthog._usage_enabled() is True


def test_empty_explicit_variable_means_unset(project, monkeypatch):
    monkeypatch.setenv("OPENADAPT_TELEMETRY_ENABLED", "")
    assert _paths_enabled() == (True, True)


def test_opted_out_usage_event_is_not_queued(project):
    _write_pyproject(project, telemetry=False)
    with patch("openadapt_telemetry.posthog._ensure_worker") as worker:
        assert posthog.capture_usage_event("agent_run") is False
    worker.assert_not_called()
