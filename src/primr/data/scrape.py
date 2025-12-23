"""
Bulletproof Web Scraper
Tiered fallback: requests -> httpx -> Playwright -> Playwright aggressive
"""

import atexit
import json
import os
import random
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import fitz
import httpx
import requests
from bs4 import BeautifulSoup
from colorama import Fore, Style, init
from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from primr.ai.llm import llm, llm_fast
from primr.config.models import PrimrModels
from primr.config.config import (
    EXCLUDED_SITES,
    GEMINI_API_KEY,
    PROJECT_ROOT,
    SCRAPE_TIMEOUT,
)
from primr.utils.console import console
from primr.utils.files import get_cache_key, secure_temp_file
from primr.utils.logging_config import get_logger

load_dotenv()
init()

# Module logger
logger = get_logger("scrape")

# ============================================================================
# CONSOLE OUTPUT - Using unified console module
# ============================================================================
VERBOSE = os.getenv("SCRAPE_VERBOSE", "false").lower() == "true"

# Convenience aliases for backward compatibility
def out_step(msg):
    console.step(msg)

def out_ok(msg, show_time=True):
    console.ok(msg, show_time=show_time)

def out_warn(msg):
    console.warn(msg)

def out_err(msg):
    console.error(msg)

def out_info(msg):
    console.info(msg)

def out_dim(msg):
    console.info(msg)

def out_progress(current, total, msg=""):
    console.progress(current, total, msg)

def out_progress_done():
    console.progress_done()

# Keep these for Playwright stealth scripts
DIM = Style.DIM
RESET = Style.RESET_ALL
BOLD = Style.BRIGHT
C_CYAN = Fore.CYAN
C_GREEN = Fore.GREEN
C_YELLOW = Fore.YELLOW
C_RED = Fore.RED
C_WHITE = Fore.WHITE


