# Requirements Document

## Introduction

This document specifies requirements for creating an exceptional CLI user experience for Primr. The goal is not merely functional output, but a CLI that feels crafted, intentional, and delightful to use. We draw inspiration from the best CLI tools: the information density of htop, the visual clarity of npm/yarn, the progressive disclosure of git, and the polish of modern tools like gh, railway, and vercel.

Primr handles long-running operations (10-40 minutes) where user attention and trust are paramount. Every visual element must earn its place. The CLI should feel like a premium instrument, not a debug log.

## Glossary

- **Primr**: The AI-powered company research CLI tool
- **Console**: The terminal output system that handles all user-facing messages
- **Phase**: A major stage of research (e.g., Data Collection, Analysis, Report Generation)
- **Step**: An individual operation within a phase
- **Live Region**: A terminal area that updates in place without scrolling
- **Progressive Disclosure**: Showing minimal information by default, with detail available on demand
- **Information Scent**: Visual cues that help users predict what will happen next
- **Deep Research**: Autonomous multi-step research mode using Gemini Deep Research Agent
- **Structured Pipeline**: Website-focused research with scraping and section-by-section analysis

## Requirements

### Requirement 1: Visual Hierarchy and Information Architecture

**User Story:** As a user, I want the CLI output to have clear visual hierarchy, so that I can instantly distinguish between phases, steps, details, and results without reading every line.

#### Acceptance Criteria

1. WHEN displaying output THEN the Console SHALL use exactly four visual levels: Phase (bold/colored header), Step (indented with indicator), Detail (further indented, muted), and Result (highlighted)
2. WHEN transitioning between phases THEN the Console SHALL use whitespace and horizontal rules to create clear visual breaks
3. WHEN displaying nested information THEN the Console SHALL use consistent indentation (2 spaces per level)
4. WHEN displaying status indicators THEN the Console SHALL use a consistent symbol vocabulary (e.g., ">" for active, "+" for success, "x" for error, "!" for warning)
5. WHEN displaying any output THEN the Console SHALL respect terminal width and wrap or truncate intelligently

### Requirement 2: Live Progress Display

**User Story:** As a user watching a long operation, I want a live-updating progress display that shows exactly what is happening, so that I feel informed and in control.

#### Acceptance Criteria

1. WHEN an operation has known bounds THEN the Console SHALL display a progress bar with percentage, current/total count, and current item name
2. WHEN an operation has unknown bounds THEN the Console SHALL display a spinner with elapsed time and current activity description
3. WHEN displaying progress THEN the Console SHALL update in place (same line) to avoid scroll noise
4. WHEN progress updates THEN the Console SHALL update at least every 100ms for spinners and every item completion for progress bars
5. WHEN an operation exceeds 10 seconds THEN the Console SHALL display elapsed time in the progress area
6. WHEN an operation exceeds 60 seconds THEN the Console SHALL display estimated time remaining if calculable

### Requirement 3: Phase Orchestration Display

**User Story:** As a user running multi-phase research, I want to see a clear roadmap of phases with my current position, so that I understand the overall journey and can estimate completion.

#### Acceptance Criteria

1. WHEN research begins THEN the Console SHALL display a phase overview showing all phases with expected durations
2. WHEN entering a new phase THEN the Console SHALL display a phase header with phase number, name, description, and expected duration
3. WHEN a phase completes THEN the Console SHALL display a phase summary with actual duration, key metrics, and success/warning/error counts
4. WHEN displaying phase progress THEN the Console SHALL show a mini-roadmap indicator (e.g., "[1] Collect > [2] Analyze > [ ] Report")
5. WHEN a phase takes significantly longer than expected THEN the Console SHALL update the estimate and explain why

### Requirement 4: Contextual Time Display

**User Story:** As a user waiting for operations, I want time information that is contextually appropriate, so that I can plan without being overwhelmed by timestamps.

#### Acceptance Criteria

1. WHEN an operation takes less than 1 second THEN the Console SHALL not display duration
2. WHEN an operation takes 1-10 seconds THEN the Console SHALL display duration only on completion
3. WHEN an operation takes more than 10 seconds THEN the Console SHALL display live elapsed time during operation
4. WHEN displaying time THEN the Console SHALL use adaptive formatting: "<1m" shows seconds, "1-60m" shows "Xm Ys", ">60m" shows "Xh Ym"
5. WHEN an operation is expected to take more than 5 minutes THEN the Console SHALL display a "safe to leave" indicator

