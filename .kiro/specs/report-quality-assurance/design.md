# Design Document

## Overview

The Report Quality Assurance feature adds automatic post-generation validation to Primr, providing seamless quality assessment for all generated reports. By default, every report generation includes a QA step that produces a clean "Grade: (XX/100)" summary in the CLI while saving detailed analysis to the workspace for later review.

The QA system operates as an integrated final step in the research pipeline, using a separate AI model to critically evaluate generated reports. This provides users with immediate confidence feedback while maintaining clean CLI output and preserving comprehensive analysis details for deeper review when needed.

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Primr CLI                            │
└─────────────────────────────────────────────────────────┘
                          │
                          ├─────────────────────────────┐
                          │                             │
                          ▼                             ▼
┌─────────────────────────────────┐    ┌──────────────────────────────┐
│   Research Pipeline             │    │   QA Pipeline                │
│   (Existing)                    │    │   (New)                      │
│                                 │    │                              │
│  ┌──────────────────────────┐  │    │  ┌────────────────────────┐ │
│  │ Scrape/Deep/Full Mode    │  │    │  │ Report Loader          │ │
│  └──────────────────────────┘  │    │  └────────────────────────┘ │
│              │                  │    │              │               │
│              ▼                  │    │              ▼               │
│  ┌──────────────────────────┐  │    │  ┌────────────────────────┐ │
│  │ Report Generation        │  │    │  │ QA Analyzer            │ │
│  └──────────────────────────┘  │    │  └────────────────────────┘ │
│              │                  │    │              │               │
│              ▼                  │    │              ▼               │
│  ┌──────────────────────────┐  │    │  ┌────────────────────────┐ │
│  │ Output (DOCX/PDF/TXT)    │  │    │  │ Issue Classifier       │ │
│  └──────────────────────────┘  │    │  └────────────────────────┘ │
│                                 │    │              │               │
└─────────────────────────────────┘    │              ▼               │
                                       │  ┌────────────────────────┐ │
                                       │  │ QA Report Generator    │ │
                                       │  └────────────────────────┘ │
                                       │              │               │
                                       │              ▼               │
                                       │  ┌────────────────────────┐ │
                                       │  │ QA Output (TXT/JSON)   │ │
                                       │  └────────────────────────┘ │
                                       └──────────────────────────────┘
```

### Component Interaction Flow

1. **Automatic Integration**: QA runs automatically after every report generation (unless `--no-qa` specified)
2. **Report Analysis**: Separate AI model evaluates report across multiple dimensions
3. **Clean CLI Output**: Display simple "Grade: (XX/100)" summary to user
4. **Detailed Storage**: Save comprehensive QA analysis to workspace for later review
5. **Optional Detail Access**: `primr qa "Company"` command shows detailed analysis when needed

## Components and Interfaces

### 1. QA Integration Handler (`qa_integration.py`)

**Responsibility**: Integrate QA into main research pipeline

```python
class QAIntegration:
    """Handles automatic QA integration with report generation"""
    
    def run_post_generation_qa(self, report_path: Path, options: QAOptions) -> QAResult:
        """
        Run QA automatically after report generation
        
        Args:
            report_path: Path to generated report
            options: QA configuration options
            
        Returns:
            QAResult with grade and summary for CLI display
        """
        pass
    
    def format_cli_summary(self, qa_result: QAResult) -> str:
        """Format clean CLI output: 'Grade: (XX/100)'"""
        pass
```

**Interface**:
- Input: Generated report path, QA options
- Output: Clean CLI summary, detailed analysis saved to workspace
- Integration: Called automatically by research pipeline

### 2. QA Command Handler (`qa_command.py`)

**Responsibility**: CLI interface for detailed QA review

```python
class QACommand:
    """Handles detailed QA review command"""
    
    def show_detailed_analysis(self, company_name: str) -> None:
        """
        Display detailed QA analysis for a company report
        
        Args:
            company_name: Name of company to show QA details for
        """
        pass
    
    def validate_qa_exists(self, company_name: str) -> bool:
        """Validate that QA analysis exists for company"""
        pass
