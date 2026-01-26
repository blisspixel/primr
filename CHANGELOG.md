# Changelog

All notable changes to Primr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-01-26

### Added
- Multiple strategy document types (AI, Customer Experience, Security & Compliance, Data Fabric)
- `--list-strategies` command to show available strategy frameworks
- `--strategy-type` option for generating specific strategy documents
- Enhanced build configuration with proper version constraints
- Comprehensive security review and hardening (January 2026)
- XXE protection with secure XML parsing
- SSRF protection with URL validation
- Input validation across all user inputs
- Auto-detection of Python 3.11+ in setup wizard

### Changed
- Python requirement updated from 3.10 to 3.11+
- Updated project description to better reflect company intelligence focus
- Improved dependency management with version constraints
- Enhanced README with clearer pipeline explanation and mode descriptions
- Consolidated scraping logic into single `fetch_web_content()` function
- Better documentation of scraping tier escalation
- Setup wizard now auto-restarts with correct Python version if needed

### Fixed
- Deep Research connection drop recovery with automatic polling
- AI Strategy retry capability with `--ai-strategy-only` flag
- Windows PATH configuration in setup wizard
- Build artifact cleanup for network/sync drives

### Security
- All critical vulnerabilities addressed (see docs/SECURITY_REVIEW_2026-01-21.md)
- Secure XML parser prevents XXE attacks
- URL validation blocks SSRF attempts
- Comprehensive input validation

## [1.2.4] - 2025-12-23

### Added
- Quality assessment system for generated reports
- Automatic QA scoring with color-coded grades
- `--qa` and `--qa-recent` commands for manual QA
- Job recovery system for Deep Research

### Changed
- Improved CLI output with better progress indicators
- Enhanced error messages and user guidance

## [1.2.0] - 2025-12-19

### Added
- AI Strategy document generation with cloud vendor customization
- `--ai-strategy-only` flag for retry capability
- `--cloud-vendor` option (azure, aws, gcp)
- Batch processing with `--csv` flag

### Changed
- Unified pipeline architecture (modes are stopping points, not separate implementations)
- Improved scraping resilience with tier escalation
- Better handling of WAF-protected sites

## [1.1.0] - 2025-11-15

### Added
- Deep Research mode for external source validation
- Vision tier for JavaScript-heavy sites
- Automatic link discovery and selection

### Changed
- Refactored scraping into tiered approach (HTTP → Stealth → Browser → Vision)
- Improved cost estimation with `--dry-run`

## [1.0.0] - 2025-10-01

### Added
- Initial release
- Basic scraping and report generation
- Gemini API integration
- DOCX report output
