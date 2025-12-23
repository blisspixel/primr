# QA Grading System Fix - Design Document

## Overview

The QA system should provide a simple, practical assessment: "Is this report accurate and well-written for internal research use?" This aligns with Primr's goal of helping teams "hit the ground running" with reliable strategic intelligence.

The current system fails because it tries to do too much complex analysis instead of focusing on the core question: Can we confidently use this report for internal decision-making?

## Architecture

### Simplified Architecture

```
Report Input → Simple Assessment → JSON Response → Actionable Feedback
     ↓              ↓                    ↓              ↓
Content Check → Single Rubric → Structured Output → Clear Recommendation
```

**Single Question**: Is this report ready for internal use?
**Single Output**: JSON with assessment and specific feedback

## Components and Interfaces

### 1. Enhanced QA Analyzer (`SimpleQAAnalyzer`)

**Purpose**: Evaluate reports against a single, practical rubric for internal research readiness, leveraging existing Primr infrastructure.

**Key Methods**:
```python
class SimpleQAAnalyzer:
    def assess_report(self, report: ReportContent) -> SimpleQAResult
    def _build_assessment_prompt(self, report: ReportContent) -> str
    def _parse_json_response(self, response: str) -> SimpleQAResult
    def _leverage_workspace_context(self, report: ReportContent) -> str
```

**Enhanced Context Integration**:
- **Workspace Context**: Use existing `consolidate_working_folder` to get structured context
- **Section Analysis**: Leverage existing section-by-section analysis for granular feedback
- **Industry Context**: Use existing industry/overview extraction for contextual assessment

**Single Rubric - Internal Research Readiness**:
- **Accuracy**: Claims appropriately qualified, sources cited, no obvious contradictions
- **Clarity**: Well-structured, clear strategic thesis, readable for internal teams
- **Completeness**: Covers expected areas, provides actionable insights
- **Confidence**: Can we use this for decision-making or does it need more work?

### 2. Robust JSON Parser (`SimpleJSONParser`)

**Purpose**: Extract structured feedback from AI response reliably.

**Expected JSON Format**:
```json
{
  "ready_for_use": true,
  "confidence_level": "high",
  "key_strengths": ["Clear strategic thesis", "Well-cited claims", "Actionable insights"],
  "areas_for_improvement": [],
  "recommendation": "Report is ready for internal use"
}
```

## Data Models

### Simple QA Models

```python
@dataclass
class SimpleQAResult:
    ready_for_use: bool
    confidence_level: Literal["high", "medium", "low"]
    key_strengths: List[str]
    areas_for_improvement: List[str]
    recommendation: str
    parsing_success: bool = True
    error_message: Optional[str] = None
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Analysis Prework

**Requirement 1.1**: WHEN the QA system analyzes a report THEN the system SHALL evaluate strategic coherence and hypothesis-driven framing per Primr standards
- **Thoughts**: This is about ensuring the assessment covers Primr's key quality indicators. We can test with reports that have/lack strategic coherence.
- **Testable**: yes - property

**Requirement 2.1**: WHEN QA analysis completes THEN the system SHALL provide specific, actionable feedback rather than just numerical scores
- **Thoughts**: This tests that the output contains actionable recommendations. We can verify the JSON contains specific feedback.
- **Testable**: yes - property

**Requirement 3.1**: WHEN comprehensive reports are analyzed THEN the system SHALL complete analysis without falling back to generic responses
- **Thoughts**: This tests reliability. We can use the Evertrue LLC report and similar comprehensive reports to verify proper analysis.
- **Testable**: yes - property

### Correctness Properties

**Property 1: Assessment covers Primr quality standards**
*For any* report analyzed, the QA system should evaluate strategic coherence, citation quality, and hypothesis-driven framing as specified in Primr's standards
**Validates: Requirements 1.1**

**Property 2: Feedback is actionable and specific**
*For any* QA analysis result, the output should contain specific strengths and improvement areas rather than generic scores or comments
**Validates: Requirements 2.1**

**Property 3: Comprehensive reports complete successfully**
*For any* well-structured report like the Evertrue LLC analysis, the system should provide a complete assessment without falling back to error responses
**Validates: Requirements 3.1**

## Error Handling

### Simplified Error Recovery

1. **JSON Parsing Failure**: Extract key information using regex patterns
2. **Model Failure**: Try one alternative model (gemini-3-flash)
3. **Complete Failure**: Return diagnostic information instead of generic fallback

```python
def handle_failure(error: Exception, report: ReportContent) -> SimpleQAResult:
    return SimpleQAResult(
        ready_for_use=False,
        confidence_level="low",
        key_strengths=[],
        areas_for_improvement=["QA analysis failed - manual review recommended"],
        recommendation=f"Technical issue prevented assessment: {str(error)}",
        parsing_success=False,
        error_message=str(error)
    )
```

## Testing Strategy

### Property-Based Testing Approach

**Property Test 1: Primr standards coverage**
```python
# Feature: qa-grading-fix, Property 1: Assessment covers Primr quality standards
@given(reports_with_varying_quality())
def test_primr_standards_coverage(report):
    result = simple_analyzer.assess_report(report)
    # Should evaluate strategic coherence, citations, hypothesis framing
    assessment_areas = result.key_strengths + result.areas_for_improvement
    assert any("strategic" in area.lower() for area in assessment_areas)
    assert any("citation" in area.lower() or "source" in area.lower() for area in assessment_areas)
```

**Property Test 2: Actionable feedback generation**
```python
# Feature: qa-grading-fix, Property 2: Feedback is actionable and specific
@given(any_report())
def test_actionable_feedback(report):
    result = simple_analyzer.assess_report(report)
    assert result.recommendation != ""
    assert len(result.key_strengths) > 0 or len(result.areas_for_improvement) > 0
    # Should not contain generic phrases
    assert "generic" not in result.recommendation.lower()
    assert "technical issues" not in result.recommendation.lower() or not result.parsing_success
```

**Property Test 3: Comprehensive report reliability**
```python
# Feature: qa-grading-fix, Property 3: Comprehensive reports complete successfully
@given(comprehensive_reports())
def test_comprehensive_report_reliability(report):
    result = simple_analyzer.assess_report(report)
    assert result.parsing_success == True
    assert result.error_message is None
    assert result.confidence_level in ["high", "medium", "low"]
```

## Implementation Plan

### Single Phase: Simplified QA (1 Week)
1. Replace complex QA analyzer with simple assessment focused on "ready for internal use?"
2. Implement single rubric evaluation with JSON response parsing
3. Add basic retry logic for model/parsing failures
4. Test with Evertrue LLC report and other comprehensive reports
5. Deploy with monitoring for success rate

## Success Metrics

1. **Reliability**: 95%+ of comprehensive reports get proper assessment (not error fallback)
2. **Usefulness**: Feedback helps users understand if report is ready for internal use
3. **Simplicity**: Single JSON response with clear recommendation
4. **Speed**: Assessment completes in under 30 seconds

## Risk Mitigation

1. **JSON Parsing**: Simple fallback to extract key information with regex
2. **Model Availability**: Single fallback model (gemini-3-flash)
3. **Complexity Creep**: Resist adding more rubrics - keep it simple and practical