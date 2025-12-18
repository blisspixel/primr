# Design Document: CLI UX Enhancement

## Overview

This design transforms Primr's CLI from functional output into a crafted experience. The goal is a CLI that feels like a premium instrument: every visual element earns its place, feedback is contextually appropriate, and the interface adapts gracefully to different terminals and use cases.

The design draws from established CLI UX patterns while addressing Primr's unique challenge: long-running operations (10-40 minutes) where user trust and attention management are critical.

## Architecture

### Component Structure

```
src/primr/utils/
├── console.py          # Core Console class (enhanced)
├── theme.py            # Visual theme and styling (new)
├── progress.py         # Progress indicators (new)
├── formatters.py       # Output formatters (new)
├── terminal.py         # Terminal capability detection (new)
└── output_modes.py     # Quiet/JSON/Verbose modes (new)
```

### Design Principles

1. **Progressive Disclosure**: Show minimal information by default, detail on demand
2. **Contextual Feedback**: Time displays, progress bars, and messages adapt to operation duration
3. **Visual Hierarchy**: Four distinct levels create scannable output
4. **Graceful Degradation**: Works in any terminal, from modern to dumb
5. **Machine-Friendly**: JSON and quiet modes for scripting

## Components and Interfaces

### Theme System

```python
@dataclass
class Theme:
    """Visual theme with terminal capability awareness."""
    
    # Status indicators (ASCII-safe)
    INDICATOR_ACTIVE: str = ">"
    INDICATOR_DONE: str = "+"
    INDICATOR_FAIL: str = "x"
    INDICATOR_WARN: str = "!"
    INDICATOR_INFO: str = "."
    INDICATOR_BULLET: str = "*"
    
    # Progress characters
    PROG_FILL: str = "#"
    PROG_EMPTY: str = "-"
    PROG_BRACKET_L: str = "["
    PROG_BRACKET_R: str = "]"
    
    # Box drawing (ASCII)
    LINE_H: str = "-"
    LINE_V: str = "|"
    CORNER: str = "+"
    
    # Semantic colors (ANSI codes, empty if no color)
    SUCCESS: str = "\033[32m"
    WARNING: str = "\033[33m"
    ERROR: str = "\033[31m"
    INFO: str = "\033[36m"
    MUTED: str = "\033[2m"
    BOLD: str = "\033[1m"
    RESET: str = "\033[0m"
    
    @classmethod
    def for_terminal(cls, supports_color: bool, supports_unicode: bool) -> "Theme":
        """Create theme appropriate for terminal capabilities."""
        theme = cls()
        if not supports_color:
            theme.SUCCESS = theme.WARNING = theme.ERROR = ""
            theme.INFO = theme.MUTED = theme.BOLD = theme.RESET = ""
        if supports_unicode:
            theme.INDICATOR_DONE = "✓"
            theme.INDICATOR_FAIL = "✗"
            theme.PROG_FILL = "█"
            theme.PROG_EMPTY = "░"
        return theme
```

### Terminal Capability Detection

```python
class TerminalCapabilities:
    """Detect and cache terminal capabilities."""
    
    supports_color: bool
    supports_unicode: bool
    supports_cursor: bool
    width: int
    is_interactive: bool
    
    @classmethod
    def detect(cls) -> "TerminalCapabilities":
        """Detect capabilities from environment."""
        caps = cls()
        
        # Color support
        caps.supports_color = (
            sys.stdout.isatty() and
            os.environ.get("NO_COLOR") is None and
            os.environ.get("TERM") != "dumb"
        )
        
        # Unicode support (conservative default)
        caps.supports_unicode = (
            sys.stdout.encoding and
            "utf" in sys.stdout.encoding.lower()
        )
        
        # Cursor movement (for in-place updates)
        caps.supports_cursor = (
            sys.stdout.isatty() and
            os.environ.get("TERM") != "dumb"
        )
        
        # Terminal width
        caps.width = shutil.get_terminal_size().columns
        
        # Interactive (not piped)
        caps.is_interactive = sys.stdout.isatty()
        
        return caps
```

### Visual Hierarchy Levels

```
Level 1: PHASE (bold, colored, with separators)
================================================
[1/3] Data Collection
  Website scraping and external source gathering
  Expected: 15-20 minutes
================================================

Level 2: STEP (indicator + text)
  > Scanning website

Level 3: DETAIL (indented, muted)
    . Found 23 pages
    . Extracting content

Level 4: RESULT (highlighted)
    + 23 pages scraped (2m 15s)
```

