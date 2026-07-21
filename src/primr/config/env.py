"""Environment loading and user-level key storage for Primr."""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from dotenv import dotenv_values, find_dotenv

logger = logging.getLogger(__name__)

# Provider aliases mirror the wired providers in `ai.providers` (the registry is
# the source of truth for which providers exist; this map is the CLI convenience
# for `primr keys set <alias>`). Keep them in sync when a provider is added.
KEY_ALIASES: dict[str, str] = {
    "xai": "XAI_API_KEY",
    "grok": "XAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gpt": "OPENAI_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "local": "OLLAMA_API_KEY",
    "foundry": "AZURE_OPENAI_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
    "bedrock": "AWS_BEARER_TOKEN_BEDROCK",
    "aws": "AWS_BEARER_TOKEN_BEDROCK",
    "search": "SEARCH_API_KEY",
    "google-search": "SEARCH_API_KEY",
    "search-engine": "SEARCH_ENGINE_ID",
    "search-engine-id": "SEARCH_ENGINE_ID",
}

KEY_HELP: dict[str, str] = {
    "XAI_API_KEY": "Grok standard reasoning and strategy pipeline",
    "GEMINI_API_KEY": "Gemini writing, utility, premium mode, and scrape summaries",
    "ANTHROPIC_API_KEY": "Anthropic Claude provider (reasoning/writing/pro; needs `pip install anthropic`)",
    "OPENAI_API_KEY": "OpenAI GPT provider (utility/reasoning/writing; needs `pip install openai`)",
    "OLLAMA_API_KEY": "Optional key for Ollama or another local OpenAI-compatible endpoint",
    "AZURE_OPENAI_API_KEY": "Microsoft Foundry / Azure OpenAI (also set AZURE_OPENAI_BASE_URL or AZURE_OPENAI_ENDPOINT)",
    "AWS_BEARER_TOKEN_BEDROCK": "Amazon Bedrock API key (or use AWS_ACCESS_KEY_ID/AWS_PROFILE + AWS_REGION; needs `pip install 'primr[bedrock]'`)",
    "SEARCH_API_KEY": "Google Custom Search, only with SEARCH_PROVIDER=google",
    "SEARCH_ENGINE_ID": "Google Custom Search engine ID",
}

_ENV_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_DOTENV_INTERPOLATION_RE = re.compile(r"\$\{[^}\r\n]+\}")
_LOADED_ENV_VALUES: dict[str, str] = {}
_SUPERVISED_ENV_LOADING = os.environ.get("PRIMR_SUPERVISED_WORKER") == "1"