# ============================================================================
# BROWSER FINGERPRINT PROFILES
# ============================================================================
BROWSER_PROFILES = [
    {
        "name": "Windows Chrome",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "platform": "Win32",
        "vendor": "Google Inc.",
        "timezone": "America/New_York",
        "locale": "en-US",
        "screen": {"width": 1920, "height": 1080},
        "color_depth": 24,
        "hardware_concurrency": 8,
        "device_memory": 8,
        "webgl_vendor": "Google Inc. (Intel)",
        "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630, OpenGL 4.5)",
        "sec_ch_ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    },
    {
        "name": "Mac Chrome",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "platform": "MacIntel",
        "vendor": "Google Inc.",
        "timezone": "America/Los_Angeles",
        "locale": "en-US",
        "screen": {"width": 2560, "height": 1440},
        "color_depth": 30,
        "hardware_concurrency": 10,
        "device_memory": 16,
        "webgl_vendor": "Google Inc. (Apple)",
        "webgl_renderer": "ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)",
        "sec_ch_ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    },
    {
        "name": "Windows Firefox",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "platform": "Win32",
        "vendor": "",
        "timezone": "America/Chicago",
        "locale": "en-US",
        "screen": {"width": 1920, "height": 1200},
        "color_depth": 24,
        "hardware_concurrency": 12,
        "device_memory": 8,
        "webgl_vendor": "Intel Inc.",
        "webgl_renderer": "Intel Iris OpenGL Engine",
        "sec_ch_ua": None,
    },
    {
        "name": "Mac Safari",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "platform": "MacIntel",
        "vendor": "Apple Computer, Inc.",
        "timezone": "America/Denver",
        "locale": "en-US",
        "screen": {"width": 1680, "height": 1050},
        "color_depth": 30,
        "hardware_concurrency": 8,
        "device_memory": 8,
        "webgl_vendor": "Apple Inc.",
        "webgl_renderer": "Apple GPU",
        "sec_ch_ua": None,
    },
]

USER_AGENTS: list[str] = [str(p["user_agent"]) for p in BROWSER_PROFILES]

def get_random_profile():
    return random.choice(BROWSER_PROFILES)

# ============================================================================
# LOGGING & CACHING
# ============================================================================
LOGS_DIR = str(Path(PROJECT_ROOT) / "logs" / "scraping_errors")
CACHE_DIR = str(Path(PROJECT_ROOT) / "logs" / "scrape_cache")
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

DISK_CACHE_TTL_HOURS = 24


class LRUCache:
    """
    Thread-safe LRU cache with configurable max size.

    Prevents unbounded memory growth during long scraping sessions.
    """

    def __init__(self, max_size: int = 100):
        from collections import OrderedDict
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        """Get item from cache, moving it to end (most recently used)."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return str(self._cache[key])
            return None

    def set(self, key: str, value: str) -> None:
        """Set item in cache, evicting oldest if at capacity."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
            else:
                if len(self._cache) >= self._max_size:
                    # Evict oldest (first) item
                    self._cache.popitem(last=False)
                self._cache[key] = value

    def clear(self) -> None:
        """Clear all items from cache."""
        with self._lock:
            self._cache.clear()

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._cache

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


# Use LRU cache instead of unbounded dict
_SCRAPE_CACHE = LRUCache(max_size=100)

def log_scraping_failure(url, error_message, level="ERROR"):
    log_file = os.path.join(LOGS_DIR, "scraping_failures.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {level}: {error_message} | URL: {url}\n")

def get_cached_content(url):
    """Get cached content from memory (LRU) or disk cache."""
    key = get_cache_key(url)

    # Check memory cache first
    cached = _SCRAPE_CACHE.get(key)
    if cached is not None:
        return cached

    # Check disk cache
    cache_file = os.path.join(CACHE_DIR, f"{key}.txt")
    meta_file = os.path.join(CACHE_DIR, f"{key}.meta")
    if os.path.exists(cache_file) and os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                meta = json.load(f)
            cached_time = datetime.fromisoformat(meta["timestamp"])
            age_hours = (datetime.now() - cached_time).total_seconds() / 3600
            if age_hours < DISK_CACHE_TTL_HOURS:
                with open(cache_file, encoding="utf-8") as f:
                    content = f.read()
                # Add to memory cache
                _SCRAPE_CACHE.set(key, content)
                return content
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug(f"Cache read failed for {url}: {e}")
    return None

def cache_content(url, content):
    """Cache scraped content to memory (LRU) and disk."""
    key = get_cache_key(url)

    # Add to memory cache (LRU will evict old entries automatically)
    _SCRAPE_CACHE.set(key, content)

    # Also persist to disk
    try:
        cache_file = os.path.join(CACHE_DIR, f"{key}.txt")
        meta_file = os.path.join(CACHE_DIR, f"{key}.meta")
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(content)
        with open(meta_file, "w") as f:
            json.dump({"url": url, "timestamp": datetime.now().isoformat(), "size": len(content)}, f)
    except OSError as e:
        logger.warning(f"Failed to cache content for {url}: {e}")

def clear_cache(max_age_hours=None):
    """Clear the scrape cache (memory and optionally disk)."""
    # Clear memory cache
    _SCRAPE_CACHE.clear()

    if max_age_hours is None:
        # Clear all disk cache
        for f in os.listdir(CACHE_DIR):
            try:
                os.remove(os.path.join(CACHE_DIR, f))
            except OSError as e:
                logger.debug(f"Failed to remove cache file {f}: {e}")
    else:
        # Clear only old disk cache entries
        for f in os.listdir(CACHE_DIR):
            if f.endswith(".meta"):
                try:
                    meta_path = os.path.join(CACHE_DIR, f)
                    with open(meta_path) as mf:
                        meta = json.load(mf)
                    cached_time = datetime.fromisoformat(meta["timestamp"])
                    age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        os.remove(meta_path)
                        os.remove(meta_path.replace(".meta", ".txt"))
                except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
                    logger.debug(f"Failed to process cache file {f}: {e}")


# ============================================================================
# URL VALIDATION & FILTERING
# ============================================================================
def normalize_url(url):
    if not url:
        return url
    url = url.split("#")[0]
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized

def is_excluded_site(url):
    return any(excluded in url.lower() for excluded in EXCLUDED_SITES)

def validate_url(url, base_url=None):
    if not isinstance(url, str) or len(url) < 5:
        return None
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url.lstrip('/')}"
    return url if "http" in url else None

def is_valid_url_string(s):
    """Check if a string is a valid HTTP(S) URL."""
    try:
        parsed = urlparse(s)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except (ValueError, AttributeError):
        return False

# ============================================================================
# SOFT BLOCK DETECTION
# ============================================================================
SOFT_BLOCK_INDICATORS = [
    "captcha", "verify you are human", "access denied", "forbidden",
    "please enable javascript", "browser check", "checking your browser",
    "ddos protection", "cloudflare", "just a moment", "ray id",
    "unusual traffic", "automated access", "bot detected",
    "enable cookies", "login required", "sign in to continue",
    "403 forbidden", "401 unauthorized", "blocked"
]

def detect_soft_block(text, url=""):
    if not text:
        return True, "Empty response"
    text_lower = text.lower()
    for indicator in SOFT_BLOCK_INDICATORS:
        if indicator in text_lower:
            if indicator == "cloudflare" and "cloudflare.com" in url.lower():
                continue
            if indicator == "login" and len(text) > 5000:
                continue
            return True, f"Detected: {indicator}"
    if len(text.strip()) < 100:
        return True, "Content too short"
    if text_lower.count("redirect") > 2:
        return True, "Redirect loop"
    return False, None

# ============================================================================
# CONTENT EXTRACTION
# ============================================================================
def extract_clean_text(soup):
    for tag in soup(["script", "style", "noscript", "meta", "header", "footer",
                     "form", "aside", "nav", "iframe", "svg", "canvas"]):
        tag.extract()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    cleaned = []
    prev_line = None
    for line in lines:
        if line != prev_line:
            cleaned.append(line)
            prev_line = line
    return "\n".join(cleaned)

def extract_text_from_pdf(pdf_url: str) -> str | None:
    """Extract text content from a PDF URL."""
    try:
        headers: dict[str, str] = {"User-Agent": random.choice(USER_AGENTS)}
        response = requests.get(pdf_url, headers=headers, timeout=30)
        response.raise_for_status()

        # Use secure temp file
        with secure_temp_file(suffix=".pdf", prefix="pdf_") as temp_path:
            temp_path.write_bytes(response.content)

            text = ""
            with fitz.open(str(temp_path)) as pdf:
                for page in pdf:
                    text += page.get_text("text") + "\n"

        result = text.strip() if text.strip() else None
        if result:
            logger.info(f"Extracted {len(result)} chars from PDF: {pdf_url}")
        return result

    except requests.RequestException as e:
        logger.warning(f"Failed to download PDF {pdf_url}: {e}")
        log_scraping_failure(pdf_url, f"PDF download failed: {e}")
        return None
    except Exception as e:
        logger.error(f"PDF extraction failed for {pdf_url}: {e}")
        log_scraping_failure(pdf_url, f"PDF extraction failed: {e}")
        return None

# ============================================================================
# TIER 1: REQUESTS
# ============================================================================
def scrape_with_requests(url: str, timeout: int = 15) -> tuple[str | None, str | None]:
    headers: dict[str, str] = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        text = extract_clean_text(soup)
        is_blocked, reason = detect_soft_block(text, url)
        if is_blocked:
            return None, reason
        return text, None
    except requests.exceptions.HTTPError as e:
        return None, f"HTTP {e.response.status_code}"
    except requests.exceptions.RequestException as e:
        return None, str(e)[:50]

# ============================================================================
# TIER 2: HTTPX
# ============================================================================
def scrape_with_httpx(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    headers: dict[str, str] = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    try:
        with httpx.Client(http2=True, follow_redirects=True, timeout=timeout) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            text = extract_clean_text(soup)
            is_blocked, reason = detect_soft_block(text, url)
            if is_blocked:
                return None, reason
            return text, None
    except httpx.HTTPStatusError as e:
        return None, f"HTTP {e.response.status_code}"
    except Exception as e:
        return None, str(e)[:50]


# ============================================================================
# TIER 3: PLAYWRIGHT
# ============================================================================
_PLAYWRIGHT = None
_BROWSER = None
_browser_lock = threading.Lock()


def _cleanup_playwright_browser():
    """Clean up Playwright browser resources on exit."""
    global _PLAYWRIGHT, _BROWSER
    with _browser_lock:
        if _BROWSER is not None:
            try:
                _BROWSER.close()
                logger.debug("Playwright browser closed")
            except Exception as e:
                logger.debug(f"Error closing browser: {e}")
            _BROWSER = None
        if _PLAYWRIGHT is not None:
            try:
                _PLAYWRIGHT.stop()
                logger.debug("Playwright stopped")
            except Exception as e:
                logger.debug(f"Error stopping playwright: {e}")
            _PLAYWRIGHT = None


# Register cleanup on exit
atexit.register(_cleanup_playwright_browser)


def get_playwright_browser():
    """Get or create the shared Playwright browser instance (thread-safe)."""
    global _PLAYWRIGHT, _BROWSER

    if _BROWSER is None:
        with _browser_lock:
            # Double-check after acquiring lock
            if _BROWSER is None:
                _PLAYWRIGHT = sync_playwright().start()
                _BROWSER = _PLAYWRIGHT.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-infobars",
                        "--window-size=1920,1080",
                        "--disable-extensions",
                        "--disable-plugins-discovery",
                        "--disable-default-apps",
                        "--disable-component-update",
                        "--disable-domain-reliability",
                        "--disable-background-networking",
                        "--disable-sync",
                        "--disable-translate",
                        "--metrics-recording-only",
                        "--no-first-run",
                        "--safebrowsing-disable-auto-update",
                        "--password-store=basic",
                        "--use-mock-keychain",
                        "--ignore-certificate-errors",
                        "--allow-running-insecure-content",
                    ]
                )
                logger.debug("Playwright browser initialized")
    return _BROWSER