### Progress Display System

```python
class ProgressDisplay:
    """Unified progress display with contextual adaptation."""
    
    def __init__(self, console: Console):
        self.console = console
        self._start_time: float = 0
        self._last_update: float = 0
    
    def bounded(self, current: int, total: int, label: str = "") -> None:
        """Progress bar for operations with known bounds.
        
        Example: [################----] 16/20 Financial Overview (3m 12s)
        """
        pct = current / total if total > 0 else 0
        bar_width = 20
        filled = int(bar_width * pct)
        
        bar = (
            self.theme.PROG_BRACKET_L +
            self.theme.PROG_FILL * filled +
            self.theme.PROG_EMPTY * (bar_width - filled) +
            self.theme.PROG_BRACKET_R
        )
        
        elapsed = self._format_elapsed()
        eta = self._format_eta(pct) if pct > 0.1 else ""
        
        line = f"\r    {bar} {current}/{total}"
        if label:
            line += f" {self._truncate(label, 25)}"
        if elapsed:
            line += f" ({elapsed})"
        if eta:
            line += f" ETA: {eta}"
        
        self._write_in_place(line)
    
    def unbounded(self, message: str) -> None:
        """Spinner for operations with unknown bounds.
        
        Example: | Waiting for Deep Research API... (2m 45s)
        """
        frame = self._spinner_frame()
        elapsed = self._format_elapsed()
        
        line = f"\r    {frame} {message}"
        if elapsed:
            line += f" ({elapsed})"
        
        self._write_in_place(line)
    
    def _format_elapsed(self) -> str:
        """Format elapsed time contextually."""
        elapsed = time.time() - self._start_time
        if elapsed < 1:
            return ""
        elif elapsed < 60:
            return f"{int(elapsed)}s"
        elif elapsed < 3600:
            return f"{int(elapsed//60)}m {int(elapsed%60)}s"
        else:
            return f"{int(elapsed//3600)}h {int((elapsed%3600)//60)}m"
    
    def _format_eta(self, progress: float) -> str:
        """Estimate time remaining."""
        if progress <= 0:
            return ""
        elapsed = time.time() - self._start_time
        total_estimated = elapsed / progress
        remaining = total_estimated - elapsed
        if remaining < 60:
            return f"{int(remaining)}s"
        return f"{int(remaining//60)}m"
```

### Phase Orchestration

```python
class PhaseDisplay:
    """Display for multi-phase operations."""
    
    def __init__(self, console: Console, phases: list[PhaseInfo]):
        self.console = console
        self.phases = phases
        self.current_phase = 0
    
    def show_roadmap(self) -> None:
        """Display phase overview at start.
        
        Example:
        Research Plan
        -------------
        [1] Collect    15-20 min   Website + external sources
        [2] Analyze    10-15 min   AI analysis of content
        [3] Report      5-10 min   Document generation
        
        Total estimated: 30-45 minutes
        """
        self.console.blank()
        self.console.text("  Research Plan")
        self.console.divider()
        
        for i, phase in enumerate(self.phases, 1):
            status = ">" if i == self.current_phase + 1 else " "
            self.console.text(
                f"  {status}[{i}] {phase.name:<12} {phase.duration:<12} {phase.description}"
            )
        
        self.console.blank()
        total = self._sum_durations()
        self.console.text(f"  Total estimated: {total}")
        self.console.blank()
    
    def enter_phase(self, phase_num: int) -> None:
        """Display phase entry banner.
        
        Example:
        ================================================
        [1/3] Data Collection
          Website scraping and external source gathering
          Expected: 15-20 minutes
        ================================================
        """
        phase = self.phases[phase_num - 1]
        width = min(50, self.console.term_width - 4)
        
        self.console.blank()
        self.console.text(f"  {'=' * width}")
        self.console.text(f"  [{phase_num}/{len(self.phases)}] {phase.name}")
        self.console.text(f"    {phase.description}")
        self.console.text(f"    Expected: {phase.duration}")
        self.console.text(f"  {'=' * width}")
        self.console.blank()
    
    def complete_phase(self, stats: dict) -> None:
        """Display phase completion summary.
        
        Example:
        + Data Collection COMPLETE
          - Pages scraped: 23
          - External sources: 5
          - Duration: 14m 32s
        """
        phase = self.phases[self.current_phase]
        
        self.console.blank()
        self.console.text(f"  {self.theme.SUCCESS}+ {phase.name} COMPLETE{self.theme.RESET}")
        for key, value in stats.items():
            self.console.text(f"    {self.theme.MUTED}- {key}: {value}{self.theme.RESET}")
        self.console.blank()
        
        self.current_phase += 1
    
    def mini_roadmap(self) -> str:
        """Generate compact roadmap indicator.
        
        Example: [1] Collect > [2] Analyze > [ ] Report
        """
        parts = []
        for i, phase in enumerate(self.phases, 1):
            if i < self.current_phase + 1:
                parts.append(f"[{self.theme.SUCCESS}✓{self.theme.RESET}] {phase.short_name}")
            elif i == self.current_phase + 1:
                parts.append(f"[{self.theme.INFO}>{self.theme.RESET}] {phase.short_name}")
            else:
                parts.append(f"[ ] {phase.short_name}")
        return " > ".join(parts)
```

