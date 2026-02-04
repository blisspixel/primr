# Security Review and Improvements - February 2, 2026

## Summary

Security review of Primr v1.5.1. Fixed JWT signature verification and CORS configuration, added security headers and operational tooling.

## Improvements Made

### 1. JWT Signature Verification - FIXED

**Severity**: MEDIUM  
**Location**: `src/primr/mcp_server/auth.py`  
**Issue**: JWT tokens were decoded but signatures were not verified, allowing token forgery.

**Fix Applied**:
- Implemented HMAC-SHA256/384/512 signature verification
- Reject unsigned tokens (alg: none) - prevents algorithm confusion attacks
- Constant-time signature comparison to prevent timing attacks
- Added issuer (`iss`) and audience (`aud`) claim validation
- Added not-before (`nbf`) claim validation
- Admin tokens now hashed before comparison

**New Configuration Options**:
```bash
MCP_JWT_SECRET=your-secret-key-minimum-32-characters
MCP_JWT_ISSUER=your-issuer        # Optional
MCP_JWT_AUDIENCE=your-audience    # Optional
```

**Test Coverage**: 15 new tests added covering:
- Signed JWT verification
- Unsigned JWT rejection
- Wrong signature rejection
- Unsupported algorithm rejection
- Issuer/audience validation
- Not-before claim validation
- Empty/malformed token handling

### 2. CORS Configuration - FIXED

**Severity**: LOW  
**Location**: `src/primr/api/service.py`  
**Issue**: CORS allowed all origins with credentials enabled.

**Fix Applied**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Configurable, defaults to localhost
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],  # Only methods we use
    allow_headers=["X-API-Key", "Content-Type", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    max_age=600,  # Cache preflight for 10 minutes
)
```

**New Configuration**:
```bash
PRIMR_CORS_ORIGINS=https://your-frontend.com,https://admin.your-domain.com
```

### 3. Security Headers Middleware - NEW

**Location**: `src/primr/api/service.py`  
**Added OWASP-recommended security headers to all API responses**:

| Header | Value | Purpose |
|--------|-------|---------|
| X-Content-Type-Options | nosniff | Prevents MIME sniffing |
| X-Frame-Options | DENY | Prevents clickjacking |
| X-XSS-Protection | 1; mode=block | Legacy XSS protection |
| Strict-Transport-Security | max-age=31536000; includeSubDomains | Enforces HTTPS |
| Content-Security-Policy | default-src 'self'; frame-ancestors 'none' | Restricts resource loading |
| Referrer-Policy | strict-origin-when-cross-origin | Controls referrer info |
| Permissions-Policy | geolocation=(), microphone=(), camera=() | Restricts browser features |

### 4. Request ID Tracking - NEW

**Location**: `src/primr/api/service.py`  
**Added request ID middleware for audit trails**:

- Generates unique UUID for each request
- Accepts client-provided X-Request-ID header
- Returns X-Request-ID in all responses
- Logs request ID for correlation

### 5. Rate Limit Headers - NEW

**Location**: `src/primr/api/service.py`  
**Added rate limit information in response headers**:

| Header | Description |
|--------|-------------|
| X-RateLimit-Remaining | Requests remaining in current window |
| X-RateLimit-Limit | Total requests allowed per hour |
| X-RateLimit-Reset | Seconds until rate limit resets (when exceeded) |

### 6. Security Utilities Module - NEW

**Location**: `src/primr/utils/security.py`  
**Comprehensive security utilities**:

- `secure_compare()` - Constant-time comparison for secrets
- `hash_secret()` / `verify_hashed_secret()` - Secure secret hashing with salt
- `mask_sensitive_data()` / `mask_dict_values()` - Sensitive data masking for logs
- `SecurityAuditLogger` - Structured security event logging
- `sanitize_log_input()` - Input sanitization for safe logging
- `generate_secure_token()` / `generate_secure_id()` - Cryptographically secure token generation
- `get_secret_from_env()` - Secure environment variable retrieval with validation

### 7. API Key Rotation - NEW

**Location**: `src/primr/api/auth.py`  
**Added zero-downtime key rotation with grace periods**:

- `rotate_key()` - Generate new key while keeping old one valid
- Configurable grace period (default 24 hours)
- Key expiration support with `expires_in_days`
- `get_expiring_keys()` - Find keys expiring soon
- `cleanup_expired()` - Remove old keys from memory
- Rotation callbacks for notifications

```python
# Rotate with 24-hour grace period
new_key = auth.rotate_key(old_key, grace_hours=24)
# Both keys work for 24 hours, then only new_key works
```

### 8. Security Operations Guide - NEW

**Location**: `docs/SECURITY_OPS.md`  
**Comprehensive operations guide including**:

- API key rotation best practices
- Cloud storage examples (AWS S3, GCP, Azure) with Terraform
- Lifecycle policies for audit log retention
- Security testing recommendations
- Penetration testing checklist
- Incident response procedures

## Existing Security Measures (Verified)

All security measures from the January 2026 review remain in place:

### SSRF Protection - VERIFIED & ENHANCED
- URL validation at all 9 HTTP entry points
- **NEW**: Orchestrator-level SSRF validation (defense in depth)
- **NEW**: Redirect SSRF bypass protection - validates final URL after redirects complete
- Blocks localhost, private IPs, link-local addresses
- DNS resolution check prevents hostname-based bypasses
- Cloud metadata endpoints blocked (169.254.169.254, metadata.google.internal, etc.)
- Protection applied before any network request is made
- Protection applied after redirects to catch redirect-based SSRF attacks

**Redirect SSRF Protection Details**:
A malicious server could redirect from a safe URL (e.g., `https://evil.com`) to an internal IP (e.g., `http://169.254.169.254/`), bypassing initial SSRF validation. This attack vector is now blocked:
- `validate_final_url_after_redirect()` function added to security module
- All HTTP clients (requests, httpx, curl_cffi) validate final URL after redirects
- `make_request()` in net.py validates final URL
- `HTTPClient.get()` in http_client.py validates initial URL and final URL after redirects
- `resolve_redirect_url()` in deep_research.py validates final URL
- `_check_website()` in preflight.py validates final URL

