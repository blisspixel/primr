# Refactoring Action Plan

## Immediate Actions (Do This Week)

### 1. Create Unified Output Module

**File:** `src/company_researcher/utils/console.py`

```python
"""Unified console output with consistent formatting."""
import sys
import time
from enum import Enum
from typing import Optional, Iterator
from contextlib import contextmanager
from colorama import Fore, Style, init

init()

class Console:
    """Thread-safe console output with timing and progress tracking."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._step_start: float = 0
        self._symbols = {
            "arrow": ">",
            "check": "+", 
            "cross": "x",
            "warn": "!",
        }
    
    def step(self, msg: str) -> None:
        """Start a new step with timing."""
        self._step_start = time.time()
        self._print(f"\n{Fore.CYAN}{self._symbols['arrow']}{Style.RESET_ALL} {msg}")
    
    def ok(self, msg: str, show_time: bool = True) -> None:
        """Success message with optional timing."""
        time_str = self._get_time_str() if show_time else ""
        self._print(f"  {Fore.GREEN}{self._symbols['check']}{Style.RESET_ALL} {msg}{time_str}")
    
    def warn(self, msg: str) -> None:
        """Warning message."""
        self._print(f"  {Fore.YELLOW}{self._symbols['warn']}{Style.RESET_ALL} {msg}")
    
    def error(self, msg: str) -> None:
        """Error message."""
        self._print(f"  {Fore.RED}{self._symbols['cross']}{Style.RESET_ALL} {msg}")
    
    def info(self, msg: str) -> None:
        """Dim info message."""
        self._print(f"  {Style.DIM}{msg}{Style.RESET_ALL}")
    
    def debug(self, msg: str) -> None:
        """Debug message (only in verbose mode)."""
        if self.verbose:
            self._print(f"  {Style.DIM}[DEBUG] {msg}{Style.RESET_ALL}")
    
    @contextmanager
    def progress(self, total: int, desc: str = "") -> Iterator[callable]:
        """Context manager for progress updates."""
        def update(current: int, item: str = ""):
            display = item[:35] + "..." if len(item) > 35 else item
            line = f"\r  {Style.DIM}{current}/{total}{Style.RESET_ALL} {display}"
            sys.stdout.write(line.ljust(70))
            sys.stdout.flush()
        
        try:
            yield update
        finally:
            sys.stdout.write("\r" + " " * 70 + "\r")
            sys.stdout.flush()
    
    def _print(self, msg: str) -> None:
        print(msg)
        sys.stdout.flush()
    
    def _get_time_str(self) -> str:
        if not self._step_start:
            return ""
        elapsed = time.time() - self._step_start
        if elapsed >= 1:
            return f" {Style.DIM}({elapsed:.1f}s){Style.RESET_ALL}"
        return ""

# Global instance
console = Console()
```

**Then update all files to use it:**
```python
from company_researcher.utils.console import console

# Instead of: out_step("Scraping website")
console.step("Scraping website")

# Instead of: out_ok(f"{count} pages scraped")
console.ok(f"{count} pages scraped")
```

---

### 2. Create Proper Logging

**File:** `src/company_researcher/utils/logging.py`

```python
"""Structured logging configuration."""
import logging
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

def setup_logging(
    level: str = "INFO",
    log_dir: Optional[Path] = None,
    session_id: Optional[str] = None
) -> logging.Logger:
    """Configure logging for the application."""
    
    logger = logging.getLogger("company_researcher")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Console handler - errors only
    console = logging.StreamHandler()
    console.setLevel(logging.ERROR)
    console.setFormatter(logging.Formatter(
        "%(levelname)s: %(message)s"
    ))
    logger.addHandler(console)
    
    # File handler - everything
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        session = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(
            log_dir / f"research_{session}.log",
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        ))
        logger.addHandler(file_handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Get a child logger."""
    return logging.getLogger(f"company_researcher.{name}")
```

---

### 3. Fix Exception Handling Pattern

**Create a decorator for consistent error handling:**