### Error Presentation

```python
class ErrorDisplay:
    """Rich error presentation with recovery guidance."""
    
    ERROR_GUIDANCE = {
        "api_key_missing": {
            "title": "API Key Not Configured",
            "fix": "Add GEMINI_API_KEY to your .env file",
            "command": "echo 'GEMINI_API_KEY=your_key' >> .env"
        },
        "network_timeout": {
            "title": "Network Timeout",
            "fix": "Check your internet connection and try again",
            "retry": True
        },
        "rate_limit": {
            "title": "API Rate Limit Exceeded",
            "fix": "Wait a few minutes before retrying",
            "wait_time": "5 minutes"
        },
        # ... more error types
    }
    
    def show_error(self, error_type: str, details: str = "") -> None:
        """Display error with recovery guidance.
        
        Example:
        +--------------------------------------------------+
        | x ERROR: API Key Not Configured                  |
        +--------------------------------------------------+
        |                                                  |
        | GEMINI_API_KEY environment variable is not set.  |
        |                                                  |
        | To fix:                                          |
        |   1. Get an API key from Google AI Studio        |
        |   2. Add to .env: GEMINI_API_KEY=your_key        |
        |                                                  |
        | Or run: echo 'GEMINI_API_KEY=...' >> .env        |
        +--------------------------------------------------+
        """
        guidance = self.ERROR_GUIDANCE.get(error_type, {})
        width = min(50, self.console.term_width - 4)
        
        self.console.blank()
        self._box_top(width)
        self._box_line(f"x ERROR: {guidance.get('title', error_type)}", width)
        self._box_separator(width)
        self._box_line("", width)
        
        if details:
            for line in self._wrap(details, width - 4):
                self._box_line(line, width)
            self._box_line("", width)
        
        if "fix" in guidance:
            self._box_line("To fix:", width)
            self._box_line(f"  {guidance['fix']}", width)
            self._box_line("", width)
        
        if "command" in guidance:
            self._box_line(f"Or run: {guidance['command']}", width)
        
        self._box_bottom(width)
        self.console.blank()
    
    def show_grouped_errors(self, errors: list[tuple[str, str]]) -> None:
        """Display multiple errors grouped by category."""
        by_category = defaultdict(list)
        for error_type, detail in errors:
            category = error_type.split("_")[0]
            by_category[category].append((error_type, detail))
        
        for category, group in by_category.items():
            self.console.text(f"  {self.theme.ERROR}x {category.title()} Errors ({len(group)}){self.theme.RESET}")
            for error_type, detail in group:
                self.console.text(f"    - {detail}")
```

### Final Output Presentation

