# Security Review and Improvements - February 2, 2026

## Executive Summary

Conducted security review of Primr v1.5.1 codebase. Identified and fixed 2 security issues:
1. JWT signature verification not implemented (MEDIUM) - FIXED
2. CORS configuration too permissive (LOW) - FIXED

## Improvements Made

### 1. JWT Signature Verification - FIXED

**Severity**: MEDIUM  
**Location**: `src/primr/mcp_server/auth.py`  
**Issue**: JWT tokens were decoded but signatures were not verified, allowing token forgery.

**Previous Code**:
```python
def _verify_jwt(self, token: str) -> AccessToken | None:
    """
    For production, this should verify the signature against a public key.
    For now, we do basic JWT structure validation and claim extraction.
    """
    # Only decoded payload, no signature verification
```

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

**Previous Code**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Fix Applied**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Configurable, defaults to localhost
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],  # Only methods we use
    allow_headers=["X-API-Key", "Content-Type", "Authorization"],
    max_age=600,  # Cache preflight for 10 minutes
)
```

**New Configuration**:
```bash
PRIMR_CORS_ORIGINS=https://your-frontend.com,https://admin.your-domain.com
```

**Default Behavior**: Only localhost origins allowed (secure for development).

## Existing Security Measures (Verified)

All security measures from the January 2026 review remain in place:

### SSRF Protection - VERIFIED
- URL validation at all 9 HTTP entry points
- Blocks localhost, private IPs, link-local addresses
- DNS resolution check prevents hostname-based bypasses
- Cloud metadata endpoints blocked

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
tests/test_security.py: 22 passed
tests/mcp_server/test_security.py: 27 passed (1 skipped - Windows-specific)
tests/test_api/test_service.py: 22 passed
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

## Recommendations

### Completed
1. ✅ JWT signature verification implemented
2. ✅ CORS configuration tightened
3. ✅ Comprehensive test coverage added

### For Production Deployment
1. Set `MCP_JWT_SECRET` to a strong random value (32+ characters)
2. Configure `PRIMR_CORS_ORIGINS` with specific allowed origins
3. Consider using `MCP_JWT_ISSUER` and `MCP_JWT_AUDIENCE` for additional validation
4. Run security tests before each release

## Conclusion

The Primr codebase now has comprehensive security protections:
- JWT authentication with proper signature verification
- SSRF, XXE, and path traversal protection
- Secure CORS configuration
- Rate limiting and input validation

**Security Status**: PRODUCTION READY

---

Review completed: February 2, 2026  
Improvements: JWT signature verification, CORS hardening  
Tests added: 15 new authentication tests
