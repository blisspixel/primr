# Scoring Framework Reference

## Grading Dimensions

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| Clarity | 25% | Readability, structure, flow |
| Completeness | 25% | Coverage of key topics |
| Insight Depth | 25% | Strategic value, non-obvious findings |
| Accuracy | 25% | Alignment with source data |

## Score Interpretation

| Score | Grade | Meaning |
|-------|-------|---------|
| 85-100 | A | Excellent, ready for use |
| 70-84 | B | Good, minor improvements possible |
| 55-69 | C | Acceptable, notable gaps |
| 40-54 | D | Below standard, needs revision |
| 0-39 | F | Unacceptable, major issues |

The QA gate threshold is 70 (B grade). Reports scoring below this trigger a warning.

## Common Quality Issues

### Clarity Issues
| Problem | Solution |
|---------|----------|
| Long paragraphs | Break into bullet points |
| Jargon overuse | Add definitions or simplify |
| Poor structure | Reorganize with clear headers |
| Passive voice | Rewrite in active voice |

### Completeness Issues
| Problem | Solution |
|---------|----------|
| Missing competitor | Run targeted deep research |
| Sparse financials | Check SEC filings, news |
| No leadership info | Search LinkedIn, press releases |
| Outdated data | Re-scrape or deep research |

### Insight Depth Issues
| Problem | Solution |
|---------|----------|
| Surface-level analysis | Add "so what" implications |
| Missing trends | Research industry context |
| No strategic recommendations | Add actionable insights |
| Generic conclusions | Make company-specific |

### Accuracy Issues
| Problem | Solution |
|---------|----------|
| Uncited claims | Add source citations |
| Contradictory info | Verify against primary sources |
| Outdated facts | Update with current data |
| Speculation as fact | Mark as hypothesis |

## QA Result Structure

```yaml
qa_result:
  overall_score: 78
  dimensions:
    clarity: 85
    completeness: 72
    insight_depth: 80
    accuracy: 75
  feedback:
    - section: "Executive Summary"
      score: 82
      issues: []
    - section: "Competitive Landscape"
      score: 65
      issues:
        - "Missing key competitor: TechCorp"
        - "Market share data outdated"
    - section: "Financial Analysis"
      score: 70
      issues:
        - "Revenue figures need citation"
```

## Refinement Strategies by Section

**Executive Summary** (score < 70):
- Ensure key findings are highlighted
- Check for clear value proposition
- Verify strategic recommendations present

**Competitive Landscape** (score < 70):
- Identify missing competitors
- Run deep research: "competitors of [company]"
- Update market positioning analysis

**Financial Analysis** (score < 70):
- Check for citation gaps
- Verify numbers against sources
- Add trend analysis if missing