def create_stealth_context(browser, profile=None):
    if profile is None:
        profile = get_random_profile()
    screen = profile["screen"]
    width = screen["width"] + random.randint(-50, 0)
    height = screen["height"] + random.randint(-30, 0)
    extra_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": f"{profile['locale']},en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    if profile.get("sec_ch_ua"):
        extra_headers["Sec-Ch-Ua"] = profile["sec_ch_ua"]
        extra_headers["Sec-Ch-Ua-Mobile"] = "?0"
        extra_headers["Sec-Ch-Ua-Platform"] = f'"{profile["platform"]}"'
    context = browser.new_context(
        user_agent=profile["user_agent"],
        viewport={"width": width, "height": height},
        locale=profile["locale"],
        timezone_id=profile["timezone"],
        geolocation={"latitude": 40.7128, "longitude": -74.0060},
        permissions=["geolocation"],
        java_script_enabled=True,
        bypass_csp=True,
        color_scheme="light",
        extra_http_headers=extra_headers,
    )
    stealth_script = f"""
        Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
        delete navigator.__proto__.webdriver;
        {'window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };' if 'Chrome' in profile['user_agent'] else ''}
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({{ state: Notification.permission }}) :
                originalQuery(parameters)
        );
        Object.defineProperty(navigator, 'plugins', {{
            get: () => {{
                const plugins = [
                    {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' }},
                    {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' }},
                    {{ name: 'Native Client', filename: 'internal-nacl-plugin' }}
                ];
                plugins.item = (i) => plugins[i];
                plugins.namedItem = (name) => plugins.find(p => p.name === name);
                plugins.refresh = () => {{}};
                return plugins;
            }}
        }});
        Object.defineProperty(navigator, 'languages', {{ get: () => ['{profile["locale"]}', 'en'] }});
        Object.defineProperty(navigator, 'language', {{ get: () => '{profile["locale"]}' }});
        Object.defineProperty(navigator, 'platform', {{ get: () => '{profile["platform"]}' }});
        Object.defineProperty(navigator, 'vendor', {{ get: () => '{profile["vendor"]}' }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {profile["hardware_concurrency"]} }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {profile["device_memory"]} }});
        Object.defineProperty(navigator, 'connection', {{
            get: () => ({{ effectiveType: '4g', rtt: {random.randint(30, 80)}, downlink: {random.randint(5, 15)}, saveData: false }})
        }});
        Object.defineProperty(screen, 'colorDepth', {{ get: () => {profile["color_depth"]} }});
        Object.defineProperty(screen, 'pixelDepth', {{ get: () => {profile["color_depth"]} }});
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        const getParameterProxyHandler = {{
            apply: function(target, thisArg, args) {{
                const param = args[0];
                if (param === 37445) return '{profile["webgl_vendor"]}';
                if (param === 37446) return '{profile["webgl_renderer"]}';
                return Reflect.apply(target, thisArg, args);
            }}
        }};
        try {{
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            if (gl) {{ gl.getParameter = new Proxy(gl.getParameter.bind(gl), getParameterProxyHandler); }}
        }} catch(e) {{}}
        Object.defineProperty(window, 'parent', {{ get: () => window }});
        Object.defineProperty(window, 'top', {{ get: () => window }});
    """
    context.add_init_script(stealth_script)
    return context

