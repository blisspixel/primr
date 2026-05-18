#!/usr/bin/env python3
"""
API Key Rotation Utility

Rotates Google Cloud API keys and updates .env file.
Gemini (AI Studio) keys must be rotated manually at https://aistudio.google.com/apikey

Usage:
    python scripts/rotate_keys.py              # Interactive mode
    python scripts/rotate_keys.py --search     # Rotate Search API key only
    python scripts/rotate_keys.py --list       # List existing keys
    python scripts/rotate_keys.py --help       # Show help

Requirements:
    - gcloud CLI installed and authenticated
    - Run: gcloud auth login
    - Run: gcloud config set project YOUR_PROJECT_ID
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def run_gcloud(args: list[str], capture: bool = True) -> tuple[int, str, str]:
    """Run a gcloud command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["gcloud", *args],
            capture_output=capture,
            text=True,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return 1, "", "gcloud CLI not found. Install from https://cloud.google.com/sdk/docs/install"


def check_gcloud_auth() -> bool:
    """Check if gcloud is authenticated."""
    code, out, err = run_gcloud(
        ["auth", "list", "--filter=status:ACTIVE", "--format=value(account)"]
    )
    if code != 0 or not out:
        print("❌ Not authenticated with gcloud")
        print("   Run: gcloud auth login")
        return False
    print(f"✓ Authenticated as: {out}")
    return True


def get_project() -> str | None:
    """Get current gcloud project."""
    code, out, err = run_gcloud(["config", "get-value", "project"])
    if code != 0 or not out:
        print("❌ No project set")
        print("   Run: gcloud config set project YOUR_PROJECT_ID")
        return None
    print(f"✓ Project: {out}")
    return out


def list_api_keys() -> list[dict]:
    """List all API keys in the project."""
    code, out, err = run_gcloud(
        ["services", "api-keys", "list", "--format=csv[no-heading](name,displayName,createTime)"]
    )
    if code != 0:
        print(f"❌ Failed to list keys: {err}")
        return []

    keys = []
    for line in out.split("\n"):
        if line:
            parts = line.split(",")
            if len(parts) >= 2:
                keys.append(
                    {
                        "id": parts[0],
                        "name": parts[1] if len(parts) > 1 else "unnamed",
                        "created": parts[2] if len(parts) > 2 else "unknown",
                    }
                )
    return keys


def get_key_string(key_id: str) -> str | None:
    """Get the actual key string for a key ID."""
    code, out, err = run_gcloud(
        ["services", "api-keys", "get-key-string", key_id, "--format=value(keyString)"]
    )
    if code != 0:
        print(f"❌ Failed to get key string: {err}")
        return None
    return out


def create_api_key(display_name: str, restrict_to_api: str | None = None) -> tuple[str, str] | None:
    """Create a new API key. Returns (key_id, key_string) or None."""
    args = [
        "services",
        "api-keys",
        "create",
        f"--display-name={display_name}",
        "--format=value(name)",
    ]

    print(f"Creating new key '{display_name}'...")
    code, key_id, err = run_gcloud(args)
    if code != 0:
        print(f"❌ Failed to create key: {err}")
        return None

    # Get the key string
    key_string = get_key_string(key_id)
    if not key_string:
        return None

    # Optionally restrict to specific API. Fail closed: a key that the
    # caller asked to be restricted but which silently came back
    # unrestricted is over-permissive and must not flow into .env. We
    # tear it down and return None so the rotation as a whole fails.
    if restrict_to_api:
        print(f"Restricting key to {restrict_to_api}...")
        code, _, err = run_gcloud(
            ["services", "api-keys", "update", key_id, f"--api-target=service={restrict_to_api}"]
        )
        if code != 0:
            print(f"❌ Failed to restrict key: {err}")
            print("  Deleting just-created unrestricted key to avoid leaving it deployable...")
            run_gcloud(["services", "api-keys", "delete", key_id, "--quiet"])
            return None

    return key_id, key_string


def delete_api_key(key_id: str) -> bool:
    """Delete an API key."""
    code, _, err = run_gcloud(["services", "api-keys", "delete", key_id, "--quiet"])
    if code != 0:
        print(f"❌ Failed to delete key: {err}")
        return False
    return True