```

**Interface**:
- Input: Company name for detailed review
- Output: Comprehensive QA analysis displayed to console
- Usage: `primr qa "Tesla"` shows detailed analysis

### 2. Report Loader (`report_loader.py`)

**Responsibility**: Locate and load reports for QA analysis

```python
class ReportLoader:
    """Loads reports from workspace for QA analysis"""
    
    def find_latest_report(self, company_name: str) -> Optional[Report]:
        """Find most recent report for company"""
        pass
    
    def load_report_content(self, report_path: Path) -> ReportContent:
        """Load and parse report content"""
        pass
    
    def extract_metadata(self, report: Report) -> ReportMetadata:
        """Extract generation metadata (date, mode, model used)"""
        pass
```

**Interface**:
- Input: Company name or specific report path
- Output: Structured report content with metadata
- Handles: TXT, DOCX, and PDF formats

### 3. QA Analyzer (`qa_analyzer.py`)

**Responsibility**: Core QA logic using AI model

```python
class QAAnalyzer:
    """Performs quality analysis on reports"""
    
    def __init__(self, model_config: ModelConfig):
        """Initialize with QA model configuration"""
        pass
    
    def analyze_report(self, report: ReportContent) -> QAAnalysis:
        """
        Perform comprehensive quality analysis
        
        Returns analysis covering:
        - Citation accuracy
        - Logical consistency
        - Completeness
        - Factual accuracy
        - Section-level confidence scores
        """
        pass
    
    def check_citations(self, report: ReportContent) -> List[CitationIssue]:
        """Verify citations support claims"""
        pass
    
    def check_logic(self, report: ReportContent) -> List[LogicIssue]:
        """Identify contradictions and unsupported leaps"""
        pass
    
    def check_completeness(self, report: ReportContent) -> CompletenessScore:
        """Assess coverage against expected sections"""
        pass
```

**Interface**:
- Input: Report content, QA configuration
- Output: Structured analysis with issues and scores
- Uses: Configured AI model (default: Gemini 2.0 Flash Pro)

### 4. Issue Classifier (`issue_classifier.py`)

**Responsibility**: Categorize and prioritize identified issues

```python
class IssueClassifier:
    """Classifies and prioritizes QA issues"""
    
    def classify_issue(self, issue: RawIssue) -> ClassifiedIssue:
        """Categorize issue by type and severity"""
        pass
    
    def calculate_severity(self, issue: ClassifiedIssue) -> Severity:
        """Determine issue severity (critical, high, medium, low)"""
        pass
    
    def group_issues(self, issues: List[ClassifiedIssue]) -> GroupedIssues:
        """Group issues by type and section"""
        pass
```

**Issue Types**:
- **Factual**: Unsupported claims, potential inaccuracies
- **Logical**: Contradictions, unsupported analytical leaps
- **Completeness**: Missing sections, weak analysis areas
- **Citation**: Broken links, mismatched sources, missing citations

### 5. QA Report Generator (`qa_report_generator.py`)

**Responsibility**: Format and output QA results

```python
class QAReportGenerator:
    """Generates formatted QA reports"""
    
    def generate_report(self, analysis: QAAnalysis) -> QAReport:
        """Create formatted QA report"""
        pass
    
    def format_console_output(self, analysis: QAAnalysis) -> str:
        """Format for CLI display"""
        pass
    
    def save_to_file(self, report: QAReport, output_path: Path) -> None:
        """Save QA report to workspace"""
        pass
```

**Output Formats**:
- **Console**: Summary with key issues and overall score
- **TXT**: Detailed findings with line references
- **JSON**: Machine-readable format for potential automation

## Data Models

### QAOptions

```python
@dataclass
class QAOptions:
    """Configuration for QA execution"""
    model: str = "gemini-2.0-flash-thinking-exp"  # QA model to use
    enabled: bool = True  # QA enabled by default
    verbose_cli: bool = False  # Show detailed CLI output
    save_detailed: bool = True  # Save detailed analysis to workspace