```python
class CompletionDisplay:
    """Success presentation that rewards the wait."""
    
    def show_success(self, company: str, outputs: list[OutputFile], stats: dict) -> None:
        """Display completion with full summary.
        
        Example:
        ================================================
        + Research Complete: Acme Corporation
        ================================================
        
        Output Files:
          DOCX   Acme_Corporation_Overview.docx     2.4 MB
          PDF    Acme_Corporation_Overview.pdf      1.8 MB
          TXT    Acme_Corporation_Overview.txt      156 KB
        
        Summary:
          Duration        32m 15s
          Pages scraped   47
          Sections        18
          Est. cost       $0.45
          Actual cost     $0.38
        
        Full path: C:\\Users\\...\\output\\Acme_Corporation_Overview.docx
        """
        width = min(50, self.console.term_width - 4)
        
        # Success banner
        self.console.blank()
        self.console.text(f"  {'=' * width}")
        self.console.text(f"  {self.theme.SUCCESS}+ Research Complete: {company}{self.theme.RESET}")
        self.console.text(f"  {'=' * width}")
        self.console.blank()
        
        # Output files
        self.console.text("  Output Files:")
        for output in outputs:
            size = self._format_size(output.size)
            self.console.text(f"    {output.type:<6} {output.name:<40} {size:>8}")
        self.console.blank()
        
        # Summary table
        self.console.text("  Summary:")
        max_label = max(len(k) for k in stats.keys())
        for label, value in stats.items():
            self.console.text(f"    {label:<{max_label}}  {value}")
        
        # Cost variance note if significant
        if "est_cost" in stats and "actual_cost" in stats:
            est = float(stats["est_cost"].replace("$", ""))
            actual = float(stats["actual_cost"].replace("$", ""))
            if actual > est * 1.2:
                self.console.blank()
                self.console.text(f"    {self.theme.WARNING}! Cost exceeded estimate due to additional API calls{self.theme.RESET}")
        
        self.console.blank()
        
        # Full path for easy copy
        if outputs:
            self.console.text(f"  Full path: {outputs[0].full_path}")
        self.console.blank()
```

### Doctor Command Display

```python
class DoctorDisplay:
    """Diagnostic dashboard for system checks."""
    
    def show_header(self, version: str) -> None:
        """Display doctor header with system info.
        
        Example:
        Primr Doctor
        ============
        Version: 1.0.0
        Python:  3.10.12
        OS:      Windows 11
        """
        self.console.blank()
        self.console.text("  Primr Doctor")
        self.console.divider()
        self.console.text(f"  Version: {version}")
        self.console.text(f"  Python:  {sys.version.split()[0]}")
        self.console.text(f"  OS:      {platform.system()} {platform.release()}")
        self.console.blank()
    
    def show_check(self, name: str, status: str, detail: str = "", fix: str = "") -> None:
        """Display individual check result.
        
        Example:
        [pass] GEMINI_API_KEY          Configured
        [FAIL] SEARCH_API_KEY          Not set
               Fix: Add SEARCH_API_KEY=... to .env
        """
        indicator = {
            "pass": f"{self.theme.SUCCESS}pass{self.theme.RESET}",
            "warn": f"{self.theme.WARNING}warn{self.theme.RESET}",
            "fail": f"{self.theme.ERROR}FAIL{self.theme.RESET}",
        }.get(status, status)
        
        self.console.text(f"  [{indicator}] {name:<24} {detail}")
        
        if fix and status in ("warn", "fail"):
            self.console.text(f"         Fix: {fix}")
    
    def show_summary(self, passed: int, warned: int, failed: int) -> None:
        """Display final summary.
        
        Example:
        ============
        All systems ready. Run: primr "Company" https://company.com
        
        Or with warnings:
        ============
        6 passed, 2 warnings, 0 failed
        Some features may be limited. See warnings above.
        """
        self.console.divider()
        
        if failed == 0 and warned == 0:
            self.console.text(f"  {self.theme.SUCCESS}All systems ready.{self.theme.RESET}")
            self.console.text('  Run: primr "Company" https://company.com')
        elif failed == 0:
            self.console.text(f"  {passed} passed, {warned} warnings")
            self.console.text("  Some features may be limited. See warnings above.")
        else:
            self.console.text(f"  {self.theme.ERROR}{passed} passed, {warned} warnings, {failed} failed{self.theme.RESET}")
            self.console.text("  Fix failed checks before running research.")
        
        self.console.blank()
```

### Output Modes

```python
class OutputMode(Enum):
    NORMAL = "normal"
    QUIET = "quiet"
    JSON = "json"
    VERBOSE = "verbose"

class OutputRouter:
    """Route output based on mode."""
    
    def __init__(self, mode: OutputMode):
        self.mode = mode
        self._json_buffer = {}
    
    def info(self, msg: str) -> None:
        if self.mode == OutputMode.QUIET:
            return
        if self.mode == OutputMode.JSON:
            return
        print(msg)
    
    def error(self, msg: str, error_type: str = "unknown") -> None:
        if self.mode == OutputMode.JSON:
            self._json_buffer.setdefault("errors", []).append({
                "type": error_type,
                "message": msg
            })
            return
        # Always show errors in other modes
        print(f"  x {msg}")
    
    def result(self, key: str, value: Any) -> None:
        if self.mode == OutputMode.JSON:
            self._json_buffer[key] = value
            return
        if self.mode == OutputMode.QUIET:
            if key in ("output_path", "error"):
                print(value)
            return
        print(f"  {key}: {value}")
    
    def finalize(self) -> None:
        if self.mode == OutputMode.JSON:
            print(json.dumps(self._json_buffer, indent=2))
```

