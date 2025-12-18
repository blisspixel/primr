# PhD-Level Code Review: Automated Company Researcher

**Review Date:** December 12, 2025  
**Reviewer:** Kiro AI  
**Scope:** Full codebase architecture, patterns, security, performance, maintainability

---

## Executive Summary

This is a sophisticated AI-powered research automation tool with impressive scraping capabilities. However, it has significant architectural debt, inconsistent patterns, and several critical issues that will cause problems at scale. The code works but is fragile.

**Overall Grade: C+** (Functional but needs significant refactoring)

---

## 1. CRITICAL ISSUES (Fix Immediately)

### 1.1 Global Mutable State Everywhere

**Location:** `scrape.py`, `llm.py`, `config.py`

```python
# scrape.py - Global browser instance
_PLAYWRIGHT = None
_BROWSER = None
_SCRAPE_CACHE = {}

# llm.py - Global client
client = genai.Client(api_key=GEMINI_API_KEY)
```

**Problem:** 
- Not thread-safe - will corrupt state in concurrent scenarios
- Memory leaks - browser instances may not be cleaned up
- Testing nightmare - can't isolate tests without side effects
- No connection pooling strategy

**Fix:**
```python
# Use a proper singleton with thread safety
from threading import Lock
from contextlib import contextmanager

class BrowserPool:
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._browsers = []
                    cls._instance._playwright = None
        return cls._instance
    
    @contextmanager
    def get_browser(self):
        """Thread-safe browser acquisition with automatic cleanup."""
        browser = self._acquire()
        try:
            yield browser
        finally:
            self._release(browser)
```

### 1.2 Silent Exception Swallowing

**Location:** Throughout codebase

```python
# research_agent.py line ~180
except:
    pass

# scrape.py - multiple locations
except:
    pass

# output_utils.py
except Exception as e:
    print(Fore.RED + f"[ERROR] ..." + Style.RESET_ALL)
    # Then continues execution!
```

**Problem:**
- Bugs are hidden, not fixed
- Impossible to debug production issues
- Data corruption goes unnoticed
- Violates fail-fast principle

**Fix:**
```python
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def scrape_with_requests(url: str, timeout: int = 15) -> Tuple[Optional[str], Optional[str]]:
    """
    Scrape URL with requests library.
    
    Returns:
        Tuple of (content, error_message). One will always be None.
    """
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        # ... processing
        return text, None
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP error scraping {url}: {e.response.status_code}")
        return None, f"HTTP {e.response.status_code}"
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout scraping {url}")
        return None, "Timeout"
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}", exc_info=True)
        return None, str(e)[:100]
```

### 1.3 API Key Validation at Import Time

**Location:** `config.py`

```python
if not GEMINI_API_KEY:
    raise ValueError("[ERROR] Missing Gemini API Key in .env")
```

**Problem:**
- Can't import module for testing without valid API keys
- Can't run any code path that doesn't need the API
- Breaks CI/CD pipelines
- Makes mocking impossible

**Fix:**
```python
# Lazy validation - only when actually needed
class Config:
    _gemini_key: Optional[str] = None
    
    @property
    def gemini_api_key(self) -> str:
        if self._gemini_key is None:
            self._gemini_key = os.getenv("GEMINI_API_KEY")
        if not self._gemini_key:
            raise ConfigurationError(
                "GEMINI_API_KEY not set. Set it in .env or environment."
            )
        return self._gemini_key

config = Config()
```

### 1.4 Hardcoded Model Names

**Location:** `config.py`, `insights_extractor.py`

```python
AI_RESEARCH_MODEL = "gemini-3-pro-preview"  # Will break when model is deprecated
```

**Problem:**
- Model names change frequently
- No fallback strategy
- Different environments may need different models

**Fix:**
```python
# config.py
AI_MODELS = {
    "research": os.getenv("AI_RESEARCH_MODEL", "gemini-2.0-flash"),
    "report": os.getenv("AI_REPORT_MODEL", "gemini-2.0-flash"),
    "fast": os.getenv("AI_FAST_MODEL", "gemini-2.0-flash"),
}

MODEL_FALLBACKS = {
    "gemini-3-pro-preview": ["gemini-2.5-pro", "gemini-2.0-flash"],
}
```