def human_like_delay(min_sec=1.0, max_sec=3.0):
    time.sleep(random.uniform(min_sec, max_sec))

def dismiss_cookie_banners(page):
    cookie_selectors = [
        "button:has-text('Accept')", "button:has-text('Accept All')",
        "button:has-text('Accept Cookies')", "button:has-text('I Accept')",
        "button:has-text('Got it')", "button:has-text('OK')",
        "button:has-text('Agree')", "button:has-text('Allow')",
        "button:has-text('Allow All')", "[id*='cookie'] button",
        "[class*='cookie'] button", "[id*='consent'] button",
        "[class*='consent'] button", "[id*='gdpr'] button",
        "[class*='gdpr'] button", ".cookie-banner button",
        "#cookie-banner button", ".consent-banner button",
        "#onetrust-accept-btn-handler", ".cc-accept",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    ]
    for selector in cookie_selectors:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=500):
                button.click(timeout=1000)
                human_like_delay(0.3, 0.7)
                return True
        except Exception:
            # Selector not found or click failed - try next selector
            continue
    return False


def scrape_with_playwright(url, timeout=30000):
    browser = None
    context = None
    page = None
    try:
        browser = get_playwright_browser()
        context = create_stealth_context(browser)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        human_like_delay(1.0, 2.0)
        dismiss_cookie_banners(page)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.3)")
        human_like_delay(0.5, 1.0)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        text = extract_clean_text(soup)
        is_blocked, reason = detect_soft_block(text, url)
        if is_blocked:
            return None, reason
        return text, None
    except PlaywrightTimeout:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)[:50]
    finally:
        if page: page.close()
        if context: context.close()

