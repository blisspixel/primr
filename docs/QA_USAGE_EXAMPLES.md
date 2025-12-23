# QA System Usage Examples

This guide provides practical examples of using the Primr QA system for different scenarios.

## Basic Usage Examples

### 1. Standard Report Generation with QA

```bash
# Generate report with automatic QA (default behavior)
primr "Microsoft Corporation" https://microsoft.com

# Output:
# Researching Microsoft Corporation...
# [Research progress...]
# Report generated: Microsoft_Corporation_Report_12-22-2025.docx
# Assessing quality...
# Grade: (87/100)
```

### 2. Generate Report Without QA

```bash
# Skip QA analysis entirely
primr "Apple Inc" https://apple.com --no-qa

# Output:
# Researching Apple Inc...
# [Research progress...]
# Report generated: Apple_Inc_Report_12-22-2025.docx
# (No QA assessment)
```

### 3. Review QA Analysis for Existing Report

```bash
# View detailed QA analysis
primr --qa "Microsoft Corporation"

# Output:
# ==========================================
# QA Analysis: Microsoft Corporation
# ==========================================
# 
# Reading QA analysis from: Microsoft_Corporation_QA_Report_12-22-2025_14-30-15.txt
# 
# Quality Assessment Report for Microsoft Corporation
# ==================================================
# Generated: 2025-12-22 14:30:15
# Analysis Model: gemini-2.0-flash-thinking-exp
# 
# OVERALL ASSESSMENT
# ------------------
# Quality Score: 87/100
# Confidence Level: 85/100
# [... detailed analysis ...]
```

### 4. View Recent QA Summary

```bash
# Show QA summary for 5 most recent reports (default)
primr --qa-recent

# Show QA summary for 10 most recent reports
primr --qa-recent 10

# Output:
# ==========================================
# QA Summary: 5 Most Recent Reports
# ==========================================
# 
# Found 5 report(s) with QA analysis:
# 
# #   Company                        Date         Grade    Status
# ----------------------------------------------------------------------
# 1   Microsoft Corporation          2025-12-22   87       ✓ Good
# 2   Apple Inc                      2025-12-21   92       ✓ Good
# 3   Tesla Inc                      2025-12-20   78       ~ Acceptable
# 4   Amazon Web Services            2025-12-19   65       ⚠️ Needs Work
# 5   Google LLC                     2025-12-18   89       ✓ Good
# 
# Average Quality Grade: 82.2/100
```

## Advanced Usage Examples

### 5. Batch Processing with QA

```bash
# Create CSV file with companies
cat > companies.csv << EOF
Company,Website
Tesla Inc,https://tesla.com
SpaceX,https://spacex.com
Neuralink,https://neuralink.com
EOF

# Process batch with QA enabled (default)
primr --csv companies.csv --mode deep

# Process batch without QA
primr --csv companies.csv --mode deep --no-qa
```

### 6. Different Research Modes with QA

```bash
# Quick analysis with QA
primr "Stripe" https://stripe.com --mode scrape

# Deep research with QA
primr "Stripe" https://stripe.com --mode deep

# Full pipeline with QA (default)
primr "Stripe" https://stripe.com --mode full
```

## QA Analysis Interpretation

### 7. Understanding QA Grades

#### Excellent Report (90-100)
```bash
primr --qa "Apple Inc"

# Sample output:
# Quality Score: 94/100
# 
# SECTION SCORES
# Executive Summary: 95/100
# Business Model: 92/100
# Financial Analysis: 96/100
# Market Position: 93/100
# 
# CITATION ANALYSIS
# Total Citations: 15
# Valid Citations: 15
# Citation Score: 100/100
# 
# LOGICAL CONSISTENCY
# No contradictions found
# Logic Score: 95/100
# 
# COMPLETENESS ASSESSMENT
# All expected sections present
# Completeness Score: 92/100
# 
# RECOMMENDATIONS
# Report quality is acceptable for use
```

#### Report Needing Attention (< 70)
```bash
primr --qa "Startup Company"

# Sample output:
# Quality Score: 65/100 ⚠️ NEEDS ATTENTION
# 
# DETAILED ISSUES
# 1. CITATION - HIGH
#    Section: Financial Analysis
#    Location: paragraph 3
#    Description: Revenue claim lacks supporting citation
#    Suggestion: Add reference to financial statements
# 
# 2. LOGICAL - MEDIUM
#    Section: Market Analysis
#    Location: section 2.1
#    Description: Market size estimate contradicts earlier figure
#    Suggestion: Reconcile conflicting market data
# 
# RECOMMENDATIONS
# 1. Review and address critical issues before using this report
# 2. Verify and update citations to improve credibility
# 3. Review logical consistency and strengthen analytical connections
```

## Integration Examples

### 8. QA with Different Output Formats

```bash
# Generate with custom output directory
primr "Netflix" https://netflix.com --output-dir ./reports

# QA files will be saved to ./reports/ directory
# - Netflix_Report_12-22-2025.docx
# - Netflix_QA_Report_12-22-2025_15-45-30.txt
```

