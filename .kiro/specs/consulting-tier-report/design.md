# Design Document

## Overview

This design transforms the Company Researcher from a good automated report generator into a consulting-tier research platform. The core output remains a one-time, deep-dive company analysis snapshot, but with dramatically improved quality, insights, and presentation.

The architecture enhances the existing pipeline while adding new components for insight extraction, quality assurance, and professional formatting.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Research Pipeline                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │  Data    │───▶│ Insight  │───▶│ Section  │───▶│ Quality  │      │
│  │ Gatherer │    │ Engine   │    │ Writer   │    │ Grader   │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│       │                                               │              │
│       ▼                                               ▼              │
│  ┌──────────┐                                   ┌──────────┐        │
│  │ Source   │                                   │ Refinement│        │
│  │ Tracker  │                                   │ Loop     │        │
│  └──────────┘                                   └──────────┘        │
│                                                       │              │
│                                                       ▼              │
│                                                 ┌──────────┐        │
│                                                 │ Report   │        │
│                                                 │ Assembler│        │
│                                                 └──────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### Data Gatherer (Enhanced)
Coordinates multi-source data collection with source tracking.

```python
@dataclass
class GatheredData:
    content: str
    source_url: str
    source_type: SourceType  # WEBSITE, NEWS, SEC_FILING, LINKEDIN, CRUNCHBASE
    confidence: float
    gathered_at: datetime
    
class DataGatherer:
    def gather_all(company: str, website: str) -> list[GatheredData]
    def gather_website(website: str, max_pages: int) -> list[GatheredData]
    def gather_news(company: str, days: int) -> list[GatheredData]
    def gather_financials(company: str) -> list[GatheredData]
    def gather_competitors(company: str, industry: str) -> list[GatheredData]
```

### Insight Engine (New)
Extracts non-obvious insights from gathered data.

```python
@dataclass
class Insight:
    title: str
    description: str
    evidence: list[str]
    confidence: ConfidenceLevel  # HIGH, MEDIUM, LOW
    category: InsightCategory  # STRATEGIC, FINANCIAL, OPERATIONAL, RISK, OPPORTUNITY
    sources: list[str]

class InsightEngine:
    def extract_insights(data: list[GatheredData], company: str) -> list[Insight]
    def identify_risks(data: list[GatheredData]) -> list[Insight]
    def identify_opportunities(data: list[GatheredData]) -> list[Insight]
    def analyze_competitive_position(company: str, competitors: list[str]) -> list[Insight]
```

### Section Writer (Enhanced)
Generates report sections with clean formatting and source attribution.

```python
@dataclass
class SectionContent:
    title: str
    content: str
    sources: list[SourceCitation]
    confidence_notes: list[str]
    
class SectionWriter:
    def write_executive_summary(insights: list[Insight], data: list[GatheredData]) -> SectionContent
    def write_section(section_type: SectionType, context: ResearchContext) -> SectionContent
    def format_for_readability(content: str) -> str  # Removes em-dashes, emojis, etc.
```

### Quality Grader (Enhanced)
Evaluates and triggers refinement for low-quality sections.

```python
@dataclass
class QualityScore:
    score: float  # 0-10
    issues: list[str]
    suggestions: list[str]
    needs_refinement: bool

class QualityGrader:
    def grade_section(content: SectionContent, section_type: SectionType) -> QualityScore
    def check_coherence(sections: list[SectionContent]) -> list[str]
    def validate_no_filler(content: str) -> bool
    def check_formatting(content: str) -> list[str]  # Catches em-dashes, emojis, etc.
```

### Report Assembler (Enhanced)
Combines sections into a clean, professional document.

```python
class ReportAssembler:
    def assemble(sections: list[SectionContent], metadata: ReportMetadata) -> Report
    def generate_toc(sections: list[SectionContent]) -> str
    def append_sources(sources: list[SourceCitation]) -> str
    def export_docx(report: Report, path: str) -> None
    def export_pdf(report: Report, path: str) -> None
```

### Citation Processor (New)
Transforms inline URLs into numbered references for clean document output.