### XXE Protection - VERIFIED
- Secure XML parser with entity expansion disabled
- Applied to sitemap parsing

### Path Traversal Protection - VERIFIED
- Multi-layered defense with pattern matching
- Symlink detection and blocking
- System directory blocklist

### SQL Injection - VERIFIED
- All queries use parameterized statements

### Other Protections - VERIFIED
- No `eval()` or `exec()` usage
- No `pickle.load()` with untrusted data
- No `subprocess` with `shell=True`
- All YAML loading uses `yaml.safe_load()`
- No hardcoded secrets

## Test Results

```
tests/mcp_server/test_auth.py: 37 passed
tests/test_utils/test_security.py: 44 passed
tests/test_security.py: 33 passed (including 4 orchestrator SSRF tests + 4 redirect SSRF tests + 3 HTTPClient SSRF tests)
tests/mcp_server/test_security.py: 27 passed (1 skipped)
tests/test_api/test_service.py: 29 passed
tests/test_api/test_auth.py: 37 passed
```

## Security Configuration Reference

### MCP Server (HTTP Mode)

| Variable | Description | Required |
|----------|-------------|----------|
| `MCP_ADMIN_TOKENS` | Comma-separated static admin tokens | No |
| `MCP_JWT_SECRET` | Secret for JWT signature verification (min 32 chars) | For JWT auth |
| `MCP_JWT_ISSUER` | Expected JWT issuer claim | No |
| `MCP_JWT_AUDIENCE` | Expected JWT audience claim | No |

### REST API

| Variable | Description | Default |
|----------|-------------|---------|
| `PRIMR_CORS_ORIGINS` | Comma-separated allowed origins | localhost only |

## Still To Do

- External penetration testing
- Dependency vulnerability scanning in CI
- Consider bug bounty if adoption grows

## Conclusion

Basic security measures are in place. The codebase handles common attack vectors (SSRF, XXE, path traversal, JWT forgery) and includes operational tooling for key rotation and audit logging. 

Not battle-tested at scale. Run your own security assessment before production use.

---

Review: February 2, 2026
