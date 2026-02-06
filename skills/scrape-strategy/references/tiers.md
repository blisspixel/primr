# Scraping Tiers Reference

## 8-Tier Fallback System

| Tier | Method | Speed | Use Case |
|------|--------|-------|----------|
| 1 | Playwright | Medium | JS-rendered content (default) |
| 2 | Playwright Aggressive | Medium | Accordions, lazy load, expandable content |
| 3 | curl_cffi | Fast | TLS compatibility for fingerprint-sensitive sites |
| 4 | DrissionPage Stealth | Slow | Challenge handling, protection bypass |
| 5 | DrissionPage | Slow | Driverless CDP browser |
| 6 | httpx | Fast | HTTP/2 sites |
| 7 | requests | Fast | Simple sites, no JS |
| 8 | Vision | Slow | AI-based extraction (opt-in) |

## Tier Selection Heuristics

### When to Expect Tier 1-2 (Playwright)
- Modern SPA sites (React, Vue, Angular)
- Sites with dynamic content loading
- Sites with accordions or expandable sections

### When to Expect Tier 3 (curl_cffi)
- Sites with TLS fingerprint detection
- Cloudflare-protected sites (some)
- Sites that block Python user agents

### When to Expect Tier 4-5 (DrissionPage)
- Sites with challenge pages
- Sites requiring JavaScript execution
- Sites with CAPTCHA (limited success)

### When to Expect Tier 6-7 (HTTP)
- Simple static sites
- API endpoints
- Sites without JavaScript requirements

### When to Expect Tier 8 (Vision)
- Sites with complex layouts
- PDF-heavy content
- Sites where text extraction fails

## Tier Statistics Interpretation

```yaml
tier_stats:
  playwright: 20
  playwright_aggressive: 8
  curl_cffi: 4
  drissionpage_stealth: 2
```

Higher numbers in lower tiers indicates a more protected site.