```

### QAResult

```python
@dataclass
class QAResult:
    """QA execution result"""
    grade: int  # 0-100 overall score
    summary: str  # Clean CLI summary
    detailed_analysis: QAAnalysis  # Full analysis for workspace storage
    needs_attention: bool  # True if grade < 70
```

### ReportContent

```python
@dataclass
class ReportContent:
    """Loaded report content"""
    company_name: str
    content: str
    sections: Dict[str, str]  # section_name -> content
    citations: List[Citation]
    metadata: ReportMetadata
    file_path: Path
```

### QAAnalysis

```python
@dataclass
class QAAnalysis:
    """Complete QA analysis results"""
    overall_score: int  # 0-100
    section_scores: Dict[str, int]
    issues: List[ClassifiedIssue]
    citation_check: CitationCheckResult
    logic_check: LogicCheckResult
    completeness_check: CompletenessCheckResult
    confidence_assessment: ConfidenceAssessment
    timestamp: datetime
    model_used: str
```

### ClassifiedIssue

```python
@dataclass
class ClassifiedIssue:
    """A classified QA issue"""
    issue_type: IssueType  # FACTUAL, LOGICAL, COMPLETENESS, CITATION
    severity: Severity  # CRITICAL, HIGH, MEDIUM, LOW
    section: str
    description: str
    location: str  # Line reference or section identifier
    suggestion: Optional[str]  # Recommended fix
```

### QAReport

```python
@dataclass
class QAReport:
    """Formatted QA report"""
    company_name: str
    analysis: QAAnalysis
    summary: str
    detailed_findings: str
    recommendations: List[str]
    generated_at: datetime
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: QA execution completeness
*For any* valid company report, when QA analysis is executed, the system should produce a QA report containing all required sections (overall score, issue classification, citation check, logic check, completeness check)
**Validates: Requirements 1.2, 2.1, 2.2, 2.3, 2.4, 2.5**

### Property 2: Score consistency
*For any* QA analysis, the overall score should be mathematically consistent with section scores (overall score should be within reasonable bounds of the weighted average of section scores)
**Validates: Requirements 3.1**

### Property 3: Issue location specificity
*For any* identified issue, the issue should include a specific location reference (section name, line number, or content excerpt) that can be traced back to the original report
**Validates: Requirements 3.3**

### Property 4: File persistence
*For any* completed QA analysis, when save_to_workspace is true, the QA report should be persisted to the file system in the expected location with proper naming conventions
**Validates: Requirements 3.4, 4.4**

### Property 5: Model configuration validation
*For any* QA model configuration, the system should validate that the specified model exists and is accessible before attempting analysis
**Validates: Requirements 4.1, 4.2, 4.3, 4.5**

### Property 6: Auto-QA integration
*For any* report generation with --auto-qa flag, the QA analysis should execute automatically after successful report generation without requiring additional user input
**Validates: Requirements 1.5**

### Property 7: Error recovery
*For any* API failure during QA analysis, the system should retry with exponential backoff and provide clear error messages if all retries fail
**Validates: Requirements 1.4**

### Property 8: Report existence validation
*For any* QA command execution, when no report exists for the specified company, the system should fail gracefully with an informative error message rather than attempting analysis
**Validates: Requirements 1.3**

## Error Handling

### Error Categories

1. **Missing Report Errors**
   - No report found for company
   - Report file corrupted or unreadable
   - Response: Clear error message with suggestions (check company name, run report first)

2. **API Errors**
   - QA model unavailable
   - Rate limiting
   - Authentication failures
   - Response: Retry with exponential backoff (3 attempts), then fail with clear message

3. **Configuration Errors**
   - Invalid QA model specified
   - Missing API keys
   - Invalid output format
   - Response: Validation at startup, clear error messages with correction guidance

4. **Analysis Errors**
   - Report too large for model context
   - Unexpected report format
   - Response: Graceful degradation, partial analysis if possible

