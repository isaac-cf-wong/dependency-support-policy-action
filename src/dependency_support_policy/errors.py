"""Exception hierarchy for dependency-support-policy."""

from __future__ import annotations


class DependencyPolicyError(Exception):
    """Base class for all errors raised by this package."""


class ConfigError(DependencyPolicyError):
    """Invalid configuration (CLI flags, action inputs, or the tool table)."""


class RegistryError(DependencyPolicyError):
    """Failure to retrieve or parse package release metadata."""


class PolicyError(DependencyPolicyError):
    """A support policy could not be evaluated (e.g. no stable releases)."""


class LockfileError(DependencyPolicyError):
    """uv lockfile regeneration failed."""
