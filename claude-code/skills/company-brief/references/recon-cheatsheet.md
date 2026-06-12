# DNS recon interpretation cheatsheet

What passive DNS records reveal about a company's stack. All of this is public data served by their own nameservers; reading it is the same lookup any mail server performs.

## MX records (email platform)

| MX points at | Means |
|---|---|
| `*.mail.protection.outlook.com` | Microsoft 365 tenant (strong signal for Azure-leaning IT) |
| `*.google.com` / `*.googlemail.com` | Google Workspace (often GCP-friendly orgs) |
| `*.pphosted.com` / `*.proofpoint.com` | Proofpoint email security in front of mail (security-mature org) |
| `*.mimecast.com` | Mimecast email security |
| `*.barracudanetworks.com` | Barracuda (common in mid-market) |
| `*.mxrecord.io` or registrar-parked | Possibly minimal IT maturity |

## TXT records (SaaS verification trail)

Verification records are breadcrumbs of tools the org actually onboarded:

| TXT contains | Means |
|---|---|
| `MS=ms########` | Microsoft 365 domain verification |
| `google-site-verification=` | Google service (Workspace, Search Console) |
| `v=spf1 include:...` | Every `include:` is a service sending mail as them; read the list: `salesforce.com`, `zendesk.com`, `hubspot.com`, `mailgun.org`, `sendgrid.net`, `amazonses.com`, `pardot.com`, `marketo.com` each name a live tool |
| `atlassian-domain-verification=` | Jira/Confluence shop |
| `docusign=` | DocuSign |
| `stripe-verification=` | Stripe payments |
| `facebook-domain-verification=` | Meta ads/commerce presence |
| `_globalsign` / `digicert` DNS auth | Certificate management maturity |

## DMARC (email security posture)

`nslookup -type=TXT _dmarc.<domain>`:

| Policy | Means |
|---|---|
| `p=reject` | Mature email security program |
| `p=quarantine` | Partway there |
| `p=none` | Monitoring only; common, weaker posture |
| No record | No DMARC; notable absence for any sizable org |

## NS records and A records (hosting and cloud hints)

| Pattern | Means |
|---|---|
| `*.awsdns-*.com` nameservers | Route 53; AWS footprint likely |
| `*.azure-dns.*` | Azure DNS; Azure footprint likely |
| `*.googledomains.com` / Cloud DNS | GCP-leaning |
| `*.cloudflare.com` | Cloudflare in front (CDN/WAF; also explains scrape challenges) |
| A record in AWS/Azure/GCP IP space | Where the website actually runs (check with a whois/IP lookup if available) |
| `*.akam.net` / `*.edgekey.net` | Akamai (enterprise-grade delivery, larger org) |

## Calibration rules

- Email platform + a couple of SPF includes is normal evidence; one TXT record alone is weak evidence. Label accordingly: a single verification record supports `(Estimated)`, a consistent cluster supports stronger phrasing.
- Productivity-suite signals (M365/Workspace) indicate the IT estate, NOT the production cloud. Do not claim "runs on Azure" from M365 alone; say "Microsoft-centric IT estate (Estimated)".
- Marketing-site hosting (Cloudflare, Netlify, Vercel) says little about where production workloads run for a product company.