### Requirement 5: Error Presentation with Recovery Guidance

**User Story:** As a user encountering errors, I want errors to be clearly explained with specific recovery steps, so that I can fix issues without searching documentation.

#### Acceptance Criteria

1. WHEN an error occurs THEN the Console SHALL display the error with a distinct visual treatment (red, boxed, or otherwise prominent)
2. WHEN displaying an error THEN the Console SHALL include: error type, brief description, and at least one recovery suggestion
3. WHEN an error is recoverable THEN the Console SHALL offer to retry or provide the exact command to retry
4. WHEN an error is due to configuration THEN the Console SHALL show the specific config key and expected format
5. WHEN an error is due to network/API issues THEN the Console SHALL distinguish between "try again later" and "fix your setup"
6. WHEN multiple errors occur THEN the Console SHALL group them by category and show count

### Requirement 6: Warning and Degradation Communication

**User Story:** As a user, I want to understand when the system is operating in a degraded mode, so that I can decide whether to continue or fix issues first.

#### Acceptance Criteria

1. WHEN a non-fatal issue occurs THEN the Console SHALL display a warning with yellow/amber styling
2. WHEN the system falls back to a secondary method THEN the Console SHALL explain what happened and what was used instead
3. WHEN data quality is degraded THEN the Console SHALL indicate which sections may be affected
4. WHEN displaying warnings THEN the Console SHALL not interrupt flow but SHALL summarize warnings at phase end

### Requirement 7: Final Output Presentation

**User Story:** As a user completing research, I want the final output to feel like a reward, so that the long wait feels worthwhile.

#### Acceptance Criteria

1. WHEN research completes successfully THEN the Console SHALL display a prominent success banner with the company name
2. WHEN displaying output files THEN the Console SHALL show each file type on its own line with full path
3. WHEN displaying output files THEN the Console SHALL indicate file sizes
4. WHEN research completes THEN the Console SHALL display a summary table with: duration, pages scraped, sections generated, estimated cost, actual cost
5. WHEN cost differs significantly from estimate THEN the Console SHALL explain the variance
6. WHEN AI strategy was generated THEN the Console SHALL highlight it as a separate deliverable

### Requirement 8: Doctor Command as Diagnostic Dashboard

**User Story:** As a user checking system status, I want the doctor command to feel like a comprehensive health check, so that I have confidence in my setup.

#### Acceptance Criteria

1. WHEN running doctor THEN the Console SHALL display a header with Primr version and system info
2. WHEN checking each component THEN the Console SHALL show the check name, status (pass/warn/fail), and relevant detail
3. WHEN a check fails THEN the Console SHALL show the exact fix command or config change needed
4. WHEN a check warns THEN the Console SHALL explain the impact of not fixing it
5. WHEN all checks pass THEN the Console SHALL display a clear "ready to research" message
6. WHEN displaying results THEN the Console SHALL align all status indicators and use consistent column widths

### Requirement 9: Batch Mode as Job Dashboard

**User Story:** As a user running batch research, I want a dashboard view of all jobs, so that I can monitor progress across multiple companies.

#### Acceptance Criteria

1. WHEN starting batch mode THEN the Console SHALL display total companies and estimated total duration
2. WHEN processing companies THEN the Console SHALL display a compact status line for each: company name, status (queued/running/done/failed), duration
3. WHEN a company completes THEN the Console SHALL update its status in place if terminal supports it, otherwise append
4. WHEN batch mode completes THEN the Console SHALL display a summary table: total succeeded, total failed, total duration, total cost
5. WHEN failures occur THEN the Console SHALL list failed companies with brief error reasons at the end
6. WHEN batch mode is interrupted THEN the Console SHALL save progress and show how to resume

### Requirement 10: Cost Transparency

**User Story:** As a user, I want complete transparency about costs, so that I can budget and avoid surprises.

#### Acceptance Criteria