## Data Models

```python
@dataclass
class PhaseInfo:
    """Information about a research phase."""
    name: str
    short_name: str
    description: str
    duration: str  # e.g., "15-20 min"
    
@dataclass
class OutputFile:
    """Information about an output file."""
    type: str  # DOCX, PDF, TXT
    name: str
    full_path: str
    size: int  # bytes

@dataclass
class CheckResult:
    """Result of a doctor check."""
    name: str
    status: Literal["pass", "warn", "fail"]
    detail: str
    fix: str | None = None

@dataclass
class ResearchStats:
    """Statistics from a research run."""
    duration_seconds: float
    pages_scraped: int
    external_sources: int
    sections_generated: int
    estimated_cost: float
    actual_cost: float
    warnings: list[str]
    errors: list[str]
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Visual Hierarchy Consistency
*For any* output message at a given hierarchy level (phase, step, detail, result), the output SHALL contain the correct indentation and styling for that level.
**Validates: Requirements 1.1, 1.3**

### Property 2: Symbol Vocabulary Consistency
*For any* status type (active, done, fail, warn, info), the displayed indicator SHALL match the defined symbol for that status type.
**Validates: Requirements 1.4**

### Property 3: Terminal Width Respect
*For any* terminal width W and any output line, the visible character count of that line SHALL not exceed W.
**Validates: Requirements 1.5, 15.2**

### Property 4: Progress Bar Rendering
*For any* current value C and total value T where 0 <= C <= T, the progress bar SHALL display filled portion proportional to C/T.
**Validates: Requirements 2.1**

### Property 5: Time Display Thresholds
*For any* operation duration D: if D < 1s, no time is shown; if 1s <= D < 10s, time shown on completion only; if D >= 10s, live time is shown.
**Validates: Requirements 2.5, 4.1, 4.2, 4.3**

### Property 6: Adaptive Time Formatting
*For any* duration D in seconds, the formatted string SHALL use: seconds for D < 60, "Xm Ys" for 60 <= D < 3600, "Xh Ym" for D >= 3600.
**Validates: Requirements 4.4**

### Property 7: Phase Header Completeness
*For any* phase entry, the header SHALL contain: phase number, total phases, phase name, description, and expected duration.
**Validates: Requirements 3.2**

### Property 8: Phase Summary Completeness
*For any* phase completion, the summary SHALL contain: phase name, completion indicator, and actual duration.
**Validates: Requirements 3.3**

### Property 9: Roadmap Indicator Generation
*For any* current phase index I and total phases N, the roadmap SHALL show completed phases (< I) with done indicator, current phase (= I) with active indicator, and future phases (> I) with empty indicator.
**Validates: Requirements 3.4**

### Property 10: Error Presentation Completeness
*For any* error with known type, the error display SHALL include: error type, description, and at least one recovery suggestion.
**Validates: Requirements 5.2**

### Property 11: Error Grouping
*For any* list of errors with multiple categories, the grouped display SHALL organize errors by category with counts.
**Validates: Requirements 5.6**

### Property 12: Status Styling Consistency
*For any* status type (success, warning, error), the output SHALL contain the appropriate color code when colors are enabled, and no color codes when colors are disabled.
**Validates: Requirements 5.1, 6.1, 15.1, 15.3, 15.5**

### Property 13: File Output Formatting
*For any* list of output files, each file SHALL be displayed on its own line with type, name, and human-readable size.
**Validates: Requirements 7.2, 7.3**

### Property 14: Completion Summary Completeness
*For any* successful research completion, the summary SHALL contain: duration, pages scraped, sections generated, estimated cost, and actual cost.
**Validates: Requirements 7.4**

### Property 15: Cost Variance Explanation
*For any* completion where actual cost exceeds estimated cost by more than 20%, the output SHALL include an explanation.
**Validates: Requirements 7.5, 10.4**

### Property 16: Check Result Formatting
*For any* doctor check, the output SHALL contain: status indicator, check name, and detail, with consistent column alignment across all checks.
**Validates: Requirements 8.2, 8.6**

### Property 17: Failed Check Fix Display
*For any* failed doctor check with a known fix, the output SHALL include the specific fix command or instruction.
**Validates: Requirements 8.3**

### Property 18: Batch Status Line Completeness
*For any* company in batch mode, the status line SHALL contain: company name, status (queued/running/done/failed), and duration when applicable.
**Validates: Requirements 9.2**

### Property 19: Batch Summary Completeness
*For any* batch completion, the summary SHALL contain: total succeeded, total failed, total duration, and total cost.
**Validates: Requirements 9.4**

### Property 20: Cost Estimate Completeness
*For any* cost estimate display, the output SHALL contain: component breakdown and min-max range.
**Validates: Requirements 10.1, 10.2**

### Property 21: Confirmation Prompt Completeness
*For any* confirmation prompt, the display SHALL contain: company name, research mode, estimated duration, and estimated cost.
**Validates: Requirements 11.1**

### Property 22: Help Command Grouping
*For any* help display, commands SHALL be organized into logical groups with group headers.
**Validates: Requirements 12.1**

### Property 23: Help Example Presence
*For any* command in help output, at least one usage example SHALL be present.
**Validates: Requirements 12.2**

### Property 24: Help Default Value Display
*For any* option with a default value, the help output SHALL show the default in brackets.
**Validates: Requirements 12.3**

### Property 25: Command Suggestion
*For any* invalid command that is similar to a valid command (edit distance <= 2), the output SHALL suggest the valid command.
**Validates: Requirements 12.5**

### Property 26: Quiet Mode Filtering
*For any* output in quiet mode, only errors and final output paths SHALL be displayed; all other output SHALL be suppressed.
**Validates: Requirements 13.1**

### Property 27: JSON Output Structure
*For any* JSON mode output, the result SHALL be valid JSON containing at minimum: status, duration, and output_files fields.
**Validates: Requirements 13.2**

### Property 28: JSON Formatting Purity
*For any* JSON mode output, the result SHALL not contain ANSI color codes or decorative ASCII characters.
**Validates: Requirements 13.3**

### Property 29: Cancellation Output Completeness
*For any* cancelled operation, the output SHALL list what was completed and what partial outputs were saved.
**Validates: Requirements 14.3, 14.4**

### Property 30: Color Adaptation
*For any* terminal where NO_COLOR is set OR output is piped OR TERM=dumb, the output SHALL not contain ANSI color codes.
**Validates: Requirements 15.1, 15.3, 15.5**

## Error Handling

### Error Categories

1. **Configuration Errors**: Missing API keys, invalid settings
   - Display: Boxed error with exact fix command
   - Recovery: Show config file location and required format

2. **Network Errors**: Timeouts, connection failures
   - Display: Error with retry suggestion
   - Recovery: Offer automatic retry with backoff

3. **API Errors**: Rate limits, quota exceeded, invalid responses
   - Display: Error with wait time or quota info
   - Recovery: Show quota check command

4. **File Errors**: Permission denied, disk full
   - Display: Error with path and permission info
   - Recovery: Suggest alternative paths or cleanup

### Graceful Degradation

When non-critical components fail:
1. Log warning but continue
2. Note degraded sections in output
3. Summarize warnings at phase end
4. Include warning count in final summary

## Testing Strategy

### Unit Testing

Unit tests verify specific formatting functions:
- Time formatting edge cases (0s, 59s, 60s, 3599s, 3600s)
- Progress bar rendering at boundaries (0%, 50%, 100%)
- Text truncation with various widths
- Color code stripping for no-color mode

### Property-Based Testing

Property tests use Hypothesis to verify universal properties:
- **Framework**: Hypothesis (Python)
- **Minimum iterations**: 100 per property
- **Tag format**: `**Feature: cli-ux-enhancement, Property {N}: {description}**`

Each correctness property from the design is implemented as a property-based test that generates random inputs and verifies the property holds.

Example test structure:
```python
from hypothesis import given, strategies as st

@given(st.integers(min_value=0, max_value=10000))
def test_time_formatting_adaptive(duration_seconds):
    """
    **Feature: cli-ux-enhancement, Property 6: Adaptive Time Formatting**
    **Validates: Requirements 4.4**
    """
    result = format_time(duration_seconds)
    
    if duration_seconds < 60:
        assert "m" not in result or duration_seconds == 0
    elif duration_seconds < 3600:
        assert "m" in result and "h" not in result
    else:
        assert "h" in result
```

### Integration Testing

Integration tests verify end-to-end flows:
- Full research run with mocked API
- Doctor command with various configurations
- Batch mode with success and failure cases
- Interrupt handling with Ctrl+C simulation