# A supervised research worker may load both the user and project .env files.
# These controller settings must never be restored inside that lower-trust,
# long-running process after the parent intentionally removed them.
SUPERVISED_BLOCKED_ENV_NAMES = frozenset(
    {
        "MCP_ADMIN_TOKENS",
        "MCP_ADMIN_TOKEN_MAX_AGE_HOURS",
        "MCP_JWT_AUDIENCE",
        "MCP_JWT_ISSUER",
        "MCP_JWT_SECRET",
        "PRIMR_MCP_APPROVAL_TOKEN_SECRET",
        "PRIMR_SUPERVISED_WORKER",
        "PRIMR_WORKER_JOB_ID",
        "PRIMR_WORKER_JOB_OBJECT",
    }
)
SUPERVISED_BLOCKED_ENV_PREFIXES = (
    "MCP_",
    "PRIMR_MCP_",
    "PRIMR_CONTROL_PLANE_",
    "PRIMR_WORKER_",
)
SUPERVISED_WORKER_ENV_NAMES = frozenset(
    {
        "ALL_PROXY",
        "ANTHROPIC_API_KEY",
        "APPDATA",
        "AWS_ACCESS_KEY_ID",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_DEFAULT_REGION",
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_ROLE_ARN",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_BASE_URL",
        "AZURE_OPENAI_ENDPOINT",
        "CHROME_PATH",
        "CHROMIUM_PATH",
        "COMSPEC",
        "CUDA_HOME",
        "CUDA_PATH",
        "CUDA_VISIBLE_DEVICES",
        "CURL_CA_BUNDLE",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "HIP_VISIBLE_DEVICES",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "DISPLAY",
        "DYLD_LIBRARY_PATH",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "LOCALAPPDATA",
        "LOCAL_LLM_BASE_URL",
        "LD_LIBRARY_PATH",
        "LIBPATH",
        "NODE_EXTRA_CA_CERTS",
        "NO_PROXY",
        "NVIDIA_DRIVER_CAPABILITIES",
        "NVIDIA_VISIBLE_DEVICES",
        "OLLAMA_BASE_URL",
        "OPENAI_API_KEY",
        "OS",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PYTHONHASHSEED",
        "PYTHONHOME",
        "PYTHONIOENCODING",
        "PYTHONPATH",
        "PYTHONUTF8",
        "REQUESTS_CA_BUNDLE",
        "ROCM_PATH",
        "ROCR_VISIBLE_DEVICES",
        "SEARCH_API_KEY",
        "SEARCH_ENGINE_ID",
        "SEARCH_PROVIDER",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "USER",
        "USERNAME",
        "USERPROFILE",
        "VIRTUAL_ENV",
        "WAYLAND_DISPLAY",
        "WINDIR",
        "XAI_API_KEY",
        "XAUTHORITY",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    }
)
SUPERVISED_WORKER_ENV_PREFIXES = (
    "AI_",
    "ANTHROPIC_",
    "GEMINI_",
    "LOCAL_LLM_",
    "MAX_EXTERNAL_",
    "MIN_SCRAPED_",
    "OLLAMA_",
    "OPENAI_",
    "PLAYWRIGHT_",
    "PRIMR_",
    "SCRAPE_",
    "SEARCH_",
    "XAI_",
)


def is_supervised_blocked_env(name: str) -> bool:
    """Return whether a controller-only setting is blocked in a worker."""
    normalized = name.upper()
    return normalized in SUPERVISED_BLOCKED_ENV_NAMES or normalized.startswith(
        SUPERVISED_BLOCKED_ENV_PREFIXES
    )


def is_supervised_worker_env_allowed(name: str) -> bool:
    """Return whether a setting may cross into a supervised research worker."""
    normalized = name.upper()
    if is_supervised_blocked_env(normalized):
        return False
    return normalized in SUPERVISED_WORKER_ENV_NAMES or normalized.startswith(
        SUPERVISED_WORKER_ENV_PREFIXES
    )


