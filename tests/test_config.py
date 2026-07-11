"""Tests for configuration loading and validation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import tomlkit

from dependency_support_policy.config import LockMode, load_config, parse_package_overrides
from dependency_support_policy.errors import ConfigError

REFERENCE = date(2025, 1, 1)
PYPROJECT = Path("pyproject.toml")


def _load(toml_text: str = "", cli: dict | None = None):  # type: ignore[no-untyped-def]
    return load_config(PYPROJECT, tomlkit.parse(toml_text), REFERENCE, cli)


class TestDefaults:
    def test_empty_document(self) -> None:
        config = _load()
        assert config.policy_name == "spec0"
        assert config.python_support_months is None
        assert config.package_support_months is None
        assert config.package_overrides == {}
        assert config.include is None
        assert config.exclude == frozenset()
        assert config.groups == ("project",)
        assert config.manage_python is True
        assert config.lock is LockMode.OFF
        assert config.python_releases == {}


class TestToolTable:
    def test_full_table(self) -> None:
        config = _load(
            """
            [tool.dependency-support-policy]
            policy = "spec0"
            python-support-months = 48
            package-support-months = 30
            include = ["NumPy", "scipy"]
            exclude = ["Pandas"]
            groups = ["project", "optional:plot"]
            manage-python = false
            lock = "minimal"

            [tool.dependency-support-policy.package-support]
            numpy = 36

            [tool.dependency-support-policy.python-releases]
            "3.15" = 2026-10-01
            "3.16" = "2027-10-01"
            """
        )
        assert config.python_support_months == 48
        assert config.package_support_months == 30
        assert config.include == frozenset({"numpy", "scipy"})
        assert config.exclude == frozenset({"pandas"})
        assert config.groups == ("project", "optional:plot")
        assert config.manage_python is False
        assert config.lock is LockMode.MINIMAL
        assert config.package_overrides == {"numpy": 36}
        assert config.python_releases == {(3, 15): date(2026, 10, 1), (3, 16): date(2027, 10, 1)}

    def test_cli_overrides_table(self) -> None:
        config = _load(
            "[tool.dependency-support-policy]\npackage-support-months = 30\nlock = 'minimal'\n",
            cli={"package_support_months": 12, "lock": "upgrade", "exclude": ["numpy"]},
        )
        assert config.package_support_months == 12
        assert config.lock is LockMode.UPGRADE
        assert config.exclude == frozenset({"numpy"})

    def test_none_cli_values_ignored(self) -> None:
        config = _load(
            "[tool.dependency-support-policy]\npackage-support-months = 30\n",
            cli={"package_support_months": None},
        )
        assert config.package_support_months == 30


class TestValidation:
    @pytest.mark.parametrize(
        "toml_text",
        [
            "[tool.dependency-support-policy]\nunknown-key = 1\n",
            "[tool.dependency-support-policy]\npolicy = 5\n",
            "[tool.dependency-support-policy]\npython-support-months = 0\n",
            "[tool.dependency-support-policy]\npython-support-months = true\n",
            "[tool.dependency-support-policy]\npackage-support-months = -3\n",
            "[tool.dependency-support-policy]\npackage-support-months = 'many'\n",
            "[tool.dependency-support-policy]\ninclude = 'numpy'\n",
            "[tool.dependency-support-policy]\ninclude = [1]\n",
            "[tool.dependency-support-policy]\ngroups = []\n",
            "[tool.dependency-support-policy]\ngroups = 'project'\n",
            "[tool.dependency-support-policy]\nmanage-python = 'yes'\n",
            "[tool.dependency-support-policy]\nlock = 'sometimes'\n",
            "[tool.dependency-support-policy]\npackage-support = 3\n",
            "[tool.dependency-support-policy.package-support]\nnumpy = 'fast'\n",
            "[tool.dependency-support-policy.python-releases]\n'3.x' = 2026-10-01\n",
            "[tool.dependency-support-policy.python-releases]\n'3.15' = 20\n",
            "[tool.dependency-support-policy.python-releases]\n'3.15' = 'someday'\n",
            "[tool]\ndependency-support-policy = 'oops'\n",
        ],
    )
    def test_invalid_configuration(self, toml_text: str) -> None:
        with pytest.raises(ConfigError):
            _load(toml_text)


class TestPackageOverrides:
    def test_names_canonicalized(self) -> None:
        assert parse_package_overrides({"NumPy": 30, "My_Package": 12}) == {"numpy": 30, "my-package": 12}

    def test_invalid_months(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            parse_package_overrides({"numpy": 0})