---

## 2. ARCHITECTURAL ISSUES

### 2.1 Inconsistent AI Client Usage

**Problem:** Two different Google AI SDKs are used:

```python
# llm.py - Modern SDK
from google import genai
client = genai.Client(api_key=GEMINI_API_KEY)

# insights_extractor.py - Legacy SDK
import google.generativeai as genai
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(AI_RESEARCH_MODEL)
```

**Impact:**
- Different error handling
- Different response formats
- Maintenance burden
- Potential version conflicts

**Fix:** Standardize on ONE SDK (the modern `google.genai`):

```python
# ai/client.py - Single source of truth
from google import genai
from google.genai import types
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class AIClient:
    """Unified AI client for all LLM operations."""
    
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)
    
    def generate(
        self,
        prompt: str,
        model: str = "gemini-2.0-flash",
        temperature: float = 1.0,
        thinking_level: str = "high",
        max_retries: int = 3
    ) -> str:
        """Generate content with automatic retries and error handling."""
        config = types.GenerateContentConfig(
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level)
        )
        
        for attempt in range(max_retries):
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
                return response.text.strip()
            except Exception as e:
                logger.warning(f"AI call failed (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
```

### 2.2 No Dependency Injection

**Problem:** Hard dependencies everywhere make testing and configuration changes difficult.

```python
# research_agent.py
from company_researcher.data.scrape import fetch_web_content  # Hard import
from company_researcher.ai.llm import llm  # Hard import
```

**Fix:** Use dependency injection:

```python
# research_agent.py
from dataclasses import dataclass
from typing import Protocol, Callable

class Scraper(Protocol):
    def fetch(self, url: str, company: str, max_pages: int) -> dict: ...

class LLMClient(Protocol):
    def generate(self, prompt: str, model_type: str) -> str: ...

@dataclass
class ResearchDependencies:
    scraper: Scraper
    llm: LLMClient
    search: Callable
    
class ResearchAgent:
    def __init__(self, deps: ResearchDependencies):
        self.deps = deps
    
    def perform_research(self, company_name: str, website: str) -> None:
        # Now fully testable with mocks
        scraped = self.deps.scraper.fetch(website, company_name, 15)
```

### 2.3 Circular Import Risk

**Problem:** The import structure creates fragile dependencies:

```
config.py <- llm.py <- scrape.py <- research_agent.py
     ^                                      |
     +--------------------------------------+
```

If `config.py` ever imports from another module that imports `llm.py`, you get a circular import.

**Fix:** Create a clear dependency hierarchy:

```
Layer 0: config/ (no internal imports)
Layer 1: utils/ (imports only config)
Layer 2: ai/ (imports config, utils)
Layer 3: data/ (imports config, utils, ai)
Layer 4: output/ (imports config, utils)
Layer 5: core/ (imports everything)
```

---

## 3. CODE QUALITY ISSUES

### 3.1 Duplicated Output Functions

**Problem:** CLI output functions are duplicated across files:

```python
# research_agent.py
def out(msg): print(msg); sys.stdout.flush()
def out_step(msg): out(f"\n{C_CYAN}>{RESET} {msg}")
def out_ok(msg): out(f"  {C_GREEN}+{RESET} {msg}")

# scrape.py - SAME FUNCTIONS COPY-PASTED
def out(msg, end="\n"): print(msg, end=end); sys.stdout.flush()
def out_step(msg): ...
def out_ok(msg, show_time=True): ...  # Slightly different signature!
```

**Fix:** Create a single output module:

