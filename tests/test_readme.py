"""Checks that the README matches the published package and the code's behavior."""

import doctest
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from openadapt_telemetry import TelemetryClient

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _visible_readme() -> str:
    """Return the README text with HTML comments removed."""
    return HTML_COMMENT.sub("", _readme())


def _python_block(containing: str) -> str:
    """Return the one README python block that contains the given text."""
    blocks = [b for b in PYTHON_BLOCK.findall(_readme()) if containing in b]
    assert len(blocks) == 1, f"expected one python block containing {containing!r}"
    return blocks[0]


def test_readme_does_not_say_package_is_unpublished():
    """The package is on PyPI, so no note may say it isn't yet."""
    assert "uncomment once package is published" not in _readme()


def test_readme_shows_pypi_badges():
    """The PyPI version and downloads badges render (are not inside a comment)."""
    visible = _visible_readme()
    assert "img.shields.io/pypi/v/openadapt-telemetry" in visible
    assert "img.shields.io/pypi/dm/openadapt-telemetry" in visible


def test_readme_doctest_examples_pass():
    """Every >>> example in the README produces the output it shows."""
    parser = doctest.DocTestParser()
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    examples = [b for b in PYTHON_BLOCK.findall(_readme()) if ">>>" in b]
    assert examples
    for i, block in enumerate(examples):
        test = parser.get_doctest(block, {}, f"README example {i}", str(README), 0)
        runner.run(test)
    assert runner.summarize(verbose=False).failed == 0


def test_quick_start_sends_the_report_the_readme_describes(clean_env, monkeypatch, sentry_events):
    """Run the quick start against an in-memory transport and compare with the README."""
    monkeypatch.setenv("OPENADAPT_TELEMETRY_DSN", "https://public@example.invalid/1")
    TelemetryClient.reset_instance()
    exec(_python_block("telemetry.initialize("), {})

    (event,) = sentry_events("event")
    (exception,) = event["exception"]["values"]
    received = f"{exception['type']}: {exception['value']}"
    claimed = re.search(r"GlitchTip receives\s+`([^`]+)`", _readme()).group(1)
    assert received == claimed
    assert "server_name" not in event
    for frame in exception["stacktrace"]["frames"]:
        assert {"filename", "function", "lineno"} <= set(frame)
        assert not {"vars", "pre_context", "context_line", "post_context"} & set(frame)


def test_quick_start_sends_nothing_without_a_dsn(clean_env, sentry_events):
    """Without a DSN, initialize() returns False and nothing is sent."""
    TelemetryClient.reset_instance()
    namespace: dict = {}
    exec(_python_block("telemetry.initialize("), namespace)
    assert namespace["telemetry"].initialized is False
    assert sentry_events("event") == []


def test_usage_event_example_queues_an_event(monkeypatch):
    """The usage-event example queues one event with the properties shown."""
    for name in ("DO_NOT_TRACK", "CI", "GITHUB_ACTIONS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENADAPT_TELEMETRY_ENABLED", "true")
    queued = []

    class Queue:
        def put_nowait(self, payload):
            queued.append(payload)

    with patch("openadapt_telemetry.posthog._ensure_worker", return_value=Queue()):
        exec(_python_block("capture_usage_event("), {})

    (payload,) = queued
    assert payload["event"] == "demo_recorded"
    assert payload["properties"]["steps"] == 12


def test_decorator_example_runs_before_initialize():
    """The decorator example runs as written and does nothing until initialize()."""
    exec(_python_block("TelemetrySpan("), {})


@pytest.mark.parametrize(
    "term",
    [
        "admission",
        "admitted",
        "signed ledger",
        "evidence authority",
        "product target",
        "lifecycle state",
        "governed",
    ],
)
def test_readme_has_no_governance_language(term):
    """Process and compliance terms belong in docs/COMPLIANCE.md, not the README."""
    assert term not in _readme().lower()


def test_readme_links_compliance_doc_once():
    """The data-handling reference is linked once, and the link target exists."""
    links = re.findall(r"\]\(([^)]*docs/COMPLIANCE\.md)\)", _readme())
    assert len(links) == 1
    assert (ROOT / "docs" / "COMPLIANCE.md").is_file()


def test_compliance_failure_signal_example_queues_one_event(monkeypatch):
    """The failure-signal example in docs/COMPLIANCE.md runs and sends only the closed schema."""
    for name in ("DO_NOT_TRACK", "CI", "GITHUB_ACTIONS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENADAPT_TELEMETRY_ENABLED", "true")
    doc = (ROOT / "docs" / "COMPLIANCE.md").read_text(encoding="utf-8")
    (block,) = PYTHON_BLOCK.findall(doc)
    queued = []

    class Queue:
        def put_nowait(self, payload):
            queued.append(payload)

    with patch("openadapt_telemetry.posthog._ensure_worker", return_value=Queue()):
        exec(block, {})

    (payload,) = queued
    assert payload["event"] == "automation_failure_observed"
    assert payload["distinct_id"].startswith("failure:")
    assert payload["properties"]["occurred_at"].endswith(":00:00Z")