```python
class CitationStyle(Enum):
    NUMBERED = "numbered"    # [1] style with appendix (default)
    INLINE = "inline"        # Preserve inline URLs as-is
    SIDECAR = "sidecar"      # Separate {company}_sources.md file

@dataclass
class CitationResult:
    transformed_content: str
    citations: list[SourceCitation]
    reference_map: dict[str, int]  # URL -> reference number

class CitationProcessor:
    def __init__(self, style: CitationStyle = CitationStyle.NUMBERED):
        self.style = style
        self._url_to_ref: dict[str, int] = {}
        self._citations: list[SourceCitation] = []
        self._next_ref: int = 1
    
    def process_content(self, content: str) -> CitationResult:
        """Transform inline markdown links to numbered references.
        
        Input: "According to [Tesla](https://tesla.com), the Model 3..."
        Output: "According to Tesla [1], the Model 3..."
        
        Reuses reference numbers for duplicate URLs.
        """
        pass
    
    def get_reference_number(self, url: str, title: str = None) -> int:
        """Get or create reference number for a URL."""
        if url in self._url_to_ref:
            return self._url_to_ref[url]
        ref_num = self._next_ref
        self._next_ref += 1
        self._url_to_ref[url] = ref_num
        self._citations.append(SourceCitation(
            url=url,
            title=title or self._extract_domain(url),
            reference_number=ref_num
        ))
        return ref_num
    
    def generate_sources_appendix(self) -> str:
        """Generate formatted sources appendix."""
        pass
    
    def generate_sidecar_file(self, company_name: str) -> tuple[str, str]:
        """Generate sidecar sources file. Returns (filename, content)."""
        pass
```

### AI Strategy Analyzer (New)
Generates AI opportunity recommendations tailored to company and cloud vendor.

```python
class CloudVendor(Enum):
    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"
    AGNOSTIC = "agnostic"

class AICategory(Enum):
    CONVERSATIONAL = "conversational"    # Chatbots, virtual assistants
    AGENTIC = "agentic"                  # Autonomous task coordination
    GEN_BI = "gen_bi"                    # Natural language data interaction
    AUTOMATION = "automation"            # Process and decision automation
    PRODUCTIVITY = "productivity"        # Copilot, AI-assisted development
    ML_WORKLOADS = "ml_workloads"        # Model training, deployment

@dataclass
class AIOpportunity:
    title: str
    description: str
    category: AICategory
    technologies: list[str]
    business_impact: str
    implementation_complexity: str  # Low, Medium, High
    estimated_timeline: str

class AIStrategyAnalyzer:
    # Cloud vendor technology mappings
    VENDOR_TECHNOLOGIES = {
        CloudVendor.AZURE: {
            AICategory.CONVERSATIONAL: ["Azure OpenAI", "Copilot Studio", "Azure Bot Service"],
            AICategory.AGENTIC: ["Azure AI Agent Service", "Semantic Kernel", "AutoGen"],
            AICategory.GEN_BI: ["Microsoft Fabric", "Power BI Copilot", "Azure Synapse"],
            AICategory.AUTOMATION: ["Power Automate", "Azure Logic Apps", "AI Builder"],
            AICategory.PRODUCTIVITY: ["Microsoft 365 Copilot", "GitHub Copilot", "Azure AI Studio"],
            AICategory.ML_WORKLOADS: ["Azure Machine Learning", "Azure OpenAI Service", "Azure AI Services"],
        },
        CloudVendor.AWS: {
            AICategory.CONVERSATIONAL: ["Amazon Bedrock", "Amazon Lex", "Amazon Q"],
            AICategory.AGENTIC: ["Amazon Bedrock Agents", "AWS Step Functions", "Amazon Q Developer"],
            AICategory.GEN_BI: ["Amazon QuickSight Q", "Amazon Athena", "AWS Glue"],
            AICategory.AUTOMATION: ["AWS Lambda", "Amazon EventBridge", "AWS Step Functions"],
            AICategory.PRODUCTIVITY: ["Amazon Q Developer", "Amazon CodeWhisperer", "AWS App Studio"],
            AICategory.ML_WORKLOADS: ["Amazon SageMaker", "Amazon Bedrock", "AWS Trainium"],
        },
        CloudVendor.GCP: {
            AICategory.CONVERSATIONAL: ["Vertex AI", "Dialogflow CX", "Gemini API"],
            AICategory.AGENTIC: ["Vertex AI Agent Builder", "LangChain on GCP", "Gemini"],
            AICategory.GEN_BI: ["BigQuery ML", "Looker", "Vertex AI Search"],
            AICategory.AUTOMATION: ["Cloud Functions", "Workflows", "Document AI"],
            AICategory.PRODUCTIVITY: ["Gemini for Workspace", "Duet AI", "Cloud Code"],
            AICategory.ML_WORKLOADS: ["Vertex AI", "TPU", "AutoML"],
        },
    }
    
    def analyze(
        self, 
        company_research: Report, 
        cloud_vendor: CloudVendor = CloudVendor.AGNOSTIC
    ) -> list[AIOpportunity]:
        """Generate 5 AI opportunities based on company research and vendor."""
        pass
    
    def _identify_industry_opportunities(self, industry: str) -> list[AICategory]:
        """Identify most relevant AI categories for an industry."""
        pass
    
    def _generate_opportunity(
        self, 
        category: AICategory, 
        company_context: str,
        vendor: CloudVendor
    ) -> AIOpportunity:
        """Generate a specific AI opportunity with vendor-appropriate technologies."""
        pass
```

