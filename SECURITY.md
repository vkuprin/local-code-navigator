# Security policy

## Supported version

Only the latest released plugin version is supported.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Please do not open a public issue for a suspected vulnerability.

Include the affected plugin version, coding-agent version, operating system, reproduction steps, and any relevant logs with secrets removed.

## Trust boundary

This repository contains configuration, a small Python launcher, and prompt guidance. At runtime, `uv` downloads and executes pinned `serena-agent`, `semble`, and `filelock` packages, and Semble downloads an embedding model. Review the upstream projects before installation in sensitive environments. No credentials are included in this plugin.