```python
# utils/errors.py
"""Error handling utilities."""
import functools
import logging
from typing import TypeVar, Callable, Optional, Tuple, Any

logger = logging.getLogger(__name__)

T = TypeVar('T')

class ResearchError(Exception):
    """Base exception for research errors."""
    pass

class ScrapingError(ResearchError):
    """Error during web scraping."""
    pass

class AIError(ResearchError):
    """Error during AI operations."""
    pass

class ConfigurationError(ResearchError):
    """Configuration error."""
    pass

def safe_call(
    default: T = None,
    exceptions: tuple = (Exception,),
    log_level: str = "warning"
) -> Callable:
    """Decorator for safe function calls with logging."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                log_func = getattr(logger, log_level)
                log_func(f"{func.__name__} failed: {e}", exc_info=True)
                return default
        return wrapper
    return decorator

# Usage:
@safe_call(default=(None, "Unknown error"), exceptions=(requests.RequestException,))
def scrape_with_requests(url: str, timeout: int = 15) -> Tuple[Optional[str], Optional[str]]:
    ...
```

---

### 4. Create Configuration Class

**File:** `src/company_researcher/config/settings.py`

```python
"""Application configuration with validation."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

@dataclass
class APIConfig:
    """API configuration."""
    gemini_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    search_key: str = field(default_factory=lambda: os.getenv("SEARCH_API_KEY", ""))
    search_engine_id: str = field(default_factory=lambda: os.getenv("SEARCH_ENGINE_ID", ""))
    
    def validate(self) -> None:
        """Validate API configuration."""
        if not self.gemini_key:
            raise ConfigurationError("GEMINI_API_KEY not set")
        if not self.search_key:
            raise ConfigurationError("SEARCH_API_KEY not set")
        if not self.search_engine_id:
            raise ConfigurationError("SEARCH_ENGINE_ID not set")

@dataclass
class ScrapingConfig:
    """Scraping configuration."""
    max_retries: int = 2
    timeout: int = 15
    max_depth: int = 2
    cache_ttl_hours: int = 24
    min_content_length: int = 100
    excluded_sites: List[str] = field(default_factory=lambda: [
        "login", "captcha", "privacy-policy", "terms-of-service"
    ])

@dataclass  
class AIConfig:
    """AI model configuration."""
    research_model: str = "gemini-2.0-flash"
    report_model: str = "gemini-2.0-flash"
    max_retries: int = 3
    grade_threshold: int = 80

@dataclass
class PathConfig:
    """Path configuration."""
    project_root: Path = field(default_factory=Path.cwd)
    output_dir: Path = field(init=False)
    working_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    cache_dir: Path = field(init=False)
    
    def __post_init__(self):
        self.output_dir = self.project_root / "output"
        self.working_dir = self.project_root / "working"
        self.logs_dir = self.project_root / "logs"
        self.cache_dir = self.logs_dir / "scrape_cache"
        
        # Create directories
        for d in [self.output_dir, self.working_dir, self.logs_dir, self.cache_dir]:
            d.mkdir(parents=True, exist_ok=True)

@dataclass
class Settings:
    """Application settings."""
    api: APIConfig = field(default_factory=APIConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    verbose: bool = field(default_factory=lambda: os.getenv("VERBOSE", "false").lower() == "true")
    
    def validate(self) -> None:
        """Validate all configuration."""
        self.api.validate()

# Lazy-loaded singleton
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    """Get application settings (lazy initialization)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

---

### 5. Create AI Client Abstraction

**File:** `src/company_researcher/ai/client.py`

```python
"""Unified AI client."""
import time
import logging
from typing import Optional
from google import genai
from google.genai import types

from company_researcher.config.settings import get_settings

logger = logging.getLogger(__name__)

