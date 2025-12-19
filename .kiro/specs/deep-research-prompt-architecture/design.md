# Design Document: Deep Research Prompt Architecture

## Overview

This design defines an internal refactor to externalize Primr's Deep Research prompts from hardcoded Python strings to structured YAML configuration files. **The CLI behavior and user experience remain unchanged** - this is about maintainability, consistency, and future extensibility.

**Goals:**
1. **Separation of concerns**: Prompt engineering is decoupled from code
2. **Composability**: Shared components (epistemic rules, formatting, personas) are reusable
3. **Extensibility**: Foundation for future strategy modules (v1.2.6 roadmap)
4. **Maintainability**: Prompts are version-controlled and reviewable as clear diffs
5. **Editability**: Prompt engineers can refine prompts without touching Python code

**What stays the same:**
- `primr "Company" https://company.com` works exactly as before
- `--mode deep/full/scrape` unchanged
- `--cloud-vendor azure/aws/gcp` unchanged
- `--no-ai-strategy` unchanged
- Output files and formats unchanged

**What changes internally:**
- Prompts load from YAML instead of hardcoded Python strings
- Shared epistemic rules and formatting applied consistently
- Strategy modules (AI Strategy) can reference associated data files
- Foundation laid for `--strategy` flag (future, not implemented in this spec)

### Reference Documentation

Implementation should reference these key documents:
- `docs/documentation gemini deep research.txt` - Gemini Deep Research API guidance
- `docs/research putting it together.txt` - Recursive Hierarchical Research Architecture patterns

### Configuration Format: YAML

**Decision: Use YAML for all prompt configurations.**

Rationale:
1. **Multi-line strings**: YAML's `|` block scalar is perfect for long prompt prose
2. **Comments**: Essential for documenting why prompt sections exist
3. **Human editability**: Prompt engineers need to read and modify these easily
4. **Industry standard**: LangChain, Anthropic, OpenAI all use YAML for prompt configs
5. **Existing codebase**: Primr already uses YAML for `company_overview.yaml` and `ai_strategy.yaml`

JSON is better for API payloads, but YAML is the clear choice for human-editable configuration files with prose content.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLI Layer                                       │
│  primr "Company" https://company.com [--strategy ai,cloud] [--cloud-vendor] │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Prompt Composer                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ load_prompt()   │  │ compose()       │  │ substitute()    │             │
│  │ load_shared()   │  │ merge_shared()  │  │ validate()      │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
│   Prompt Configs      │ │   Shared Components   │ │   Strategy Modules    │
│                       │ │                       │ │                       │
│ company_overview.yaml │ │ shared/               │ │ strategies/           │
│ strategic_layer.yaml  │ │   epistemic_rules.yaml│ │   ai_strategy.yaml    │
│                       │ │   formatting.yaml     │ │   cloud_migration.yaml│
│                       │ │   personas.yaml       │ │   data_strategy.yaml  │
└───────────────────────┘ └───────────────────────┘ └───────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Deep Research Orchestrator                              │
│  Uses composed prompts to execute Deep Research API calls                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. PromptComposer

The central component that loads, composes, and builds prompts from YAML configurations.

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class PromptContext:
    """Runtime context for prompt variable substitution."""
    company_name: str
    website_url: str | None = None
    cloud_vendor: str = "agnostic"
    current_date: str | None = None  # Auto-populated if None
    has_stage1_context: bool = False
    custom_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class ComposedPrompt:
    """Result of prompt composition."""
    content: str
    source_files: list[str]
    section_count: int
    word_count: int
    variables_substituted: list[str]


class PromptComposer:
    """
    Composes prompts from YAML configurations with shared components.
    
    Usage:
        composer = PromptComposer()
        prompt = composer.compose(
            "company_overview",
            PromptContext(company_name="Tesla", website_url="https://tesla.com")
        )
    """
    
    def __init__(self, prompts_dir: Path | None = None):
        """Initialize with optional custom prompts directory."""
        ...
    
    def compose(self, prompt_name: str, context: PromptContext) -> ComposedPrompt:
        """
        Compose a complete prompt from YAML config and context.
        
        Args:
            prompt_name: Name of the prompt config (e.g., "company_overview")
            context: Runtime context for variable substitution
            
        Returns:
            ComposedPrompt with fully assembled content
        """
        ...
    
    def compose_strategy(self, strategy_name: str, context: PromptContext) -> ComposedPrompt:
        """
        Compose a strategy module prompt.
        
        Args:
            strategy_name: Name of the strategy (e.g., "ai", "cloud")
            context: Runtime context for variable substitution
            
        Returns:
            ComposedPrompt with strategy-specific content
        """
        ...
    
    def list_strategies(self) -> list[str]:
        """List all available strategy modules."""
        ...
    
    def validate_config(self, config_path: Path) -> list[str]:
        """
        Validate a prompt config file against the schema.
        
        Returns:
            List of validation errors (empty if valid)
        """
        ...
