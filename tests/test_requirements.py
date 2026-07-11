"""Tests for requirement parsing and lower-bound rewriting."""

from __future__ import annotations

import pytest
from packaging.version import Version

from dependency_support_policy_action.requirements import (
    RewriteStatus,
    requirement_name,
    rewrite_requirement_lower_bound,
    rewrite_specifier_lower_bound,
)

FLOOR = Version("1.25.0")


def test_requirement_name_canonicalized() -> None:
    assert requirement_name("NumPy[dev]>=1.0") == "numpy"
    assert requirement_name("My_Package.Extra") == "my-package-extra"
    assert requirement_name("=== broken ===") is None


class TestUpdated:
    @pytest.mark.parametrize(
        ("original", "expected"),
        [
            # no existing bound: floor appended
            ("numpy", "numpy>=1.25.0"),
            # existing >= raised in place
            ("numpy>=1.21", "numpy>=1.25.0"),
            # original spacing preserved around the operator
            ("numpy >= 1.21", "numpy >= 1.25.0"),
            # strict lower bound replaced by an inclusive one
            ("numpy>1.21", "numpy>=1.25.0"),
            # other clauses untouched, in original order
            ("numpy>=1.21,<3", "numpy>=1.25.0,<3"),
            ("numpy>=1.21, <3", "numpy>=1.25.0, <3"),
            ("numpy<3,>=1.21", "numpy<3,>=1.25.0"),
            # exclusion not matching the floor is preserved
            ("numpy>=1.21,!=1.24.*", "numpy>=1.25.0,!=1.24.*"),
            # appended bound matches the existing comma style
            ("numpy<3", "numpy<3,>=1.25.0"),
            ("numpy <3, !=2.0.0", "numpy <3, !=2.0.0, >=1.25.0"),
            # extras preserved
            ("numpy[dev]>=1.21", "numpy[dev]>=1.25.0"),
            ("numpy[dev]", "numpy[dev]>=1.25.0"),
            # environment markers preserved verbatim
            (
                'numpy>=1.21; python_version < "3.11"',
                'numpy>=1.25.0; python_version < "3.11"',
            ),
            ('numpy; extra == "fast"', 'numpy>=1.25.0; extra == "fast"'),
            # parenthesized specifiers (PEP 508) preserved
            ("numpy (>=1.21)", "numpy (>=1.25.0)"),
            # the highest of several lower bounds is the one raised
            ("numpy>=1.0,>=1.21", "numpy>=1.0,>=1.25.0"),
        ],
    )
    def test_rewrite(self, original: str, expected: str) -> None:
        result = rewrite_requirement_lower_bound(original, FLOOR)
        assert result.status is RewriteStatus.UPDATED
        assert result.text == expected
        assert result.new_floor == FLOOR

    def test_reports_old_floor(self) -> None:
        result = rewrite_requirement_lower_bound("numpy>=1.21", FLOOR)
        assert result.old_floor == Version("1.21")
        assert result.name == "numpy"

    def test_no_previous_floor_reported_as_none(self) -> None:
        result = rewrite_requirement_lower_bound("numpy", FLOOR)
        assert result.old_floor is None


class TestUnchanged:
    @pytest.mark.parametrize(
        "original",
        [
            "numpy>=1.25.0",  # equal floor
            "numpy>=2.0",  # higher floor is never lowered
            "numpy>2.0",  # strict bound above the floor
            "numpy>=2.0,<3",
        ],
    )
    def test_never_lowered(self, original: str) -> None:
        result = rewrite_requirement_lower_bound(original, FLOOR)
        assert result.status is RewriteStatus.UNCHANGED
        assert result.text == original


class TestSkipped:
    @pytest.mark.parametrize(
        ("original", "reason_fragment"),
        [
            ("numpy==1.24.0", "pinned"),
            ("numpy===1.24.0", "pinned"),
            ("numpy~=1.24", "pinned"),
            ("numpy @ https://example.com/numpy.whl", "direct URL"),
            ("not a requirement !!!", "unparsable requirement"),
            ("numpy>=1.21,<1.24", "conflicts"),  # floor above the upper bound
            ("numpy<1.24", "conflicts"),  # appending the floor would be unsatisfiable
            ("numpy>=1.21,!=1.25.0", "conflicts"),  # floor explicitly excluded
        ],
    )
    def test_skipped(self, original: str, reason_fragment: str) -> None:
        result = rewrite_requirement_lower_bound(original, FLOOR)
        assert result.status is RewriteStatus.SKIPPED
        assert result.text == original
        assert result.reason is not None
        assert reason_fragment in result.reason


class TestSpecifierRewrite:
    def test_raise_floor(self) -> None:
        result = rewrite_specifier_lower_bound(">=3.9", Version("3.11"))
        assert result.status is RewriteStatus.UPDATED
        assert result.text == ">=3.11"

    def test_upper_bound_preserved(self) -> None:
        result = rewrite_specifier_lower_bound(">=3.9,<3.14", Version("3.11"))
        assert result.text == ">=3.11,<3.14"

    def test_empty_specifier_gets_floor(self) -> None:
        result = rewrite_specifier_lower_bound("", Version("3.11"))
        assert result.text == ">=3.11"

    def test_never_lowered(self) -> None:
        result = rewrite_specifier_lower_bound(">=3.12", Version("3.11"))
        assert result.status is RewriteStatus.UNCHANGED

    def test_unparsable_lower_bound_version(self) -> None:
        result = rewrite_specifier_lower_bound(">=3.*", Version("3.11"))
        assert result.status is RewriteStatus.SKIPPED
        assert result.reason is not None
        assert "lower-bound" in result.reason

    def test_unparsable_clause(self) -> None:
        result = rewrite_specifier_lower_bound("^3.9", Version("3.11"))
        assert result.status is RewriteStatus.SKIPPED