### 9. QA with Context Files

```bash
# Use context files for deep analysis
primr "OpenAI" https://openai.com --mode deep --context ./ai_research.pdf

# QA will analyze the enhanced report with context
```

### 10. QA History Tracking

```bash
# Generate multiple reports over time
primr "Tesla" https://tesla.com
# Grade: (78/100)

# Later analysis
primr "Tesla" https://tesla.com
# Grade: (85/100)

# View history
primr --qa-recent 10
# Shows progression of Tesla reports with timestamps
```

## Troubleshooting Examples

### 11. Handling QA Failures

```bash
# If QA fails due to network issues
primr "Company" https://company.com

# Output might show:
# Assessing quality...
# Grade: QA Failed

# Check detailed logs
primr "Company" https://company.com --verbose

# Or skip QA if needed
primr "Company" https://company.com --no-qa
```

### 12. Debugging Low QA Scores

```bash
# Generate report
primr "Complex Corp" https://complexcorp.com
# Grade: (62/100) - Needs Attention

# Review detailed analysis
primr --qa "Complex Corp"

# Common issues and solutions:
# - Missing citations: Add more source references
# - Logical inconsistencies: Review section flow
# - Incomplete sections: Ensure all expected sections present
# - Low confidence: Add more supporting evidence
```

### 13. Comparing QA Across Reports

```bash
# Generate reports for comparison
primr "Established Corp" https://established.com
primr "Startup Corp" https://startup.com

# Compare QA results
primr --qa-recent 2

# Output shows comparative analysis:
# #   Company           Date         Grade    Status
# ---------------------------------------------------
# 1   Established Corp  2025-12-22   89       ✓ Good
# 2   Startup Corp      2025-12-22   67       ⚠️ Needs Work
```

## Best Practices Examples

### 14. Optimizing for High QA Scores

```bash
# Use full research mode for comprehensive analysis
primr "Target Company" https://target.com --mode full

# Include relevant context
primr "Target Company" https://target.com --context ./industry_report.pdf

# Use appropriate citation style
primr "Target Company" https://target.com --citation-style numbered
```

### 15. Monitoring QA Trends

```bash
# Regular QA monitoring script
#!/bin/bash

echo "Weekly QA Summary"
echo "=================="
primr --qa-recent 20

# Check for reports needing attention
echo ""
echo "Reports needing attention:"
primr --qa-recent 20 | grep "⚠️"
```

### 16. QA-Driven Report Improvement

```bash
# Initial report
primr "Company" https://company.com
# Grade: (72/100)

# Review issues
primr --qa "Company"
# Identify: Missing citations, weak financial section

# Regenerate with more context
primr "Company" https://company.com --context ./financial_data.pdf
# Grade: (84/100)

# Track improvement
primr --qa-recent 2
# Shows progression from 72 to 84
```

## Automation Examples

### 17. Automated QA Reporting

```bash
# Daily QA report script
#!/bin/bash

DATE=$(date +%Y-%m-%d)
REPORT_FILE="qa_summary_$DATE.txt"

echo "Daily QA Summary - $DATE" > $REPORT_FILE
echo "==============================" >> $REPORT_FILE
echo "" >> $REPORT_FILE

primr --qa-recent 10 >> $REPORT_FILE

# Email or save report
echo "QA summary saved to $REPORT_FILE"
```

### 18. QA-Based Quality Gates

```bash
# Quality gate script for CI/CD
#!/bin/bash

COMPANY="$1"
MIN_SCORE=75

# Generate report
primr "$COMPANY" --mode deep

# Check QA score
SCORE=$(primr --qa "$COMPANY" | grep "Quality Score:" | grep -o '[0-9]\+')

if [ "$SCORE" -ge "$MIN_SCORE" ]; then
    echo "✓ Quality gate passed: $SCORE/100"
    exit 0
else
    echo "✗ Quality gate failed: $SCORE/100 (minimum: $MIN_SCORE)"
    exit 1
fi
```

### 19. Bulk QA Analysis

```bash
# Analyze QA for all reports in output directory
#!/bin/bash

cd output
for report in *_Report_*.docx; do
    if [ -f "$report" ]; then
        # Extract company name from filename
        company=$(echo "$report" | sed 's/_Report_.*$//' | tr '_' ' ')
        echo "Analyzing: $company"
        primr --qa "$company" | grep "Quality Score:"
    fi
done
```

## Integration with Other Tools

### 20. QA Data Export

```bash
# Export QA data for analysis
#!/bin/bash

echo "Company,Date,Grade,Status" > qa_export.csv

primr --qa-recent 50 | grep -E "^[0-9]+" | while read line; do
    # Parse line and format as CSV
    # (Implementation depends on exact output format)
    echo "$line" | awk '{print $2","$3","$4","$5}' >> qa_export.csv
done

echo "QA data exported to qa_export.csv"
```

These examples demonstrate the flexibility and power of the Primr QA system for maintaining high-quality research reports across different use cases and workflows.