```python
# utils/output.py
import sys
from enum import Enum
from colorama import Fore, Style
from contextlib import contextmanager
import time

class OutputLevel(Enum):
    STEP = "step"
    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    INFO = "info"

class ConsoleOutput:
    """Unified console output with consistent formatting."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._step_start: float = 0
    
    def step(self, msg: str) -> None:
        self._step_start = time.time()
        print(f"\n{Fore.CYAN}>{Style.RESET_ALL} {msg}")
        sys.stdout.flush()
    
    def ok(self, msg: str, show_time: bool = True) -> None:
        time_str = ""
        if show_time and self._step_start:
            elapsed = time.time() - self._step_start
            if elapsed >= 1:
                time_str = f" {Style.DIM}({elapsed:.1f}s){Style.RESET_ALL}"
        print(f"  {Fore.GREEN}+{Style.RESET_ALL} {msg}{time_str}")
        sys.stdout.flush()
    
    @contextmanager
    def progress(self, total: int, desc: str = ""):
        """Context manager for progress tracking."""
        # Implementation
        yield progress_updater

# Global instance (or inject it)
console = ConsoleOutput()
```

### 3.2 Magic Numbers and Strings

**Problem:** Hardcoded values scattered throughout:

```python
# scrape.py
if len(html_content) > 500:  # Why 500?
if len(text.strip()) < 100:  # Why 100?
DISK_CACHE_TTL_HOURS = 24  # Should be configurable

# grading_agent.py
if score < GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT:  # Good - uses config
```

**Fix:** Centralize all thresholds:

```python
# config/thresholds.py
from dataclasses import dataclass

@dataclass(frozen=True)
class ScrapingThresholds:
    min_html_length: int = 500
    min_content_length: int = 100
    cache_ttl_hours: int = 24
    max_url_length: int = 2000
    soft_block_min_length: int = 100

@dataclass(frozen=True)
class AIThresholds:
    min_summary_length: int = 200
    grade_refinement_threshold: int = 80
    max_prompt_length: int = 100000

SCRAPING = ScrapingThresholds()
AI = AIThresholds()
```

### 3.3 No Type Hints

**Problem:** Most functions lack type hints, making the code harder to understand and maintain.

```python
# Current
def scrape_page(url, silent=False, pbar=None, use_vision=False):
    ...

# Should be
from typing import Optional, Tuple, Any
from tqdm import tqdm

def scrape_page(
    url: str,
    silent: bool = False,
    pbar: Optional[tqdm] = None,
    use_vision: bool = False
) -> Tuple[Optional[str], Optional[str]]:
    """
    Scrape a single page using tiered fallback strategy.
    
    Args:
        url: The URL to scrape
        silent: Suppress console output
        pbar: Optional progress bar to update
        use_vision: Enable vision-based extraction as final fallback
    
    Returns:
        Tuple of (content, method_used). Content is None if all methods fail.
    """
```

---

## 4. SECURITY ISSUES

### 4.1 Temp Files with Predictable Names

**Location:** `scrape.py`

```python
temp_file = f"temp_{random.randint(1000,9999)}.pdf"  # Predictable!
pdf_path = f"temp_vision_{random.randint(10000, 99999)}.pdf"
```

**Problem:**
- Race condition vulnerability
- Files left behind on crash
- Predictable names enable attacks

**Fix:**
```python
import tempfile
from contextlib import contextmanager

@contextmanager
def secure_temp_file(suffix: str = ".pdf"):
    """Create a secure temporary file that's automatically cleaned up."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        os.close(fd)  # Close the file descriptor
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

# Usage
with secure_temp_file(".pdf") as pdf_path:
    page.pdf(path=pdf_path)
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
```

### 4.2 No Input Sanitization for File Paths

**Location:** `output_utils.py`, `research_agent.py`

```python
folder_name = company_name.replace(" ", "_")  # What about "../../../etc/passwd"?
folder_path = os.path.join(WORKING_DIR, folder_name)
```

