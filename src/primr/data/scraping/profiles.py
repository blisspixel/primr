"""
Browser fingerprint profiles for stealth scraping - 2026 standards.

Modern WAF detection looks at:
1. TLS fingerprint (JA3/JA4) - must match browser
2. HTTP/2 fingerprint (AKAMAI) - header order, priorities
3. JavaScript fingerprints - navigator properties, WebGL, Canvas
4. Behavioral patterns - mouse movements, timing

This module provides realistic 2026 browser profiles.
"""

import platform
import random
import re
from dataclasses import dataclass


@dataclass
class HttpHeaderProfile:
    """HTTP headers that must match TLS fingerprint."""

    name: str
    user_agent: str
    sec_ch_ua: str | None
    sec_ch_ua_platform: str | None
    accept_language: str


@dataclass
class BrowserContextProfile:
    """Browser context settings (safe to set via Playwright/DrissionPage)."""

    name: str
    viewport_width: int
    viewport_height: int
    locale: str
    timezone: str
    color_scheme: str  # "light" or "dark"


@dataclass
class StealthPatch:
    """Legacy class for backward compatibility."""

    name: str
    script: str
    description: str


# =============================================================================
# 2026 HTTP Header Profiles - Current Chrome/Edge versions
# =============================================================================

HTTP_PROFILES = [
    HttpHeaderProfile(
        name="chrome_131_windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    HttpHeaderProfile(
        name="chrome_131_mac",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"macOS"',
        accept_language="en-US,en;q=0.9",
    ),
    HttpHeaderProfile(
        name="chrome_130_windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="130", "Google Chrome";v="130", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    HttpHeaderProfile(
        name="edge_131_windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        sec_ch_ua='"Chromium";v="131", "Microsoft Edge";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    HttpHeaderProfile(
        name="safari_18_mac",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
        sec_ch_ua=None,  # Safari doesn't send sec-ch-ua
        sec_ch_ua_platform=None,
        accept_language="en-US,en;q=0.9",
    ),
]


# =============================================================================
# Browser Context Profiles - Common screen resolutions
# =============================================================================

CONTEXT_PROFILES = [
    BrowserContextProfile(
        name="desktop_1080p",
        viewport_width=1920,
        viewport_height=1080,
        locale="en-US",
        timezone="America/New_York",
        color_scheme="light",
    ),
    BrowserContextProfile(
        name="desktop_1440p",
        viewport_width=2560,
        viewport_height=1440,
        locale="en-US",
        timezone="America/Los_Angeles",
        color_scheme="light",
    ),
    BrowserContextProfile(
        name="desktop_1200",
        viewport_width=1920,
        viewport_height=1200,
        locale="en-US",
        timezone="America/Chicago",
        color_scheme="light",
    ),
    BrowserContextProfile(
        name="laptop_1366",
        viewport_width=1366,
        viewport_height=768,
        locale="en-US",
        timezone="America/Denver",
        color_scheme="light",
    ),
]


# =============================================================================
# Stealth Script - Comprehensive 2026 anti-detection
# =============================================================================