## Data Models

### Source Tracking
```python
class SourceType(Enum):
    COMPANY_WEBSITE = "company_website"
    NEWS_ARTICLE = "news_article"
    SEC_FILING = "sec_filing"
    LINKEDIN = "linkedin"
    CRUNCHBASE = "crunchbase"
    GLASSDOOR = "glassdoor"
    JOB_POSTING = "job_posting"
    ESTIMATE = "estimate"

@dataclass
class SourceCitation:
    url: str
    title: str
    source_type: SourceType
    accessed_at: datetime
    excerpt: str  # Relevant quote or data point
```

### Confidence Levels
```python
class ConfidenceLevel(Enum):
    VERIFIED = "verified"      # Direct from official source
    REPORTED = "reported"      # From credible news/reports
    INFERRED = "inferred"      # Derived from multiple signals
    ESTIMATED = "estimated"    # Best guess based on available data

@dataclass
class ConfidenceNote:
    statement: str
    confidence: ConfidenceLevel
    basis: str  # Why this confidence level
```

### Report Structure
```python
@dataclass
class ReportMetadata:
    company_name: str
    website: str
    industry: str
    generated_at: datetime
    research_duration_seconds: float
    sources_count: int
    
@dataclass  
class Report:
    metadata: ReportMetadata
    executive_summary: SectionContent
    sections: list[SectionContent]
    sources_appendix: list[SourceCitation]
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Executive Summary Completeness
*For any* generated report, the executive summary SHALL contain all required components: company snapshot, strategic position, at least 3 key insights, risks section, and recommended actions.
**Validates: Requirements 1.1**

### Property 2: Executive Summary Length
*For any* generated executive summary, the word count SHALL NOT exceed 500 words.
**Validates: Requirements 1.3**

### Property 3: Financial Data Inclusion
*For any* report where financial data is provided as input, the output SHALL contain financial metrics with trend indicators.
**Validates: Requirements 1.4, 3.1**

### Property 4: Competitor Count
*For any* competitive analysis section, when competitor data is available, the output SHALL reference at least 5 competitors.
**Validates: Requirements 2.2**

### Property 5: Insight Minimum Count
*For any* generated report, the Insight Engine SHALL produce at least 5 strategic insights.
**Validates: Requirements 4.1**

### Property 6: Recommendation Count and Structure
*For any* recommendations section, the output SHALL contain 3-5 recommendations, each with a rationale field.
**Validates: Requirements 4.3**

### Property 7: Source Attribution
*For any* fact or claim in the report, there SHALL be an associated source citation.
**Validates: Requirements 5.1**

### Property 8: Confidence Marking
*For any* estimated or inferred data point, the output SHALL include a confidence level indicator.
**Validates: Requirements 5.2, 3.3**

### Property 9: Sources Appendix
*For any* completed report, there SHALL be a sources appendix containing all referenced URLs with access timestamps.
**Validates: Requirements 5.5**

### Property 10: Clean Formatting - No Emojis or Em-dashes
*For any* generated content, the text SHALL NOT contain emoji characters (Unicode emoji ranges) or em-dash characters (—).
**Validates: Requirements 6.1, 11.1, 11.2**

### Property 11: Natural Headings
*For any* section heading in the report, the heading SHALL NOT begin with a number followed by a period (e.g., "1. Section").
**Validates: Requirements 6.2**

### Property 12: Readable Number Formatting
*For any* large number in the report, it SHALL be formatted in abbreviated form (e.g., $50M, 2.5K) rather than full numeric form with excessive decimal places.
**Validates: Requirements 6.5**

### Property 13: No Nested Numbering
*For any* list in the report, the list SHALL NOT use nested numbering schemes (e.g., 1.1.1, a.i.ii).
**Validates: Requirements 11.5**

### Property 14: Quality Refinement Trigger
*For any* section that scores below 7/10 on quality grading, the system SHALL trigger a refinement cycle.
**Validates: Requirements 9.1**

### Property 15: No Filler Content
*For any* generated section, the content SHALL NOT contain common filler phrases ("In conclusion", "It is important to note", "As mentioned above", placeholder text like "TBD" or "N/A" for required fields).
**Validates: Requirements 9.4**

### Property 16: Execution Time
*For any* standard report generation, the total execution time SHALL NOT exceed 300 seconds (5 minutes).
**Validates: Requirements 10.1**

### Property 17: Timeout Handling
*For any* section that exceeds 60 seconds of processing, the system SHALL proceed with available data and note the limitation.
**Validates: Requirements 10.5**

### Property 18: Citation Reference Numbering
*For any* content containing inline markdown links, the CitationProcessor SHALL replace each `[text](url)` with `text [n]` where n is a sequential reference number.
**Validates: Requirements 12.1**

### Property 19: Citation Deduplication
*For any* URL that appears multiple times in the document, the CitationProcessor SHALL assign the same reference number to all occurrences.
**Validates: Requirements 12.2**

### Property 20: Citation Round-Trip Consistency
*For any* content processed by CitationProcessor, the number of unique URLs in the input SHALL equal the number of entries in the generated sources appendix.
**Validates: Requirements 12.3**

### Property 21: AI Opportunity Count
*For any* AI strategy analysis, the AIStrategyAnalyzer SHALL produce exactly 5 AI opportunities.
**Validates: Requirements 13.2**

### Property 22: AI Opportunity Structure
*For any* generated AI opportunity, it SHALL contain all required fields: title, description, category, technologies, business_impact.
**Validates: Requirements 13.7**

### Property 23: Vendor Technology Alignment
*For any* AI opportunity generated with a specific cloud vendor, the technologies list SHALL only contain technologies from that vendor's catalog.
**Validates: Requirements 13.3, 13.4, 13.5**

## Error Handling

### Data Gathering Errors
- Website scraping failures: Log error, attempt alternative pages, continue with partial data
- API rate limits: Implement exponential backoff, queue requests
- Network timeouts: Retry up to 3 times with increasing delays

### AI Generation Errors
- Model failures: Fall back to alternative model, then to template-based content
- Token limits: Chunk large inputs, summarize intermediate results
- Quality failures: Trigger refinement loop up to 3 times before accepting

### Report Assembly Errors
- Missing sections: Generate placeholder with explanation, flag for review
- Formatting errors: Apply cleanup pass, validate output structure
- Export failures: Retry with simplified formatting, provide alternative format

## Testing Strategy

### Unit Testing
- Test individual components (DataGatherer, InsightEngine, SectionWriter, QualityGrader)
- Test data model serialization/deserialization
- Test formatting utilities (em-dash removal, emoji removal, number formatting)

### Property-Based Testing
Using Hypothesis (Python PBT library):
- Generate random company data and verify report structure properties
- Generate random text and verify formatting cleanup properties
- Generate random financial data and verify metric inclusion properties

### Integration Testing
- End-to-end report generation with mock data sources
- Quality grading and refinement loop testing
- Multi-format export testing (DOCX, PDF)

### Test Configuration
- Property tests: minimum 100 iterations per property
- Each property test tagged with: `**Feature: consulting-tier-report, Property {number}: {property_text}**`
