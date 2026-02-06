# Confidence Levels Reference

## Four-Level Confidence System

| Level | Meaning | Evidence Required |
|-------|---------|-------------------|
| `UNTESTED` | Claim extracted, not yet verified | None (initial state) |
| `VALIDATED` | Supporting evidence found | At least one corroborating source |
| `INVALIDATED` | Contradicting evidence found | At least one contradicting source |
| `CONFIRMED` | High confidence, multiple sources | Multiple independent sources |

## Hypothesis Lifecycle

```
                    UNTESTED
                       |
           +-----------+-----------+
           |           |           |
           v           v           v
       VALIDATED   INVALIDATED  (remains
           |                    UNTESTED)
           v
       CONFIRMED
```

## Hypothesis Structure

```yaml
hypothesis:
  id: "h_001"                       # Unique identifier
  claim: "Company uses AWS"         # The testable claim
  confidence: validated             # Current confidence level
  evidence:                         # Supporting/contradicting evidence
    - "Job posting mentions AWS certifications"
    - "CTO blog post discusses AWS migration"
  topic: "technology"               # Category for filtering
  created_at: "2026-02-01T10:00:00"
  updated_at: "2026-02-03T14:30:00"
  expires_at: "2026-05-01T10:00:00" # Optional expiration
```

## Expiration Defaults by Topic

| Topic | Expiration | Rationale |
|-------|-----------|-----------|
| Financial | 90 days | Quarterly updates |
| Technology | 180 days | Tech stack changes |
| Strategy | 365 days | Annual planning cycles |
| Leadership | No expiration | Until change detected |
