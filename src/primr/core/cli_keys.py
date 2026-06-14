"""The ``primr keys`` subcommand: store and inspect per-user API keys.

Extracted from ``core/cli.py`` to keep that coordinator under the
architecture line ceiling (see ``tests/test_architecture.py``). Wired back
via ``from primr.core.cli_keys import run_keys``.
"""

import argparse
import os
import sys

from primr.utils.console import console


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
        help="Key to set. Common choices: gemini, xai",
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
    return parser


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
            if not sys.stdin.isatty():
                console.error("No key value provided and stdin is not interactive")
                console.info(f"Usage: primr keys set {parsed.provider} --value <key>")
                return 1
            value = getpass.getpass(f"{env_name}: ")
        value = value.strip()
        if not value:
            console.error("Key value cannot be empty")
            return 1

        saved_name, path = set_user_key(parsed.provider, value)
        console.ok(f"{saved_name} saved to user config ({mask_secret(value)})")
        console.info(f"Config file: {path}")
        console.info("Run: primr doctor")
        return 0

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