def get_user_config_dir() -> Path:
    """Return the platform-appropriate Primr user config directory."""
    override = os.getenv("PRIMR_CONFIG_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "primr"
        return Path.home() / "AppData" / "Roaming" / "primr"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "primr"

    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    base = Path(xdg_config_home).expanduser() if xdg_config_home else Path.home() / ".config"
    return base / "primr"


def get_user_env_path() -> Path:
    """Return the per-user Primr environment file path."""
    return get_user_config_dir() / ".env"


def keystore_sandbox_warning() -> str | None:
    """Warn if the key store is redirected by Microsoft Store Python.

    Store-distributed Python virtualizes writes under ``%APPDATA%`` into a
    per-package ``LocalCache`` sandbox at the *filesystem* layer: the process
    reports a normal ``...\\AppData\\Roaming\\primr\\.env`` path, but the bytes
    physically land in ``...\\Packages\\PythonSoftwareFoundation...\\LocalCache``.
    Keys saved by such an install are invisible to a normal (python.org) primr,
    which silently looks like "keys won't save". Detect the divergence between
    the reported path and its real path and return an actionable message, else
    ``None``. No path construction escapes this - only a non-AppData location
    (``PRIMR_CONFIG_DIR``) or a non-Store Python does.
    """
    if sys.platform != "win32":
        return None
    try:
        reported = str(get_user_env_path())
        real = os.path.realpath(reported)
    except OSError:
        return None
    norm = real.replace("\\", "/")
    redirected = "/Packages/" in norm and "/LocalCache/" in norm
    if redirected and os.path.normcase(real) != os.path.normcase(reported):
        return (
            f"Key store is sandboxed by Microsoft Store Python at {real} - keys "
            "saved here are NOT shared with a non-Store primr install. Fix: use a "
            "python.org Python, or set PRIMR_CONFIG_DIR to a path outside AppData "
            "(e.g. %USERPROFILE%\\.primr)."
        )
    return None


def get_local_env_path() -> Path | None:
    """Return the nearest local .env found from the current working directory."""
    found = find_dotenv(usecwd=True)
    if not found:
        return None
    path = Path(found)
    user_path = get_user_env_path()
    try:
        if path.resolve() == user_path.resolve():
            return None
    except OSError:
        pass
    return path


def _apply_env_file(path: Path | None, protected_keys: set[str]) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if not path or not path.exists():
        return loaded
    # Supervised workers parse raw assignments. Expanding the complete file
    # first would let a blocked controller secret flow into an allowed provider
    # variable through ``XAI_API_KEY=${MCP_JWT_SECRET}``.
    values = dotenv_values(path, interpolate=not _SUPERVISED_ENV_LOADING)
    for key, value in values.items():
        if not key or value is None:
            continue
        if _SUPERVISED_ENV_LOADING and not is_supervised_worker_env_allowed(key):
            continue
        if _SUPERVISED_ENV_LOADING and _DOTENV_INTERPOLATION_RE.search(value):
            continue
        if key not in protected_keys:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def load_primr_env() -> None:
    """Load Primr environment values with predictable precedence.

    Precedence, highest to lowest:
    1. Real process environment
    2. Nearest local .env from the current working directory
    3. Per-user Primr config file
    """
    protected_keys = {
        key for key, value in os.environ.items() if _LOADED_ENV_VALUES.get(key) != value
    }
    loaded_values: dict[str, str] = {}
    loaded_values.update(_apply_env_file(get_user_env_path(), protected_keys))
    loaded_values.update(_apply_env_file(get_local_env_path(), protected_keys))
    _LOADED_ENV_VALUES.update(loaded_values)


def normalize_key_name(name: str) -> str:
    """Map a provider/key alias to the environment variable Primr reads."""
    normalized = name.strip().lower().replace("_", "-")
    if normalized in KEY_ALIASES:
        return KEY_ALIASES[normalized]

    upper = name.strip().upper()
    if upper in set(KEY_ALIASES.values()):
        return upper

    allowed = ", ".join(sorted(KEY_ALIASES))
    raise ValueError(f"Unknown key '{name}'. Choose one of: {allowed}")


def mask_secret(value: str | None) -> str:
    """Return a safe display form for a configured secret."""
    if not value:
        return "not set"
    if len(value) <= 8:
        return "set"
    return f"{value[:4]}...{value[-4:]}"


def read_user_env_values() -> dict[str, str]:
    """Read values from the per-user Primr environment file."""
    path = get_user_env_path()
    if not path.exists():
        return {}
    return {key: value or "" for key, value in dotenv_values(path).items() if key}


def _env_file_value(env_name: str) -> tuple[str | None, str | None]:
    """Return ``(value, source_label)`` for ``env_name`` from the .env files.

    Checks the local .env first (higher precedence), then the per-user config.
    Returns ``(None, None)`` if neither file defines the key.
    """
    local_path = get_local_env_path()
    if local_path:
        local_path = Path(local_path)
        if local_path.exists():
            value = dotenv_values(local_path).get(env_name)
            if value:
                return value, "local .env"
    user_path = Path(get_user_env_path())
    if user_path.exists():
        value = dotenv_values(user_path).get(env_name)
        if value:
            return value, "user config"
    return None, None


def describe_key_source(env_name: str) -> tuple[str | None, str | None, str | None]:
    """Resolve where ``env_name``'s active value comes from and detect shadowing.

    Returns ``(active_value, source_label, shadowed_file_value)``:

    - ``active_value`` — current ``os.environ`` value (``None`` if unset).
    - ``source_label`` — ``"OS environment variable"``, ``"local .env"``,
      ``"user config"``, or ``None`` when unset.
    - ``shadowed_file_value`` — set only when an OS environment variable overrides
      a *different* value configured in a .env file, so callers can warn that
      edits to the file have no effect until the env var is cleared. This is the
      common "I changed the .env but it still uses the old key" failure mode.
    """
    active = os.environ.get(env_name)
    file_value, file_source = _env_file_value(env_name)
    if active is None:
        return None, None, None
    if file_value is not None and active == file_value:
        return active, file_source, None
    if file_value is not None:
        # An OS environment variable (or other process-level source) wins over
        # the differing .env value, so the file edit is silently ignored.
        return active, "OS environment variable", file_value
    return active, "OS environment variable", None


def _format_env_assignment(key: str, value: str) -> str:
    return f"{key}={value}"


def _secure_path_modes(path: Path) -> None:
    """Best-effort POSIX permission hardening for the user key store.

    On POSIX hosts the directory is forced to 0700 and the file to 0600 so
    other local users on the same machine cannot read the stored provider
    API keys — previously the file was created with the default umask
    (typically 0644), making Gemini / xAI / search keys world-readable on
    multi-user systems. ``chmod`` is best-effort: filesystems without
    POSIX permissions (FAT, some network mounts) silently no-op. Windows
    relies on its NTFS default ACL where files in a user profile inherit
    owner-only rights, so we skip chmod there.
    """
    if os.name != "posix":
        return
    try:
        path.parent.chmod(0o700)
    except OSError as e:
        logger.debug("Could not chmod %s to 0700: %s", path.parent, e)
    if path.exists():
        try:
            path.chmod(0o600)
        except OSError as e:
            logger.debug("Could not chmod %s to 0600: %s", path, e)


def set_user_key(name: str, value: str) -> tuple[str, Path]:
    """Persist a key in the per-user Primr environment file.

    The on-disk file holds provider secrets, so we tighten permissions to
    owner-only on POSIX before any data lands on disk. ``open(..., 0o600)``
    via ``os.open`` ensures the file is created with restrictive mode
    instead of inheriting the umask, and ``_secure_path_modes`` corrects
    a pre-existing file that may have been written by an older release.
    """
    env_name = normalize_key_name(name)
    path = get_user_env_path()
    # mkdir with mode=0o700 is honored only on POSIX (Windows ignores the
    # mode arg). Pre-existing dirs keep their mode; _secure_path_modes
    # tightens them below.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    lines: list[str]
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = [
            "# Primr user configuration",
            "# Managed by 'primr keys'. Local .env files and shell env vars can override this.",
            "",
        ]

    replacement = _format_env_assignment(env_name, value.strip())
    replaced = False
    for idx, line in enumerate(lines):
        match = _ENV_ASSIGNMENT_RE.match(line)
        if match and match.group(1) == env_name:
            lines[idx] = replacement
            replaced = True
            break

    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(replacement)

    data = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
    # Create-or-truncate with restrictive permissions in one syscall so
    # there is no window where the file is readable to other users.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(str(path), flags, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)

    _secure_path_modes(path)

    os.environ[env_name] = value.strip()
    _LOADED_ENV_VALUES[env_name] = value.strip()
    return env_name, path


def unset_user_key(name: str) -> tuple[str, Path, bool]:
    """Remove a key from the per-user Primr environment file."""
    env_name = normalize_key_name(name)
    path = get_user_env_path()
    if not path.exists():
        return env_name, path, False

    lines = path.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    removed = False
    for line in lines:
        match = _ENV_ASSIGNMENT_RE.match(line)
        if match and match.group(1) == env_name:
            removed = True
            continue
        kept.append(line)

    if removed:
        path.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
        _LOADED_ENV_VALUES.pop(env_name, None)
    return env_name, path, removed
