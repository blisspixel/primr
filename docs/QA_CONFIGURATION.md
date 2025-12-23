# QA System Configuration Guide

The Primr QA (Quality Assurance) system automatically evaluates the quality of generated reports and provides detailed feedback. This guide covers configuration options and best practices.

## Overview

The QA system:
- Runs automatically after report generation (enabled by default)
- Analyzes reports for citation accuracy, logical consistency, and completeness
- Provides clean CLI output with grades and detailed analysis files
- Supports multiple AI models for different use cases
- Includes comprehensive error handling and retry logic

## Quick Start

### Basic Usage

```bash
# Generate report with automatic QA (default behavior)
primr "Tesla" https://tesla.com

# Generate report without QA
primr "Tesla" https://tesla.com --no-qa

# View detailed QA analysis for a company
primr --qa "Tesla"

# View QA summary for recent reports
primr --qa-recent 5
```

### QA Output

The QA system provides two levels of output:

1. **CLI Summary**: Clean, immediate feedback
   ```
   Grade: (85/100)
   ```
   or
   ```
   Grade: (65/100) - Needs Attention
   ```

2. **Detailed Analysis**: Comprehensive reports saved to `output/` directory
   - File format: `Company_Name_QA_Report_MM-DD-YYYY_HH-MM-SS.txt`
   - Contains section scores, issue details, and recommendations

## Configuration

### Model Configuration

The QA system supports multiple AI models with different characteristics:

| Model | Provider | Cost | Best For |
|-------|----------|------|----------|
| gemini-2.0-flash-thinking-exp | Google | Free | General analysis, complex reasoning |
| gemini-2.0-flash | Google | Free | Fast analysis, general use |
| gemini-1.5-pro | Google | $0.00125/1K tokens | Complex reports, detailed analysis |

### Configuration File

QA settings are stored in `~/.primr/qa_config.json`:

```json
{
  "default_model": "gemini-2.0-flash-thinking-exp",
  "enabled_by_default": true,
  "save_detailed_reports": true,
  "max_retries": 3,
  "retry_base_delay": 2.0,
  "timeout_seconds": 120,
  "models": {
    "gemini-2.0-flash-thinking-exp": {
      "name": "gemini-2.0-flash-thinking-exp",
      "display_name": "Gemini 2.0 Flash Thinking (Experimental)",
      "provider": "google",
      "cost_per_1k_tokens": 0.0,
      "max_tokens": 8192,
      "supports_json_mode": true,
      "recommended_for": ["general", "technical", "analysis"],
      "available": true
    }
  }
}
```

### Configuration Options

- **default_model**: Model used for QA analysis
- **enabled_by_default**: Whether QA runs automatically (default: true)
- **save_detailed_reports**: Save detailed analysis files (default: true)
- **max_retries**: Maximum retry attempts for failed requests (default: 3)
- **retry_base_delay**: Base delay for exponential backoff (default: 2.0 seconds)
- **timeout_seconds**: Request timeout (default: 120 seconds)

## QA Analysis Components

### 1. Citation Accuracy
- Verifies claims are properly attributed
- Checks citation format consistency
- Identifies unsupported claims
- Note: Cannot verify external link validity

### 2. Logical Consistency
- Detects internal contradictions
- Validates analytical reasoning
- Identifies unsupported logical leaps
- Checks assumption clarity

### 3. Completeness Assessment
- Compares against expected report sections
- Evaluates analysis depth
- Identifies missing key topics
- Adapts to different report types

### 4. Confidence Assessment
- Evaluates certainty levels
- Identifies areas needing more evidence
- Provides section-by-section confidence scores

## Quality Scoring

### Score Ranges
- **90-100**: Excellent - Comprehensive, well-structured, logically sound
- **80-89**: Good - Solid analysis with minor gaps
- **70-79**: Acceptable - Adequate but could benefit from improvements
- **60-69**: Needs Work - Significant issues affecting credibility
- **0-59**: Poor - Major structural or logical flaws