### Retry Strategy

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((APIError, RateLimitError))
)
def analyze_with_retry(report: ReportContent) -> QAAnalysis:
    """Execute QA analysis with retry logic"""
    pass
```

## Testing Strategy

### Unit Tests

1. **Report Loader Tests**
   - Test loading reports in different formats (TXT, DOCX, PDF)
   - Test handling of missing reports
   - Test metadata extraction

2. **Issue Classifier Tests**
   - Test classification of different issue types
   - Test severity calculation
   - Test issue grouping logic

3. **QA Report Generator Tests**
   - Test console output formatting
   - Test file output generation
   - Test JSON serialization

### Property-Based Tests

Property-based tests will use Hypothesis to generate random test data and verify that correctness properties hold across all inputs.

**Configuration**:
- Library: Hypothesis (Python property-based testing)
- Minimum iterations: 100 per property test
- Each test tagged with: `# Feature: report-quality-assurance, Property X: [property description]`

**Test Coverage**:
- Property 1: Generate random report structures, verify all QA sections present
- Property 2: Generate random section scores, verify overall score consistency
- Property 3: Generate random issues, verify all have valid location references
- Property 4: Generate random QA results, verify file persistence
- Property 5: Generate random model configs, verify validation catches invalid ones
- Property 6: Test auto-QA integration with various report generation scenarios
- Property 7: Simulate API failures, verify retry behavior
- Property 8: Test with non-existent companies, verify error handling

### Integration Tests

1. **End-to-End QA Flow**
   - Generate report → Run QA → Verify output
   - Test with different report modes (scrape, deep, full)
   - Test with different QA models

2. **Auto-QA Integration**
   - Run report generation with --auto-qa
   - Verify QA executes automatically
   - Verify both reports saved correctly

3. **CLI Integration**
   - Test `primr qa` command with various options
   - Test error messages and user feedback
   - Test integration with `primr doctor` and `primr list`

### Edge Cases

1. Very large reports (test context window limits)
2. Reports with no citations
3. Reports with broken/invalid citations
4. Malformed report files
5. Concurrent QA operations
6. QA on reports generated with different Primr versions

## Implementation Notes

### QA Prompt Engineering

The QA analyzer will use a structured prompt that instructs the AI model to:

1. **Evaluate systematically** across defined dimensions
2. **Provide specific evidence** for each issue identified
3. **Assign confidence scores** to assessments
4. **Format output** as structured JSON for parsing

Example prompt structure:
```
You are a quality assurance analyst reviewing a company intelligence report.

Evaluate the report across these dimensions:
1. Citation Accuracy: Do sources support claims?
2. Logical Consistency: Are there contradictions or unsupported leaps?
3. Completeness: Are all expected sections present and well-developed?
4. Factual Accuracy: Do claims appear accurate and well-supported?

For each issue found:
- Specify the exact location (section and line)
- Classify the issue type
- Rate severity (critical/high/medium/low)
- Suggest a fix if possible

Provide an overall quality score (0-100) and section-level scores.

Report to analyze:
{report_content}
```

### Model Selection Rationale

**Default: Gemini 2.0 Flash Thinking Exp**
- Cost-effective for routine QA
- Fast inference for quick feedback
- Sufficient capability for most quality checks

**Optional: Gemini 2.0 Pro**
- Higher capability for complex analysis
- Better at nuanced logical reasoning
- Use for critical reports or when quality is paramount

### Performance Considerations

- QA analysis should complete in 2-5 minutes for typical reports
- Parallel processing for multiple QA checks where possible
- Caching of report parsing to avoid redundant work
- Streaming output for long-running QA operations

### Future Enhancements

1. **Comparative QA**: Compare multiple reports for the same company over time
2. **Custom QA Rules**: Allow users to define custom quality criteria
3. **QA Templates**: Different QA profiles for different report types
4. **Automated Fixes**: Suggest or apply automatic corrections for common issues
5. **QA Dashboard**: Visual summary of quality trends across reports