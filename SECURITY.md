# Security Policy

Primr is a local-first research CLI, web scraper, and MCP/A2A agent. Its security
boundary includes untrusted retrieved content, provider credentials, outbound
requests, local artifacts, and authenticated agent tools.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.39.x  | Yes                |
| < 1.39  | No                 |

The maintained package runtime range is Python 3.11 through 3.15.
Development and release verification use Python 3.15.

## Reporting a Vulnerability

If you discover a security vulnerability in Primr, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. Report security vulnerabilities privately through [GitHub vulnerability reporting](https://github.com/blisspixel/primr/security/advisories/new).
2. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes (optional)

### What to Expect

- Acknowledgment within 48 hours
- Status update within 7 days
- Fix timeline depends on severity:
  - Critical: 24-48 hours
  - High: 7 days
  - Medium: 30 days
  - Low: Next release

### Scope

Security issues we care about:
- SSRF vulnerabilities
- Authentication/authorization bypasses
- Injection attacks (SQL, command, template)
- Path traversal
- Sensitive data exposure
- Denial of service

Out of scope:
- Rate limiting effectiveness (configurable by deployment)
- Issues requiring physical access
- Social engineering

## Security Controls and Threat Model

See the [detailed threat model](docs/SECURITY.md) for security invariants,
implemented controls, known limitations, and accepted deployment assumptions.
[Security operations](docs/SECURITY_OPS.md) covers deployment and incident handling.
Dependency changes pass scheduled advisory audits and the normal CI security
gates, including CodeQL, Bandit, pip-audit, Trivy, and hash-locked container builds.