1. WHEN displaying cost estimates THEN the Console SHALL show breakdown by component (API calls, tokens, etc.)
2. WHEN displaying cost estimates THEN the Console SHALL show range (min-max) based on historical data
3. WHEN research completes THEN the Console SHALL show actual cost with comparison to estimate
4. WHEN actual cost exceeds estimate by more than 20% THEN the Console SHALL explain why
5. WHEN running with --dry-run THEN the Console SHALL show detailed cost breakdown without executing

### Requirement 11: Confirmation Flow with Full Context

**User Story:** As a user about to run expensive operations, I want a confirmation screen that gives me all the information I need to decide, so that I never feel surprised.

#### Acceptance Criteria

1. WHEN confirmation is required THEN the Console SHALL display: company name, research mode, estimated duration, estimated cost
2. WHEN displaying confirmation THEN the Console SHALL show what outputs will be generated
3. WHEN displaying confirmation THEN the Console SHALL accept y/n/q (yes/no/quit) with clear key labels
4. WHEN user types 'n' THEN the Console SHALL exit with message "Research cancelled. No charges incurred."
5. WHEN user types 'y' THEN the Console SHALL immediately begin with no additional prompts
6. WHEN --yes flag is provided THEN the Console SHALL skip confirmation but still display the estimate summary

### Requirement 12: Help System with Examples

**User Story:** As a user learning Primr, I want help that teaches by example, so that I can quickly understand how to use each feature.

#### Acceptance Criteria

1. WHEN displaying help THEN the Console SHALL organize commands into logical groups (Research, Utilities, Options)
2. WHEN displaying a command THEN the Console SHALL show at least one realistic example
3. WHEN displaying options THEN the Console SHALL show default values in brackets
4. WHEN displaying help THEN the Console SHALL use consistent column alignment
5. WHEN user runs invalid command THEN the Console SHALL suggest the closest valid command
6. WHEN user runs command with missing required args THEN the Console SHALL show usage for that specific command

### Requirement 13: Quiet and JSON Output Modes

**User Story:** As a user integrating Primr into scripts, I want machine-readable output options, so that I can parse results programmatically.

#### Acceptance Criteria

1. WHEN --quiet is specified THEN the Console SHALL suppress all output except errors and final file paths
2. WHEN --json is specified THEN the Console SHALL output structured JSON with: status, duration, cost, output_files, errors
3. WHEN --json is specified THEN the Console SHALL suppress all human-readable formatting
4. WHEN errors occur in --json mode THEN the Console SHALL include error details in the JSON structure
5. WHEN --quiet is specified THEN the Console SHALL still respect --verbose for debugging

### Requirement 14: Keyboard Interrupt Handling

**User Story:** As a user who needs to cancel an operation, I want graceful interrupt handling, so that I understand what happened and what state things are in.

#### Acceptance Criteria

1. WHEN user presses Ctrl+C THEN the Console SHALL immediately acknowledge with "Cancelling..."
2. WHEN cancelling THEN the Console SHALL complete any in-progress file writes to avoid corruption
3. WHEN cancelled THEN the Console SHALL display what was completed and what was not
4. WHEN cancelled THEN the Console SHALL display any partial outputs that were saved
5. WHEN cancelled during batch mode THEN the Console SHALL offer to save progress for resume

### Requirement 15: Terminal Capability Adaptation

**User Story:** As a user with various terminal setups, I want the CLI to adapt to my terminal's capabilities, so that output looks good everywhere.

#### Acceptance Criteria

1. WHEN terminal does not support colors THEN the Console SHALL fall back to plain text with ASCII indicators
2. WHEN terminal width is narrow THEN the Console SHALL wrap or truncate content appropriately
3. WHEN output is piped THEN the Console SHALL disable colors and animations automatically
4. WHEN terminal does not support cursor movement THEN the Console SHALL use append-only output
5. WHEN NO_COLOR environment variable is set THEN the Console SHALL disable all colors

### Requirement 16: Startup Performance Perception

**User Story:** As a user starting Primr, I want the CLI to feel instant and responsive, so that I have confidence in the tool.

#### Acceptance Criteria

1. WHEN Primr starts THEN the Console SHALL display first output within 500ms
2. WHEN loading configuration THEN the Console SHALL not block visible output
3. WHEN validating inputs THEN the Console SHALL provide immediate feedback on errors
4. WHEN starting research THEN the Console SHALL show activity indicator within 1 second of command execution
