"""The ``primr keys`` subcommand: store and inspect per-user API keys.

Extracted from ``core/cli.py`` to keep that coordinator under the
architecture line ceiling (see ``tests/test_architecture.py``). Wired back
via ``from primr.core.cli_keys import run_keys``.
"""

import argparse
import os
import sys

from primr.utils.console import console
from primr.utils.terminal import can_prompt_for_input


def create_keys_parser() -> argparse.ArgumentParser:
    """Create the parser for the keys helper command."""
    from primr.config.env import KEY_ALIASES

    key_choices = sorted(set(KEY_ALIASES) | set(KEY_ALIASES.values()))

    parser = argparse.ArgumentParser(
        prog="primr keys",
        description="Store Primr API keys in the per-user Primr config file.",
    )
    subparsers = parser.add_subparsers(dest="action")

    set_parser = subparsers.add_parser("set", help="Set an API key")
    set_parser.add_argument(
        "provider",
        choices=key_choices,
        help="Key to set. Common choices: xai, gemini, openai, anthropic, ollama",
    )
    set_parser.add_argument(
        "provided_value",
        nargs="?",
        help="Key value. Omit this to enter it without echoing to the terminal.",
    )
    set_parser.add_argument(
        "--value",
        dest="option_value",
        help="Key value for scripts. Prefer the hidden prompt for manual setup.",
    )

    unset_parser = subparsers.add_parser("unset", help="Remove a key from user config")
    unset_parser.add_argument("provider", choices=key_choices)

    subparsers.add_parser("list", help="Show configured key status")
    subparsers.add_parser("path", help="Show where Primr stores user keys")

    test_parser = subparsers.add_parser(
        "test",
        help="Validate that configured keys actually authenticate (free, no model spend)",
    )
    test_parser.add_argument(
        "provider",
        nargs="?",
        choices=key_choices,
        help="Validate only this provider. Omit to test every configured provider.",
    )
    return parser


def _run_keys_test(provider_filter: str | None) -> int:
    """Live, auth-only validation of configured provider keys (no model spend)."""
    from primr.ai.providers import (
        KNOWN_PROVIDERS,
        get_available_providers,
        validate_provider_credentials,
    )
    from primr.config.env import load_primr_env, normalize_key_name

    load_primr_env()
    console.banner("Primr Key Validation")
    console.info("Auth-only checks (free models.list; no model generation, no token spend)")
    console.blank()

    if provider_filter:
        target_env = normalize_key_name(provider_filter)
        entries = [p for p in KNOWN_PROVIDERS if p.api_key_env == target_env]
    else:
        entries = get_available_providers()

    if not entries:
        console.warn("No configured providers to test. Set a key with: primr keys set <provider>")
        return 0

    failures = 0
    for entry in entries:
        result = validate_provider_credentials(entry)
        latency = f" ({result.latency_ms} ms)" if result.latency_ms is not None else ""
        if result.ok:
            console.ok(f"{entry.name}: {result.detail}{latency}")
        else:
            failures += 1
            console.error(f"{entry.name}: {result.detail}{latency}")

    console.blank()
    if failures:
        console.warn(f"{failures} provider(s) failed validation")
        return 1
    console.ok("All configured provider keys authenticated")
    return 0


def run_keys(args: list[str] | None) -> int:
    """Run the ``primr keys`` helper command."""
    import getpass

    from primr.config.env import (
        KEY_HELP,
        describe_key_source,
        get_local_env_path,
        get_user_env_path,
        load_primr_env,
        mask_secret,
        normalize_key_name,
        set_user_key,
        unset_user_key,
    )

    argv = args if args is not None else sys.argv[1:]
    parser = create_keys_parser()
    keys_args = argv[1:]
    parsed = parser.parse_args(keys_args or ["list"])

    if parsed.action == "path":
        user_path = get_user_env_path()
        console.info(f"User config: {user_path}")
        local_path = get_local_env_path()
        if local_path:
            console.info(f"Local override: {local_path}")
        return 0

    if parsed.action == "list":
        from primr.config.env import keystore_sandbox_warning

        load_primr_env()
        console.banner("Primr Keys")
        console.info(f"User config: {get_user_env_path()}")
        local_path = get_local_env_path()
        if local_path:
            console.info(f"Local override: {local_path}")
        sandbox = keystore_sandbox_warning()
        if sandbox:
            console.warn(sandbox)
        console.blank()
        for env_name, purpose in KEY_HELP.items():
            active, _source, shadowed = describe_key_source(env_name)
            if active:
                console.ok(f"{env_name} configured ({mask_secret(active)}) - {purpose}")
                if shadowed is not None:
                    console.warn(
                        f"  {env_name} is set by an OS environment variable, overriding the "
                        f".env value ({mask_secret(shadowed)}). Clear the env var for the "
                        f".env file to take effect."
                    )
            else:
                console.info(f"{env_name} not set - {purpose}")
        return 0

    if parsed.action == "set":
        env_name = normalize_key_name(parsed.provider)
        value = parsed.option_value or parsed.provided_value
        if value is None:
            if not can_prompt_for_input():
                console.error("No key value provided and an interactive terminal is unavailable")
                console.info(f"Usage: primr keys set {parsed.provider} --value <key>")
                return 1
            try:
                value = getpass.getpass(f"{env_name}: ")
            except (EOFError, OSError, ValueError):
                console.error("Key input became unavailable before a value was read")
                console.info(f"Usage: primr keys set {parsed.provider} --value <key>")
                return 1
        value = value.strip()
        if not value:
            console.error("Key value cannot be empty")
            return 1

        saved_name, path = set_user_key(parsed.provider, value)
        console.ok(f"{saved_name} saved to user config ({mask_secret(value)})")
        console.info(f"Config file: {path}")
        console.info("Run: primr doctor")
        return 0

    if parsed.action == "test":
        return _run_keys_test(getattr(parsed, "provider", None))

    if parsed.action == "unset":
        env_name, path, removed = unset_user_key(parsed.provider)
        if removed:
            console.ok(f"{env_name} removed from user config")
            if os.environ.get(env_name):
                console.warn(
                    f"{env_name} is still set by your shell or local .env for this process"
                )
        else:
            console.warn(f"{env_name} was not present in user config")
        console.info(f"Config file: {path}")
        return 0

    parser.print_help()
    return 0
