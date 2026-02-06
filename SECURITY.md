# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.11.x  | Yes                |
| 1.7.x   | Yes                |
| 1.6.x   | Yes                |
| < 1.6   | No                 |

## Reporting a Vulnerability

If you discover a security vulnerability in Primr, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. Email security concerns to the maintainers (see GitHub profile for contact)
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

## Security Measures

Primr implements several security controls:

- **SSRF Protection**: All URLs validated against private IP ranges, cloud metadata endpoints, and DNS rebinding
- **Input Sanitization**: Company names and URLs sanitized against injection attacks
- **JWT Authentication**: Signed token verification for MCP HTTP mode
- **Rate Limiting**: Per-client request limits
- **Security Headers**: OWASP-recommended headers on all API responses

See [docs/SECURITY_OPS.md](docs/SECURITY_OPS.md) for operational security guidance.

## Security Audits

- January 2026: Initial security review (XXE, SSRF fixes)
- February 2026: JWT verification, CORS hardening, input sanitization

## Acknowledgments

We appreciate responsible disclosure and will acknowledge security researchers who report valid vulnerabilities (with permission).