```

### 2. SharedComponentLoader

Loads and caches shared components (epistemic rules, formatting, personas).

```python
@dataclass
class SharedComponents:
    """Container for all shared prompt components."""
    epistemic_rules: dict[str, str]
    formatting_rules: dict[str, str]
    personas: dict[str, str]
    
    def get_default_persona(self) -> str:
        """Get the default consulting persona."""
        return self.personas.get("senior_consultant", "")


class SharedComponentLoader:
    """
    Loads shared components from YAML files with caching.
    
    Components are loaded once and cached for the lifetime of the loader.
    """
    
    def __init__(self, shared_dir: Path):
        """Initialize with path to shared components directory."""
        ...
    
    def load(self) -> SharedComponents:
        """Load all shared components."""
        ...
    
    def reload(self) -> SharedComponents:
        """Force reload of all shared components (clears cache)."""
        ...
```

### 3. PromptConfig Schema

The YAML schema for prompt configuration files.

```python
@dataclass
class SectionSpec:
    """Specification for a single report section."""
    id: str
    name: str
    part: int  # 1-5 for the five parts of the report
    purpose: str
    covers: list[str] = field(default_factory=list)
    depth: str = ""
    subsections: list["SectionSpec"] = field(default_factory=list)


@dataclass
class PromptConfig:
    """Complete prompt configuration from YAML."""
    meta: dict[str, Any]  # name, version, description
    document_purpose: str
    sections: list[SectionSpec]
    
    # Optional overrides for shared components
    epistemic_rules_override: dict[str, str] | None = None
    formatting_override: dict[str, str] | None = None
    persona_override: str | None = None
    
    # Strategy-specific fields
    vendor_guidance: dict[str, Any] | None = None  # For AI strategy
    
    @property
    def name(self) -> str:
        return self.meta.get("name", "Unknown")
    
    @property
    def version(self) -> str:
        return self.meta.get("version", "0.0.0")
```

### 4. StrategyModuleRegistry

Discovers and manages strategy modules, including their associated data sources.

```python
@dataclass
class DataSource:
    """A data source associated with a strategy module."""
    name: str  # e.g., "azure_vendor_research"
    path: str  # Relative path to the data file
    description: str
    required: bool = False  # If True, strategy fails without this file
    
    def resolve_path(self, base_dir: Path) -> Path:
        """Resolve the data source path relative to base directory."""
        ...
    
    def exists(self, base_dir: Path) -> bool:
        """Check if the data source file exists."""
        ...


@dataclass
class StrategyModule:
    """Metadata about a strategy module."""
    name: str  # e.g., "ai", "cloud"
    display_name: str  # e.g., "AI Strategy", "Cloud Migration"
    description: str
    config_path: Path
    is_builtin: bool
    data_sources: list[DataSource] = field(default_factory=list)
    
    def get_context_files(self, base_dir: Path, vendor: str | None = None) -> list[Path]:
        """
        Get paths to context files for this strategy.
        
        For AI Strategy with vendor="azure", returns paths to Azure-specific
        vendor research files that should be uploaded to File Search Store.
        """
        ...


class StrategyModuleRegistry:
    """
    Registry for discovering and loading strategy modules.
    
    Automatically discovers modules from the strategies/ directory.
    Each module can specify associated data sources that provide
    current context to the Deep Research agent.
    """
    
    def __init__(self, strategies_dir: Path, data_dir: Path | None = None):
        """
        Initialize with paths to strategies and data directories.
        
        Args:
            strategies_dir: Path to strategies/ YAML configs
            data_dir: Path to data files (defaults to docs/)
        """
        ...
    
    def discover(self) -> list[StrategyModule]:
        """Discover all available strategy modules."""
        ...
    
    def get(self, name: str) -> StrategyModule | None:
        """Get a specific strategy module by name."""
        ...
    
    def list_names(self) -> list[str]:
        """List all strategy module names."""
        ...
    
    def get_context_files(self, name: str, vendor: str | None = None) -> list[Path]:
        """Get context files for a strategy module."""
        ...
