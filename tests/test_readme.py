"""Checks that the README matches the published state of the package."""

import re
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _visible_readme() -> str:
    """Return the README text with HTML comments removed."""
    return HTML_COMMENT.sub("", README.read_text(encoding="utf-8"))


def test_readme_does_not_say_package_is_unpublished():
    """The package is on PyPI, so no note may say it isn't yet."""
    assert "uncomment once package is published" not in README.read_text(encoding="utf-8")


def test_readme_shows_pypi_badges():
    """The PyPI version and downloads badges render (are not inside a comment)."""
    visible = _visible_readme()
    assert "img.shields.io/pypi/v/openadapt-telemetry" in visible
    assert "img.shields.io/pypi/dm/openadapt-telemetry" in visible