### Score Components
The overall score is calculated from:
- Citation accuracy (25%)
- Logical consistency (25%)
- Completeness (25%)
- Confidence assessment (15%)
- Issue severity penalty (10%)

## Error Handling

The QA system includes comprehensive error handling:

### Automatic Retry
- Exponential backoff for API failures
- Handles rate limiting automatically
- Recovers from transient network issues

### Error Types
- **Model Errors**: Authentication, rate limits, model unavailability
- **File Errors**: Missing reports, permission issues, encoding problems
- **Analysis Errors**: Malformed responses, parsing failures

### Fallback Behavior
When QA analysis fails:
- Returns neutral score (50/100)
- Creates fallback analysis with system issue noted
- Continues report generation without blocking

## Advanced Usage

### Custom Models

Add custom models programmatically:

```python
from src.primr.qa.config import get_qa_config, QAModelConfig

config_manager = get_qa_config()
custom_model = QAModelConfig(
    name="custom-model",
    display_name="Custom Analysis Model",
    provider="custom",
    cost_per_1k_tokens=0.005,
    max_tokens=16384,
    recommended_for=["specialized"],
    available=True
)

config_manager.add_custom_model(custom_model)
config_manager.save_config()
```

### Cost Estimation

```python
from src.primr.qa.config import get_qa_config

config_manager = get_qa_config()
estimated_cost = config_manager.estimate_cost("gemini-1.5-pro", 5000)
print(f"Estimated cost: ${estimated_cost:.4f}")
```

### Model Validation

```python
from src.primr.qa.config import get_qa_config

config_manager = get_qa_config()
is_valid, error_msg = config_manager.validate_model("gemini-2.0-flash")
if not is_valid:
    print(f"Model validation failed: {error_msg}")
```

## Integration with Primr Commands

### Doctor Command
```bash
primr doctor
```
Includes QA model configuration validation.

### List Command
```bash
primr --list-recent
```
Shows QA grades alongside report information.

## Troubleshooting

### Common Issues

1. **QA Analysis Fails**
   - Check internet connection
   - Verify API credentials
   - Try with `--no-qa` to isolate issue

2. **Low Quality Scores**
   - Review detailed analysis file
   - Check citation formatting
   - Verify logical flow between sections

3. **Missing QA Reports**
   - Ensure `save_detailed_reports: true` in config
   - Check `output/` directory permissions
   - Verify report generation completed successfully

### Debug Mode

Enable verbose logging:
```bash
export PRIMR_LOG_LEVEL=DEBUG
primr "Company" --verbose
```

### Reset Configuration

Delete configuration file to restore defaults:
```bash
rm ~/.primr/qa_config.json
```

## Best Practices

### For High-Quality Reports
1. Include proper citations for all claims
2. Maintain logical flow between sections
3. Use clear, specific language
4. Include all expected sections for report type

### For QA Configuration
1. Use free models for general analysis
2. Reserve paid models for complex reports
3. Enable detailed report saving for review
4. Monitor QA grades over time for improvement

### For Development
1. Test QA system with sample reports
2. Validate custom model configurations
3. Monitor error rates and retry patterns
4. Use property-based tests for QA components

## API Reference

### QA Integration
```python
from src.primr.qa.integration import QAIntegration
from src.primr.qa.models import QAOptions

qa_options = QAOptions(enabled=True, save_detailed=True)
qa_integration = QAIntegration(qa_options)
result = qa_integration.run_post_generation_qa(report_path, company_name)
```

### Configuration Management
```python
from src.primr.qa.config import get_qa_config

config = get_qa_config()
summary = config.get_config_summary()
available_models = config.get_available_models()
```

### Command Interface
```python
from src.primr.qa.command import QACommand

qa_command = QACommand()
qa_command.show_detailed_analysis("Company Name")
qa_command.show_recent_qa_summary(10)
```