**Fix:**
```python
import re
from pathlib import Path

def sanitize_company_name(name: str) -> str:
    """Sanitize company name for safe filesystem use."""
    # Remove any path traversal attempts
    name = name.replace("..", "").replace("/", "").replace("\\", "")
    # Keep only safe characters
    name = re.sub(r'[^\w\s\-]', '', name)
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    # Limit length
    return name[:100] if name else "unknown_company"

def get_company_folder(company_name: str) -> Path:
    """Get safe folder path for company data."""
    safe_name = sanitize_company_name(company_name)
    folder = Path(WORKING_DIR) / safe_name
    # Verify it's still under WORKING_DIR (defense in depth)
    folder = folder.resolve()
    if not str(folder).startswith(str(Path(WORKING_DIR).resolve())):
        raise ValueError(f"Invalid company name: {company_name}")
    return folder
```

### 4.3 Logging Sensitive Data

**Location:** `chat_logger.py`

```python
chat_history.append({
    "timestamp": datetime.now().isoformat(),
    "prompt": prompt,  # May contain company secrets!
    "response": response  # May contain PII!
})
```

**Fix:**
```python
import hashlib

def redact_sensitive(text: str) -> str:
    """Redact potentially sensitive information from logs."""
    # Redact emails
    text = re.sub(r'\b[\w.-]+@[\w.-]+\.\w+\b', '[EMAIL]', text)
    # Redact phone numbers
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', text)
    # Redact SSN patterns
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)
    return text

def log_chat_interaction(prompt: str, response: str, session_id: str = "general"):
    """Log AI interaction with sensitive data redaction."""
    # Only log in debug mode or with explicit consent
    if not os.getenv("ENABLE_CHAT_LOGGING", "false").lower() == "true":
        return
    
    chat_history.append({
        "timestamp": datetime.now().isoformat(),
        "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()[:16],
        "prompt_preview": redact_sensitive(prompt[:200]) + "...",
        "response_length": len(response),
    })
```

---

## 5. PERFORMANCE ISSUES

### 5.1 No Connection Pooling

**Problem:** Each request creates a new connection:

```python
response = requests.get(url, headers=headers, timeout=timeout)
```

**Fix:**
```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class ConnectionPool:
    _session: Optional[requests.Session] = None
    
    @classmethod
    def get_session(cls) -> requests.Session:
        if cls._session is None:
            cls._session = requests.Session()
            retry = Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[500, 502, 503, 504]
            )
            adapter = HTTPAdapter(
                pool_connections=10,
                pool_maxsize=20,
                max_retries=retry
            )
            cls._session.mount("http://", adapter)
            cls._session.mount("https://", adapter)
        return cls._session
```

### 5.2 Synchronous Scraping

**Problem:** Pages are scraped sequentially:

```python
for i, page_url in enumerate(pages_to_scrape):
    page_text, method = scrape_page(page_url)  # Blocking!
```

**Fix:** Use async or thread pool:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict

def fetch_web_content_parallel(
    pages: list[str],
    max_workers: int = 5
) -> Dict[str, str]:
    """Scrape multiple pages in parallel."""
    results = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(scrape_page, url): url 
            for url in pages
        }
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                content, method = future.result(timeout=60)
                if content:
                    results[url] = content
            except Exception as e:
                logger.warning(f"Failed to scrape {url}: {e}")
    
    return results
```

### 5.3 Inefficient Cache Implementation

**Problem:** Cache checks disk on every call:

```python
def get_cached_content(url):
    key = get_cache_key(url)
    if key in _SCRAPE_CACHE:  # Memory check
        return _SCRAPE_CACHE[key]
    # Then disk check - EVERY TIME even if we know it's not there
    cache_file = os.path.join(CACHE_DIR, f"{key}.txt")
```

**Fix:**
```python
from functools import lru_cache
from typing import Optional
import sqlite3

class ContentCache:
    """Efficient content cache with SQLite backend."""
    
    def __init__(self, db_path: str, ttl_hours: int = 24):
        self.db_path = db_path
        self.ttl_hours = ttl_hours
        self._memory_cache: Dict[str, str] = {}
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON cache(created_at)")
    
    def get(self, url: str) -> Optional[str]:
        key = hashlib.md5(url.encode()).hexdigest()
        
        # L1: Memory
        if key in self._memory_cache:
            return self._memory_cache[key]
        
        # L2: SQLite
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT content FROM cache WHERE url_hash = ? AND created_at > datetime('now', ?)",
                (key, f'-{self.ttl_hours} hours')
            ).fetchone()
            
            if row:
                self._memory_cache[key] = row[0]
                return row[0]
        
        return None