```

## Data Models

### Directory Structure

```
src/primr/prompts/
├── __init__.py                    # Public API exports
├── composer.py                    # PromptComposer implementation
├── loader.py                      # YAML loading utilities (existing, enhanced)
├── schema.py                      # Dataclass definitions
├── registry.py                    # StrategyModuleRegistry
│
├── company_overview.yaml          # Strategic Company Overview prompt
├── strategic_layer.yaml           # Stage 2 strategic analysis (NEW)
│
├── shared/                        # Shared components (NEW)
│   ├── epistemic_rules.yaml       # Fact/inference/hypothesis rules
│   ├── formatting.yaml            # Formatting standards
│   └── personas.yaml              # Analyst personas
│
└── strategies/                    # Strategy modules
    ├── ai_strategy.yaml           # AI Strategy (existing, moved)
    ├── cloud_migration.yaml       # Cloud Migration (NEW)
    ├── data_strategy.yaml         # Data Strategy (NEW, placeholder)
    └── security_posture.yaml      # Security Posture (NEW, placeholder)
```

### YAML Schema: Shared Components

**shared/epistemic_rules.yaml:**
```yaml
# Epistemic Rules for Consulting-Grade Research
# These rules ensure intellectual honesty and appropriate hedging

rules:
  fact_inference_hypothesis: |
    Distinguish facts (with citations) from inferences (labeled as such) 
    from hypotheses (to validate).
  
  risk_framing: |
    Frame risks as "areas to explore" not definitive threats.
  
  hedging_language: |
    Use language like "appears to", "worth exploring", "we'd want to validate".
  
  transformation_rule: |
    If a sentence implies inevitability or failure, rewrite it as a 
    scenario comparison.
  
  confidence_labeling: |
    For any claim without direct citation, indicate confidence level:
    - High confidence: Multiple corroborating sources
    - Medium confidence: Single source or logical inference
    - Low confidence: Speculation based on patterns
```

**shared/formatting.yaml:**
```yaml
# Formatting Standards for Professional Output
# These rules ensure clean, readable documents

rules:
  paragraphs: "Write in full paragraphs with evidence"
  bullets: "Use bullets only for lists of specific items"
  bullet_depth: "Single-level bullets only, no nested hierarchies"
  no_dashes: "No em-dashes or en-dashes, use commas or periods instead"
  citations: "Cite sources at section end using [cite: X, Y, Z] format"
  tables: "Include tables for financials, competitors, timelines"
  numbers: "Use readable formats ($50M not $50,000,000.00)"
  headings: "Use natural headings that flow like a narrative"
```

**shared/personas.yaml:**
```yaml
# Consulting Personas for Prompt Injection
# These define the voice and perspective of generated content

personas:
  senior_consultant: |
    You are a senior strategy consultant at a top-tier firm preparing 
    pre-meeting research for a client engagement. Write with analytical 
    depth. Surface uncomfortable hypotheses. Prioritize clarity over 
    diplomacy. Treat strong claims as working hypotheses unless 
    explicitly supported by cited sources.
  
  ai_strategist: |
    You are a senior AI strategy consultant. Generate a comprehensive 
    AI roadmap for board-level decision making. Connect AI capabilities 
    to THIS company's specific business model, pain points, and 
    competitive pressures.
  
  technical_architect: |
    You are a principal technical architect assessing infrastructure 
    and platform decisions. Focus on practical implementation paths, 
    migration complexity, and operational considerations.
```

### YAML Schema: Strategy Module

**strategies/ai_strategy.yaml (structure):**
```yaml
meta:
  name: "AI Strategy"
  version: "1.0.0"
  description: "AI roadmap and opportunity assessment"
  output_filename: "{company_name}_AI_Strategy"
  expected_pages: "15-30"  # Guidance for expected output length

# Override default persona for this strategy
persona: "ai_strategist"