def update_env_file(key_name: str, new_value: str) -> bool:
    """Update a key in the .env file."""
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env file not found")
        return False

    content = env_path.read_text()
    pattern = rf"^{re.escape(key_name)}=.*$"

    if re.search(pattern, content, re.MULTILINE):
        new_content = re.sub(pattern, f"{key_name}={new_value}", content, flags=re.MULTILINE)
        env_path.write_text(new_content)
        print(f"✓ Updated {key_name} in .env")
        return True
    else:
        print(f"⚠ {key_name} not found in .env, appending...")
        with open(env_path, "a") as f:
            f.write(f"\n{key_name}={new_value}\n")
        return True


def rotate_search_key(old_key_id: str | None = None) -> bool:
    """Rotate the Google Custom Search API key."""
    print("\n=== Rotating Search API Key ===\n")

    # Create new key
    result = create_api_key("primr-search", restrict_to_api="customsearch.googleapis.com")
    if not result:
        return False

    new_key_id, new_key_string = result
    print(f"✓ Created new key: {new_key_id[-12:]}")

    # Update .env
    if not update_env_file("SEARCH_API_KEY", new_key_string):
        print("⚠ Remember to manually update SEARCH_API_KEY in .env")

    # Delete old key if provided. Fail closed: a rotation that leaves the
    # old credential alive is no rotation at all. Caller is expected to
    # delete out-of-band, so we surface failure rather than print success.
    if old_key_id:
        print(f"Deleting old key: {old_key_id[-12:]}...")
        if not delete_api_key(old_key_id):
            print("❌ Failed to delete old key. Revoke it manually before declaring rotation done.")
            return False
        print("✓ Old key deleted")

    print("\n✓ Search API key rotated successfully")
    return True


def interactive_mode():
    """Interactive key rotation."""
    print("=" * 50)
    print("Primr API Key Rotation Utility")
    print("=" * 50)

    # Check prerequisites
    if not check_gcloud_auth():
        return 1

    project = get_project()
    if not project:
        return 1

    print("\n--- Current API Keys ---")
    keys = list_api_keys()
    if keys:
        for i, key in enumerate(keys):
            print(f"  [{i + 1}] {key['name']} (created: {key['created'][:10]})")
    else:
        print("  No keys found")

    print("\n--- Options ---")
    print("  [1] Rotate Search API key (creates new, updates .env, deletes old)")
    print("  [2] Create new Search API key only")
    print("  [3] List keys and exit")
    print("  [4] Exit")
    print("\n⚠ Gemini API keys must be rotated manually at:")
    print("   https://aistudio.google.com/apikey")

    choice = input("\nChoice [1-4]: ").strip()

    if choice == "1":
        # Find existing search key
        search_keys = [k for k in keys if "search" in k["name"].lower()]
        old_key_id = None
        if search_keys:
            print(f"\nFound existing search key: {search_keys[0]['name']}")
            if input("Delete after rotation? [y/N]: ").lower() == "y":
                old_key_id = search_keys[0]["id"]

        return 0 if rotate_search_key(old_key_id) else 1

    elif choice == "2":
        result = create_api_key("primr-search", "customsearch.googleapis.com")
        if result:
            _, key_string = result
            print("\n✓ New key created!")
            print(f"  Add to .env: SEARCH_API_KEY={key_string}")
            return 0
        return 1

    elif choice == "3":
        return 0

    else:
        print("Exiting.")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Rotate Google Cloud API keys for Primr",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/rotate_keys.py              # Interactive mode
    python scripts/rotate_keys.py --search     # Rotate Search API key
    python scripts/rotate_keys.py --list       # List existing keys

Note: Gemini API keys must be rotated manually at https://aistudio.google.com/apikey
        """,
    )
    parser.add_argument("--search", action="store_true", help="Rotate Search API key")
    parser.add_argument("--list", action="store_true", help="List existing API keys")
    parser.add_argument("--delete", metavar="KEY_ID", help="Delete a specific key by ID")

    args = parser.parse_args()

    # Check gcloud first
    code, _, err = run_gcloud(["--version"])
    if code != 0:
        print("❌ gcloud CLI not found")
        print("   Install from: https://cloud.google.com/sdk/docs/install")
        return 1

    if args.list:
        if not check_gcloud_auth() or not get_project():
            return 1
        print("\n--- API Keys ---")
        for key in list_api_keys():
            print(f"  {key['name']}: {key['id']}")
        return 0

    if args.delete:
        if not check_gcloud_auth() or not get_project():
            return 1
        return 0 if delete_api_key(args.delete) else 1

    if args.search:
        if not check_gcloud_auth() or not get_project():
            return 1
        return 0 if rotate_search_key() else 1

    # Default: interactive mode
    return interactive_mode()


if __name__ == "__main__":
    sys.exit(main())