```

---

## 6. TESTING GAPS

### 6.1 No Unit Tests for Core Logic

**Missing tests for:**
- `research_section()` - the core research logic
- `generate_initial_overview()` - overview generation
- `grade_report()` - grading logic
- `extract_insights()` - insight extraction

### 6.2 Integration Tests Mock at Wrong Level

**Current:** Mocking internal functions
**Better:** Mock at the HTTP/API boundary

```python
# Better approach - mock the HTTP layer
import responses

@responses.activate
def test_scrape_with_requests_success():
    responses.add(
        responses.GET,
        "https://example.com",
        body="<html><body><p>Test content</p></body></html>",
        status=200
    )
    
    text, error = scrape_with_requests("https://example.com")
    
    assert error is None
    assert "Test content" in text
```

### 6.3 No Property-Based Tests for Parsing

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=100, max_size=10000))
def test_extract_clean_text_never_crashes(html_content):
    """Property: extract_clean_text should never raise on any input."""
    soup = BeautifulSoup(f"<html><body>{html_content}</body></html>", "html.parser")
    result = extract_clean_text(soup)
    assert isinstance(result, str)

@given(st.text())
def test_sanitize_company_name_always_safe(name):
    """Property: sanitized names should always be filesystem-safe."""
    safe = sanitize_company_name(name)
    assert "/" not in safe
    assert "\\" not in safe
    assert ".." not in safe
    assert len(safe) <= 100
```

---

## 7. DOCUMENTATION ISSUES

### 7.1 No API Documentation

The code lacks docstrings explaining:
- What each function does
- What parameters mean
- What exceptions can be raised
- What the return values represent

### 7.2 No Architecture Documentation

Missing:
- System architecture diagram
- Data flow documentation
- Configuration guide
- Deployment guide

---

## 8. RECOMMENDED REFACTORING PRIORITY

### Phase 1: Critical Fixes (1-2 days)
1. Fix silent exception swallowing
2. Add proper logging
3. Fix temp file security
4. Standardize on one AI SDK

### Phase 2: Architecture (3-5 days)
1. Create unified output module
2. Implement dependency injection
3. Add type hints throughout
4. Create proper configuration class

### Phase 3: Performance (2-3 days)
1. Implement connection pooling
2. Add parallel scraping
3. Improve cache implementation

### Phase 4: Testing (3-5 days)
1. Add unit tests for core logic
2. Add property-based tests
3. Fix integration test mocking
4. Add CI/CD pipeline

### Phase 5: Documentation (1-2 days)
1. Add comprehensive docstrings
2. Create architecture documentation
3. Write deployment guide

---

## 9. QUICK WINS (Do Today)

1. **Add `py.typed` marker** for type checking:
   ```
   touch src/company_researcher/py.typed
   ```

2. **Add logging configuration**:
   ```python
   # __init__.py
   import logging
   logging.getLogger(__name__).addHandler(logging.NullHandler())
   ```

3. **Fix the bare `except:` clauses** - search and replace with specific exceptions

4. **Add `.gitignore` entries** for temp files:
   ```
   temp_*.pdf
   *.pyc
   __pycache__/
   logs/
   ```

5. **Create `requirements-dev.txt`**:
   ```
   pytest>=7.0
   pytest-cov
   hypothesis
   responses
   mypy
   black
   ruff
   ```

---

## Conclusion

This codebase has good bones - the scraping strategy is sophisticated, the AI integration is modern, and the overall flow makes sense. However, it needs significant hardening before production use. The main issues are:

1. **Reliability:** Silent failures hide bugs
2. **Security:** Temp files and path handling need work
3. **Testability:** Global state makes testing hard
4. **Maintainability:** Duplicated code and inconsistent patterns

Focus on Phase 1 fixes first - they'll have the biggest impact on reliability.