def scrape_with_playwright_aggressive(url, timeout=45000):
    """Aggressive Playwright scraping with content expansion."""
    playwright = None
    browser = None
    context = None
    page = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage", "--no-sandbox",
                "--disable-setuid-sandbox", "--disable-infobars",
                "--disable-extensions", "--ignore-certificate-errors",
            ]
        )
        profile = get_random_profile()
        context = create_stealth_context(browser, profile)
        page = context.new_page()
        if VERBOSE:
            out_dim(f"Using profile: {profile['name']}")
        page.goto(url, wait_until="load", timeout=timeout)
        human_like_delay(2.0, 4.0)
        dismiss_cookie_banners(page)
        
        # Try to expand collapsed content (accordions, read-more, etc.)
        expand_selectors = [
            "[aria-expanded='false']",
            ".accordion-header:not(.active)",
            ".accordion-button.collapsed",
            "[data-toggle='collapse']",
            "[data-bs-toggle='collapse']",
            ".expand-btn", ".show-more", ".read-more",
            "button:has-text('Read more')",
            "button:has-text('Show more')",
            "button:has-text('View more')",
            "button:has-text('Load more')",
            ".expandable:not(.expanded)",
            "[class*='expand']:not([class*='expanded'])",
        ]
        for selector in expand_selectors:
            try:
                elements = page.locator(selector).all()
                for el in elements[:10]:  # Limit to 10 per selector
                    if el.is_visible():
                        el.click()
                        human_like_delay(0.2, 0.4)
            except Exception:
                pass  # Selector not found, continue
        
        # Scroll through page to load lazy content
        for i in range(3):
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {0.3 * (i+1)})")
            human_like_delay(0.5, 1.0)
        page.evaluate("window.scrollTo(0, 0)")
        human_like_delay(1.0, 2.0)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        text = extract_clean_text(soup)
        is_blocked, reason = detect_soft_block(text, url)
        if is_blocked:
            return None, reason
        return text, None
    except Exception as e:
        return None, str(e)[:50]
    finally:
        if page: page.close()
        if context: context.close()
        if browser: browser.close()
        if playwright: playwright.stop()

