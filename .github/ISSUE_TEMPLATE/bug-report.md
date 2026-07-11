---
name: 🐛 Bug Report
about: Create a report to help us improve
title: '[BUG]: '
labels: bug
assignees: ''
---

## 📝 Description

A clear and concise description of what the bug is.

## 🚀 Reproduction Steps

Steps to reproduce the behavior:

1. '...'
2. '...'
3. '...'

## 💻 Minimal Reproducible Example

Please provide the smallest `pyproject.toml` (and configuration) that
demonstrates the issue, plus the exact CLI command or workflow snippet:

```toml
# pyproject.toml
```

```bash
dependency-support-policy check --reference-date 2026-01-01
```

## 📋 Expected Behavior

A clear and concise description of what you expected to happen (e.g. the
floor you expected the policy to compute).

## 💥 Actual Behavior / Output

Add the CLI output, change-plan JSON, or workflow log here **after redacting
secrets** (API keys, tokens, credentials, private URLs/paths, personal data).
If this is a potential security vulnerability, do **not** post it publicly;
use the Security reporting channel instead.

```text

```

## 🛠 Environment Information

- **Python Version:** (e.g., 3.13)
- **Package / Action Version:** (e.g., 0.1.0 or the `uses:` ref)
- **uv Version:** (e.g., 0.9.0, if lockfile handling is involved)
- **Operating System:** (e.g., Windows 11, Ubuntu 22.04, macOS)
- **Where it runs:** (CLI locally, GitHub Actions, other CI)

## 📎 Additional Context

Add any other context about the problem here (e.g., screenshots, logs).
