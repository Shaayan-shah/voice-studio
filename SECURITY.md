# Security Policy

## Supported versions

Only the latest version on the default branch is currently supported.

## Reporting a vulnerability

Please do not report vulnerabilities in a public issue. Use GitHub's private vulnerability reporting feature for this repository when it is enabled. Include the affected version or commit, steps to reproduce, impact, and any suggested mitigation. Do not include credentials, private scripts, or personal documents.

The app is intended for local use and binds its HTTP server to `127.0.0.1`. Do not expose it through a reverse proxy or public network without a separate security review and appropriate authentication and request protections.