def scrape_with_vision(url, timeout=60000):
    """Scrape using vision AI to extract text from rendered page."""
    from google import genai
    from google.genai import types

    playwright = None
    browser = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage", "--no-sandbox"]
        )
        profile = get_random_profile()
        context = create_stealth_context(browser, profile)
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout)
        human_like_delay(2.0, 3.0)
        dismiss_cookie_banners(page)

        # Try to expand collapsed content
        expand_selectors = [
            "[aria-expanded='false']", ".accordion-header:not(.active)",
            "[data-toggle='collapse']", ".expand-btn", ".show-more", ".read-more",
        ]
        for selector in expand_selectors:
            try:
                elements = page.locator(selector).all()
                for el in elements[:10]:
                    if el.is_visible():
                        el.click()
                        human_like_delay(0.2, 0.4)
            except Exception as e:
                logger.debug(f"Could not expand {selector}: {e}")

        # Scroll through page to load lazy content
        page.evaluate("""
            async () => {
                await new Promise(resolve => {
                    let totalHeight = 0;
                    const distance = 300;
                    const timer = setInterval(() => {
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if (totalHeight >= document.body.scrollHeight) {
                            clearInterval(timer);
                            window.scrollTo(0, 0);
                            resolve();
                        }
                    }, 100);
                });
            }
        """)
        human_like_delay(1.0, 2.0)

        # Use secure temp file for PDF
        with secure_temp_file(suffix=".pdf", prefix="vision_") as pdf_path:
            page.pdf(path=str(pdf_path), format="A4", print_background=True)
            pdf_bytes = pdf_path.read_bytes()

            client = genai.Client(api_key=GEMINI_API_KEY)
            content = types.Content(parts=[
                types.Part(text="Extract ALL text content from this webpage PDF. Include headings, paragraphs, lists, and any visible text. Output only the extracted text, no commentary."),
                types.Part(inline_data=types.Blob(mime_type="application/pdf", data=pdf_bytes))
            ])
            response = client.models.generate_content(
                model=PrimrModels.FAST_MODEL,
                contents=content,
                config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0))
            )

        text = (response.text or "").strip()
        if text and len(text) > 100:
            logger.info(f"Vision extraction successful for {url}")
            return text, None
        else:
            logger.warning(f"Vision extraction returned insufficient content for {url}")
            return None, "Vision extraction returned insufficient content"

    except Exception as e:
        logger.error(f"Vision scraping failed for {url}: {e}")
        return None, str(e)[:80]
    finally:
        # Cleanup resources - ignore errors during cleanup
        if page:
            try: page.close()
            except Exception: pass
        if context:
            try: context.close()
            except Exception: pass
        if browser:
            try: browser.close()
            except Exception: pass
        if playwright:
            try: playwright.stop()
            except Exception: pass


# ============================================================================
# MAIN SCRAPING ORCHESTRATOR
# ============================================================================
def scrape_page(url, silent=False, pbar=None, use_vision=False):
    short_url = urlparse(url).path or "/"
    if len(short_url) > 40:
        short_url = short_url[:37] + "..."
    cached = get_cached_content(url)
    if cached:
        if pbar:
            pbar.set_postfix_str(f"cached: {short_url}")
        return cached, "cache"
    if url.lower().endswith(".pdf"):
        if pbar:
            pbar.set_postfix_str(f"pdf: {short_url}")
        text = extract_text_from_pdf(url)
        if text:
            cache_content(url, text)
        return text, "pdf" if text else None
    tiers = [
        ("requests", scrape_with_requests, {"timeout": SCRAPE_TIMEOUT}),
        ("httpx", scrape_with_httpx, {"timeout": SCRAPE_TIMEOUT + 5}),
        ("browser", scrape_with_playwright, {"timeout": 30000}),
        ("browser+", scrape_with_playwright_aggressive, {"timeout": 45000}),
    ]
    if use_vision:
        tiers.append(("vision", scrape_with_vision, {"timeout": 60000}))
    last_error = None
    for tier_name, scrape_func, kwargs in tiers:
        if last_error:
            time.sleep(random.uniform(1.0, 3.0))
        if pbar:
            pbar.set_postfix_str(f"{tier_name}: {short_url}")
        try:
            text, error = scrape_func(url, **kwargs)
            if text and not error:
                cache_content(url, text)
                return text, tier_name
            else:
                last_error = error
                log_scraping_failure(url, f"{tier_name}: {error}", level="WARN")
        except Exception as e:
            last_error = str(e)
            log_scraping_failure(url, f"{tier_name}: {e}", level="ERROR")
    log_scraping_failure(url, f"All tiers failed. Last: {last_error}", level="CRITICAL")
    return None, None