class AIClient:
    """Unified AI client with retry logic and error handling."""
    
    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self._client = genai.Client(api_key=api_key or settings.api.gemini_key)
        self._settings = settings.ai
    
    def generate(
        self,
        prompt: str,
        model_type: str = "research",
        temperature: float = 1.0,
        thinking_level: str = "high",
        max_retries: Optional[int] = None
    ) -> str:
        """
        Generate content with automatic retries.
        
        Args:
            prompt: The prompt to send
            model_type: "research" or "report"
            temperature: Sampling temperature
            thinking_level: "low" or "high"
            max_retries: Override default retry count
            
        Returns:
            Generated text
            
        Raises:
            AIError: If all retries fail
        """
        model = (
            self._settings.research_model 
            if model_type == "research" 
            else self._settings.report_model
        )
        retries = max_retries or self._settings.max_retries
        
        config = types.GenerateContentConfig(
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level)
        )
        
        last_error = None
        for attempt in range(retries):
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
                return response.text.strip()
            except Exception as e:
                last_error = e
                logger.warning(
                    f"AI call failed (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
        
        raise AIError(f"AI call failed after {retries} attempts: {last_error}")
    
    def generate_fast(self, prompt: str, model_type: str = "research") -> str:
        """Fast generation with minimal thinking."""
        return self.generate(prompt, model_type=model_type, thinking_level="low")

# Convenience functions for backward compatibility
_client: Optional[AIClient] = None

def get_client() -> AIClient:
    global _client
    if _client is None:
        _client = AIClient()
    return _client

def llm(prompt: str, model_type: str = "research", **kwargs) -> str:
    """Backward-compatible LLM function."""
    return get_client().generate(prompt, model_type=model_type, **kwargs)

def llm_fast(prompt: str, model_type: str = "research") -> str:
    """Backward-compatible fast LLM function."""
    return get_client().generate_fast(prompt, model_type=model_type)
```

---

### 6. Add Type Stubs

**File:** `src/company_researcher/py.typed`
```
# Marker file for PEP 561
```

**File:** `src/company_researcher/types.py`
```python
"""Type definitions for the package."""
from typing import TypedDict, Optional, List, Dict, Tuple, Protocol

class SearchResult(TypedDict):
    title: str
    url: str

class ScrapedContent(TypedDict):
    url: str
    content: str
    method: str
    timestamp: str

class GradeResult(TypedDict):
    score: int
    needs_research: bool
    reason: str

class Scraper(Protocol):
    """Protocol for scraper implementations."""
    def scrape(self, url: str, timeout: int = 15) -> Tuple[Optional[str], Optional[str]]: ...

class SearchClient(Protocol):
    """Protocol for search implementations."""
    def search(self, query: str, num_results: int = 10) -> List[SearchResult]: ...
```

---

### 7. Fix Temp File Handling

**Add to `utils/files.py`:**

```python
"""File handling utilities."""
import os
import tempfile
import hashlib
import re
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator

@contextmanager
def secure_temp_file(suffix: str = "") -> Iterator[Path]:
    """Create a secure temporary file that's automatically cleaned up."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    path = Path(path)
    try:
        os.close(fd)
        yield path
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Sanitize a string for safe use as a filename."""
    # Remove path traversal attempts
    name = name.replace("..", "").replace("/", "").replace("\\", "")
    # Keep only safe characters
    name = re.sub(r'[^\w\s\-.]', '', name)
    # Replace spaces
    name = name.replace(" ", "_")
    # Limit length
    return name[:max_length] if name else "unnamed"

def get_safe_company_path(base_dir: Path, company_name: str) -> Path:
    """Get a safe path for company data."""
    safe_name = sanitize_filename(company_name)
    path = (base_dir / safe_name).resolve()
    
    # Verify path is under base_dir (defense in depth)
    base_resolved = base_dir.resolve()
    if not str(path).startswith(str(base_resolved)):
        raise ValueError(f"Invalid company name: {company_name}")
    
    return path

def get_cache_key(url: str) -> str:
    """Generate a cache key for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:32]
```

---

## Testing Improvements

### Add `tests/conftest.py` fixtures:

```python
"""Shared test fixtures."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from company_researcher.config.settings import Settings, APIConfig, PathConfig

@pytest.fixture
def mock_settings(tmp_path):
    """Create mock settings for testing."""
    return Settings(
        api=APIConfig(
            gemini_key="test-key",
            search_key="test-search-key", 
            search_engine_id="test-engine-id"
        ),
        paths=PathConfig(project_root=tmp_path)
    )

@pytest.fixture
def mock_ai_client():
    """Create a mock AI client."""
    client = MagicMock()
    client.generate.return_value = "Mock AI response"
    return client

@pytest.fixture
def sample_html():
    """Sample HTML for testing."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Test Company</title></head>
    <body>
        <nav>Navigation</nav>
        <main>
            <h1>Welcome to Test Company</h1>
            <p>We provide innovative solutions.</p>
        </main>
        <footer>Footer</footer>
    </body>
    </html>
    """
```

---

## Migration Path

1. **Week 1:** Create new utility modules (console, logging, errors, files)
2. **Week 2:** Create Settings class and AI client abstraction
3. **Week 3:** Update existing code to use new modules (one file at a time)
4. **Week 4:** Add comprehensive tests
5. **Week 5:** Remove deprecated code paths

Each step should be a separate PR with tests.
