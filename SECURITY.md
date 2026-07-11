# Security Policy

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

Please report vulnerabilities privately via
[GitHub Security Advisories](https://github.com/isaac-cf-wong/dependency-support-policy-action/security/advisories/new).
Do not open a public issue for security reports. You should receive a
response within a week.

## Scope notes

- The action runs entirely inside the workflow's runner; it needs no secrets
  and works with read-only `GITHUB_TOKEN` permissions.
- Release metadata is fetched from the PyPI JSON API over HTTPS; no other
  network access is performed.
- Workflows in this repository are linted with actionlint and audited with
  zizmor in CI.