# ============================================================================
# LINK EXTRACTION
# ============================================================================
def extract_links_from_homepage(base_url, company_name):
    """Extract links from homepage, prioritizing browser for JS-heavy sites."""
    html_content = None
    method_used = None
    
    # For link extraction, try browser FIRST since most modern sites are JS-heavy
    methods = [
        ("browser", lambda: get_html_playwright_for_links(base_url)),
        ("httpx", lambda: get_html_httpx(base_url)),
        ("requests", lambda: get_html_requests(base_url)),
    ]
    
    for method_name, get_html in methods:
        try:
            html_content = get_html()
            if html_content and len(html_content) > 500:
                method_used = method_name
                # Count links to see if we got good content
                soup = BeautifulSoup(html_content, "html.parser")
                link_count = len(soup.find_all(["a", "area"], href=True))
                if link_count > 5 or method_name == "browser":
                    # Good enough content or already tried browser
                    break
                elif VERBOSE:
                    out_dim(f"{method_name} found only {link_count} links, trying next method")
        except Exception as e:
            if VERBOSE:
                out_dim(f"{method_name} failed: {str(e)[:50]}")
            html_content = None
            
    if not method_used:
        out_err("Could not access website")
        return [base_url]
        
    soup = BeautifulSoup(html_content, "html.parser")
    links = set()
    parsed_base = urlparse(base_url)
    
    # Extract links from anchor tags
    for link in soup.find_all(["a", "area"], href=True):
        href = link["href"]
        full_url = urljoin(base_url, href)
        parsed_link = urlparse(full_url)
        if (parsed_link.netloc == parsed_base.netloc and
            parsed_link.scheme in ("http", "https") and
            "#" not in parsed_link.path):
            links.add(normalize_url(full_url))
    
    # Also check for links in navigation elements, buttons with onclick, etc.
    for nav in soup.find_all(["nav", "header", "footer"]):
        for link in nav.find_all("a", href=True):
            href = link["href"]
            full_url = urljoin(base_url, href)
            parsed_link = urlparse(full_url)
            if (parsed_link.netloc == parsed_base.netloc and
                parsed_link.scheme in ("http", "https")):
                links.add(normalize_url(full_url))
    
    if not links:
        return [normalize_url(base_url)]
        
    EXCLUDED_KEYWORDS = [
        "login", "signin", "sign-in", "signup", "sign-up", "register",
        "support", "help", "faq", "contact", "contact-us",
        "terms", "privacy", "cookies", "legal", "disclaimer",
        "accessibility", "sitemap", "careers", "jobs", "apply", "internship", "hiring",
        "webinar", "event", "calendar", "cart", "checkout", "account", "profile", "settings",
        "unsubscribe", "preferences",
    ]
    filtered_links = {link for link in links if not any(kw in link.lower() for kw in EXCLUDED_KEYWORDS)}
    
    # If we filtered too aggressively, keep some links
    if len(filtered_links) < 3 and len(links) > 3:
        filtered_links = links
    
    try:
        prompts_file = Path(__file__).parent.parent / "config" / "prompts.json"
        with open(prompts_file, encoding="utf-8") as f:
            prompts = json.load(f)
        if "filter_links_for_research" in prompts and len(filtered_links) > 5:
            filter_prompt = prompts["filter_links_for_research"].format(
                company_name=company_name, website=base_url, links="\n".join(sorted(filtered_links))
            )
            # Use link_selection model type - intelligent prioritization of which pages to scrape
            llm_response = llm_fast(filter_prompt, model_type="link_selection")
            llm_links = {line.strip() for line in llm_response.split("\n") if line.strip() and is_valid_url_string(line.strip())}
            # Only use AI link selection if it returns reasonable results
            if llm_links and len(llm_links) >= 3:
                filtered_links = llm_links
    except Exception:
        # AI link selection failed - fall back to heuristic filtering
        pass
        
    filtered_links.add(normalize_url(base_url))
    return sorted(filtered_links)


def get_html_playwright_for_links(url, retries=2):
    """Get HTML with Playwright for link extraction - fast and simple."""
    from playwright.sync_api import sync_playwright
    
    last_error = None
    for attempt in range(retries):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                try:
                    # Use domcontentloaded - faster than networkidle and usually enough
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    # Short wait for JS to render
                    page.wait_for_timeout(2000)
                    html = page.content()
                    if html and len(html) > 500:
                        return html
                finally:
                    browser.close()
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                import time
                time.sleep(1)
                
    if last_error:
        raise last_error
    return None