document_purpose: |
  This strategy document answers "What should we actually do with AI, 
  and why?" Connect AI capabilities to THIS company's specific business 
  model, pain points, and competitive pressures.

# Associated data sources - files that provide current context
# These are uploaded to File Search Store for the Deep Research agent
data_sources:
  - name: "vendor_research_azure"
    path: "docs/vendor-research-azure-2025-12.txt"
    description: "Latest Azure AI services and capabilities"
    vendor: "azure"  # Only used when --cloud-vendor azure
  - name: "vendor_research_aws"
    path: "docs/vendor-research-aws-2025-12.txt"
    description: "Latest AWS AI services and capabilities"
    vendor: "aws"
  - name: "vendor_research_gcp"
    path: "docs/vendor-research-gcp-2025-12.txt"
    description: "Latest GCP AI services and capabilities"
    vendor: "gcp"
  - name: "vendor_research_agnostic"
    path: "docs/vendor-research-agnostic-2025-12.txt"
    description: "Cloud-agnostic AI guidance"
    vendor: "agnostic"

# Vendor-specific guidance embedded in the prompt
vendor_guidance:
  azure:
    display_name: "Microsoft Azure"
    key_services:
      foundation_models:
        - "Azure OpenAI Service (GPT-4, GPT-4o)"
        - "Azure AI Studio"
      # ... more services
  aws:
    display_name: "Amazon Web Services"
    # ... AWS services
  gcp:
    display_name: "Google Cloud Platform"
    # ... GCP services
  agnostic:
    display_name: "Cloud-Agnostic"
    guidance: "Compare options across major cloud providers"

sections:
  - id: executive_summary
    name: "Executive Summary"
    purpose: "Board-level overview of AI opportunity and recommended path"
    covers:
      - "Current AI maturity assessment"
      - "Top 3 high-impact opportunities"
      - "Recommended 12-month roadmap"
      - "Investment requirements and expected ROI"
    depth: "Concise but substantive, 1-2 pages"
  
  # ... more sections (15-20 sections for comprehensive 15-30 page output)