STEALTH_SCRIPT = """
// Hide webdriver flag
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
delete navigator.__proto__.webdriver;

// Fix plugins array (headless Chrome has empty plugins)
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
            {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''},
        ];
        plugins.item = (i) => plugins[i];
        plugins.namedItem = (name) => plugins.find(p => p.name === name);
        plugins.refresh = () => {};
        plugins.length = 3;
        return plugins;
    }
});

// Fix languages
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'language', {get: () => 'en-US'});

// Fix permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({state: Notification.permission}) :
        originalQuery(parameters)
);

// Fix chrome object (missing in headless)
if (!window.chrome) {
    window.chrome = {
        runtime: {
            connect: function() {},
            sendMessage: function() {},
            onMessage: {addListener: function() {}},
            onConnect: {addListener: function() {}},
            PlatformOs: {MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd'},
            PlatformArch: {ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64'},
            PlatformNaclArch: {ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64'},
            RequestUpdateCheckStatus: {THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available'},
        },
        loadTimes: function() {
            return {
                requestTime: Date.now() / 1000 - Math.random() * 10,
                startLoadTime: Date.now() / 1000 - Math.random() * 5,
                commitLoadTime: Date.now() / 1000 - Math.random() * 2,
                finishDocumentLoadTime: Date.now() / 1000 - Math.random(),
                finishLoadTime: Date.now() / 1000,
                firstPaintTime: Date.now() / 1000 - Math.random() * 3,
                firstPaintAfterLoadTime: 0,
                navigationType: 'Other',
                wasFetchedViaSpdy: false,
                wasNpnNegotiated: true,
                npnNegotiatedProtocol: 'h2',
                wasAlternateProtocolAvailable: false,
                connectionInfo: 'h2'
            };
        },
        csi: function() {
            return {
                onloadT: Date.now(),
                pageT: Date.now() - performance.timing.navigationStart,
                startE: performance.timing.navigationStart,
                tran: 15
            };
        },
        app: {
            isInstalled: false,
            InstallState: {INSTALLED: 'installed', NOT_INSTALLED: 'not_installed'},
            RunningState: {RUNNING: 'running', CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run'}
        }
    };
}

// Fix WebGL vendor/renderer (headless shows "Google SwiftShader")
const getParameterProxyHandler = {
    apply: function(target, thisArg, args) {
        const param = args[0];
        const gl = thisArg;
        // UNMASKED_VENDOR_WEBGL
        if (param === 37445) {
            return 'Google Inc. (NVIDIA)';
        }
        // UNMASKED_RENDERER_WEBGL
        if (param === 37446) {
            return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)';
        }
        return Reflect.apply(target, thisArg, args);
    }
};

try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (gl) {
        const originalGetParameter = gl.getParameter.bind(gl);
        gl.getParameter = new Proxy(originalGetParameter, getParameterProxyHandler);
    }
} catch (e) {}

// Fix connection type
if (navigator.connection) {
    Object.defineProperty(navigator.connection, 'rtt', {get: () => 50});
}

// Fix hardware concurrency (headless often shows 1)
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});

// Fix device memory
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

// Fix platform (ensure it's not detected as headless)
Object.defineProperty(navigator, 'platform', {get: () => '__PRIMR_PLATFORM__'});

// Fix vendor
Object.defineProperty(navigator, 'vendor', {get: () => 'Google Inc.'});

// Fix product
Object.defineProperty(navigator, 'product', {get: () => 'Gecko'});

// Fix productSub
Object.defineProperty(navigator, 'productSub', {get: () => '20030107'});

// Fix appVersion to match Chrome
Object.defineProperty(navigator, 'appVersion', {
    get: () => '__PRIMR_APP_VERSION__'
});

// Fix appName
Object.defineProperty(navigator, 'appName', {get: () => 'Netscape'});

// Fix mimeTypes
Object.defineProperty(navigator, 'mimeTypes', {
    get: () => {
        const mimeTypes = [
            {type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format'},
            {type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format'},
        ];
        mimeTypes.item = (i) => mimeTypes[i];
        mimeTypes.namedItem = (name) => mimeTypes.find(m => m.type === name);
        mimeTypes.length = 2;
        return mimeTypes;
    }
});

// Fix Notification
if (typeof Notification === 'undefined') {
    window.Notification = {
        permission: 'default',
        requestPermission: () => Promise.resolve('default')
    };
}

// Fix screen properties
Object.defineProperty(screen, 'availWidth', {get: () => window.innerWidth});
Object.defineProperty(screen, 'availHeight', {get: () => window.innerHeight});
Object.defineProperty(screen, 'colorDepth', {get: () => 24});
Object.defineProperty(screen, 'pixelDepth', {get: () => 24});

// Fix outerWidth/outerHeight (headless often has these as 0)
Object.defineProperty(window, 'outerWidth', {get: () => window.innerWidth + 16});
Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 88});

// Fix screenX/screenY
Object.defineProperty(window, 'screenX', {get: () => 0});
Object.defineProperty(window, 'screenY', {get: () => 0});
"""


# =============================================================================
# Public API Functions
# =============================================================================


def get_random_http_profile() -> HttpHeaderProfile:
    """Get a random HTTP header profile for fingerprint diversity."""
    return random.choice(HTTP_PROFILES)


def get_random_context_profile() -> BrowserContextProfile:
    """Get a random browser context profile."""
    return random.choice(CONTEXT_PROFILES)


def _extract_chromium_major(browser_version: str | None) -> str:
    """Extract a Chromium major version from Playwright's browser.version string."""
    if not browser_version:
        return "145"
    match = re.search(r"(\d+)", browser_version)
    return match.group(1) if match else "145"


def _host_platform_tokens(platform_name: str | None = None) -> tuple[str, str, str]:
    """Map host platform to UA and navigator.platform tokens."""
    normalized = (platform_name or platform.system()).lower()
    if normalized == "darwin":
        return "Macintosh; Intel Mac OS X 10_15_7", "macOS", "MacIntel"
    if normalized == "linux":
        return "X11; Linux x86_64", "Linux", "Linux x86_64"
    return "Windows NT 10.0; Win64; x64", "Windows", "Win32"


def get_browser_compatible_http_profile(
    browser_version: str | None = None, platform_name: str | None = None
) -> HttpHeaderProfile:
    """
    Build a browser profile aligned to the actual Chromium version and host OS.

    This avoids fingerprint mismatches such as Playwright Chromium 145 presenting
    itself as Chrome 130/131 or as a different operating system.
    """
    major = _extract_chromium_major(browser_version)
    ua_platform, ch_platform, _ = _host_platform_tokens(platform_name)
    return HttpHeaderProfile(
        name=f"chrome_{major}_{ch_platform.lower()}",
        user_agent=(
            f"Mozilla/5.0 ({ua_platform}) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
        ),
        sec_ch_ua=(
            f'"Chromium";v="{major}", "Google Chrome";v="{major}", "Not_A Brand";v="24"'
        ),
        sec_ch_ua_platform=f'"{ch_platform}"',
        accept_language="en-US,en;q=0.9",
    )


def get_stealth_script(user_agent: str | None = None, platform_name: str | None = None) -> str:
    """Get comprehensive stealth script, optionally aligned to a concrete browser fingerprint."""
    _, _, navigator_platform = _host_platform_tokens(platform_name)
    app_version = user_agent or (
        "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    )
    return (
        STEALTH_SCRIPT.replace("__PRIMR_PLATFORM__", navigator_platform).replace(
            "__PRIMR_APP_VERSION__", app_version
        )
    )


def get_http_profile_by_name(name: str) -> HttpHeaderProfile | None:
    """Get a specific HTTP profile by name."""
    for profile in HTTP_PROFILES:
        if profile.name == name:
            return profile
    return None


def get_context_profile_by_name(name: str) -> BrowserContextProfile | None:
    """Get a specific context profile by name."""
    for profile in CONTEXT_PROFILES:
        if profile.name == name:
            return profile
    return None