def get_html_requests(url: str) -> str:
    headers: dict[str, str] = {"User-Agent": random.choice(USER_AGENTS)}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text

def get_html_httpx(url: str) -> str:
    headers: dict[str, str] = {"User-Agent": random.choice(USER_AGENTS)}
    with httpx.Client(http2=True, follow_redirects=True, timeout=20) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        return response.text

def get_html_playwright(url, retries=2):
    global _BROWSER
    last_error = None
    for attempt in range(retries):
        try:
            browser = get_playwright_browser()
            context = create_stealth_context(browser)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                human_like_delay(2.0, 3.5)
                html = page.content()
                if html and len(html) > 500:
                    return html
            finally:
                page.close()
                context.close()
        except Exception as e:
            last_error = e
            cleanup_browser()
            if attempt < retries - 1:
                human_like_delay(1.0, 2.0)
    if last_error:
        raise last_error
    return None


# ============================================================================
# HIGH-LEVEL SCRAPING FUNCTIONS
# ============================================================================
def scrape_company_website(base_url, company_name, filtered_links):
    if not filtered_links:
        out_warn("No pages to scrape")
        return {}
    scraped_content = {}
    success_count = 0
    total = len(filtered_links)
    for i, url in enumerate(filtered_links):
        path = urlparse(url).path or "/"
        out_progress(i + 1, total, path)
        human_like_delay(0.5, 1.5)
        content, method = scrape_page(url, silent=True, pbar=None)
        if content:
            scraped_content[url] = content
            success_count += 1
    out_progress_done()
    if success_count == total:
        out_ok(f"{success_count} pages scraped")
    elif success_count > 0:
        out_warn(f"{success_count}/{total} pages scraped")
    else:
        out_err("Could not scrape any pages")
    return scraped_content

def fetch_web_content(website, company_name, max_pages=None, use_vision=False):
    out_step(f"Scraping {C_WHITE}{website}{RESET}")
    pages_to_scrape = extract_links_from_homepage(website, company_name)
    if not pages_to_scrape:
        out_err("No pages found")
        return {}
    total_found = len(pages_to_scrape)
    if max_pages and max_pages < total_found:
        pages_to_scrape = pages_to_scrape[:max_pages]
        out_info(f"{total_found} pages found, scraping top {max_pages}")
    else:
        out_info(f"{len(pages_to_scrape)} pages to scrape")
    scraped_content = {}
    success_count = 0
    total = len(pages_to_scrape)
    for i, page_url in enumerate(pages_to_scrape):
        normalized_url = normalize_url(page_url)
        if normalized_url in scraped_content:
            continue
        path = urlparse(page_url).path or "/"
        out_progress(i + 1, total, path)
        human_like_delay(0.5, 1.5)
        page_text, method = scrape_page(page_url, silent=True, pbar=None, use_vision=use_vision)
        if page_text:
            scraped_content[normalized_url] = page_text
            success_count += 1
    out_progress_done()
    if success_count == total:
        out_ok(f"{success_count} pages scraped")
    elif success_count > 0:
        out_warn(f"{success_count}/{total} pages scraped")
    else:
        out_err("Could not scrape any pages")
    return scraped_content

def scrape_external_sources(search_results, max_sources=2, allowed_domains=None):
    scraped_sources = {}
    count = 0
    for result in search_results:
        url = result.get("url")
        if not url:
            continue
        if allowed_domains:
            domain = urlparse(url).netloc.lower()
            if not any(allowed in domain for allowed in allowed_domains):
                continue
        text, method = scrape_page(url, silent=True)
        if text and len(text.strip()) > 100:
            scraped_sources[url] = text.strip()
            count += 1
        if count >= max_sources:
            break
    return scraped_sources

# ============================================================================
# CLEANUP
# ============================================================================
def cleanup_browser():
    """Clean up browser resources at exit."""
    global _PLAYWRIGHT, _BROWSER
    if _BROWSER:
        try:
            _BROWSER.close()
        except Exception:
            # Ignore errors during cleanup
            pass
        _BROWSER = None
    if _PLAYWRIGHT:
        try:
            _PLAYWRIGHT.stop()
        except Exception:
            # Ignore errors during cleanup
            pass
        _PLAYWRIGHT = None

atexit.register(cleanup_browser)