```

### Data Source Integration

Strategy modules can reference external data files that provide current context to the Deep Research agent. This is critical for:

1. **AI Strategy**: Vendor research files with latest service announcements
2. **Cloud Migration**: Current pricing, service comparisons, migration guides
3. **Security Posture**: Compliance frameworks, threat intelligence

The data sources are:
- Uploaded to File Search Store before the Deep Research API call
- Referenced in the prompt with hierarchy of truth instructions
- Filtered by vendor when applicable (e.g., only Azure files for `--cloud-vendor azure`)

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: YAML Loading Round-Trip
*For any* valid prompt configuration, loading the YAML and then serializing it back should produce semantically equivalent content.
**Validates: Requirements 1.1**

### Property 2: Shared Component Inclusion
*For any* prompt built by the PromptComposer, the output SHALL contain all epistemic rules from `shared/epistemic_rules.yaml`.
**Validates: Requirements 2.1, 7.1, 7.2, 7.3, 7.4**

### Property 3: Formatting Rules Inclusion
*For any* prompt built by the PromptComposer, the output SHALL contain all formatting rules from `shared/formatting.yaml`.
**Validates: Requirements 2.2, 8.1, 8.2, 8.3, 8.4, 8.5**

### Property 4: Variable Substitution Completeness
*For any* prompt with placeholders and a PromptContext with values, all placeholders SHALL be replaced with their corresponding values.
**Validates: Requirements 9.1, 9.2, 9.3, 9.4**

### Property 5: Missing Variable Graceful Handling
*For any* prompt with placeholders and a PromptContext with missing values, the system SHALL either use defaults or omit sections without leaving raw placeholders in output.
**Validates: Requirements 9.5**

### Property 6: Section Completeness
*For any* company_overview prompt, the output SHALL contain all sections defined in the YAML configuration.
**Validates: Requirements 3.1, 3.5**

### Property 7: Section Spec Rendering
*For any* SectionSpec with purpose, covers, and depth fields, the rendered section SHALL include all three components.
**Validates: Requirements 6.2, 6.3, 6.4**

### Property 8: Subsection Hierarchy
*For any* section with subsections, the subsections SHALL be rendered with H3 headings when the parent is H2.
**Validates: Requirements 6.5**

### Property 9: Strategy Module Discovery
*For any* YAML file in the strategies/ directory, it SHALL appear in the list returned by `list_strategies()`.
**Validates: Requirements 4.5, 11.1, 11.4**

### Property 10: Strategy Module Validation
*For any* strategy module loaded, it SHALL be validated against the StrategyModule schema before use.
**Validates: Requirements 11.2**

### Property 11: Custom Strategy Shared Components
*For any* custom strategy module, the composed prompt SHALL include the same shared components as built-in modules.
**Validates: Requirements 11.3**

### Property 12: Override Precedence
*For any* prompt config that overrides a shared component, the prompt-specific value SHALL take precedence over the shared value.
**Validates: Requirements 2.5**

### Property 13: Context-Aware Prompt Building
*For any* prompt built with `has_stage1_context=True`, the output SHALL include hierarchy of truth instructions.
**Validates: Requirements 10.1, 10.2, 10.4**

### Property 14: Standalone Prompt Completeness
*For any* prompt built with `has_stage1_context=False`, the output SHALL be complete without referencing missing context.
**Validates: Requirements 10.5**

### Property 15: Vendor-Specific Content
*For any* AI strategy prompt with a specific cloud_vendor, the output SHALL contain vendor-specific guidance from the vendor_guidance section.
**Validates: Requirements 5.2**

### Property 16: Section Purpose Non-Empty
*For any* section defined in a prompt YAML, the purpose field SHALL be non-empty.
**Validates: Requirements 12.2**

### Property 17: Malformed YAML Error Handling
*For any* malformed YAML file, the loader SHALL raise a descriptive error identifying the file and issue.
**Validates: Requirements 1.5**

### Property 18: Multiple Strategy Output
*For any* request with multiple strategies, the system SHALL produce separate composed prompts for each.
**Validates: Requirements 4.3**

### Property 19: Data Source Vendor Filtering
*For any* strategy module with vendor-specific data sources, only the data sources matching the specified vendor SHALL be included in the context files.
**Validates: Requirements 4.6, 13.2**

### Property 20: Data Source File Resolution
*For any* data source defined in a strategy module, the system SHALL correctly resolve the file path relative to the data directory.
**Validates: Requirements 13.1, 13.3**

## Error Handling

### Configuration Errors

| Error Type | Cause | Handling |
|------------|-------|----------|
| `PromptConfigNotFoundError` | YAML file doesn't exist | Raise with file path and available alternatives |
| `PromptConfigParseError` | Invalid YAML syntax | Raise with line number and syntax issue |
| `PromptConfigValidationError` | Schema validation failure | Raise with field name and expected type |
| `SharedComponentMissingError` | Required shared file missing | Raise with component name and expected path |
| `StrategyModuleNotFoundError` | Unknown strategy name | Raise with name and list of available strategies |

### Runtime Errors

| Error Type | Cause | Handling |
|------------|-------|----------|
| `PlaceholderSubstitutionError` | Required variable missing | Use default or omit section gracefully |
| `CircularDependencyError` | Shared components reference each other | Detect during load, raise with cycle path |

## Testing Strategy

### Dual Testing Approach

This implementation uses both unit tests and property-based tests:

- **Unit tests**: Verify specific examples, edge cases, and integration points
- **Property-based tests**: Verify universal properties across all valid inputs using Hypothesis

### Property-Based Testing Framework

The implementation will use **Hypothesis** for property-based testing, as it's already used in the Primr codebase.

### Test Configuration

Each property-based test will:
- Run a minimum of 100 iterations
- Be tagged with the property it validates using the format: `**Feature: deep-research-prompt-architecture, Property {number}: {property_text}**`

### Key Test Strategies

1. **YAML Round-Trip Tests**: Generate random valid YAML structures, load them, serialize back, verify equivalence
2. **Substitution Tests**: Generate random company names, URLs, dates; verify all placeholders replaced
3. **Section Completeness Tests**: Load configs, verify all defined sections appear in output
4. **Discovery Tests**: Add/remove files from strategies/, verify list updates correctly
5. **Override Tests**: Create configs with overrides, verify precedence is correct

### Unit Test Coverage

- Loading specific YAML files and verifying content
- Error handling for missing/malformed files
- Integration with existing `build_company_overview_prompt()` function
- CLI flag parsing for `--strategy` and `--list-strategies`

