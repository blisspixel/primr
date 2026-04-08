#!/usr/bin/env python3
"""
Google Custom Search API Setup

Provisions the SEARCH_API_KEY and SEARCH_ENGINE_ID needed by Primr,
using the gcloud CLI and Google APIs.

Steps performed:
  1. Verify gcloud CLI is available and authenticated
  2. Enable Custom Search API on the project
  3. Create a restricted API key (Custom Search only)
  4. Create a Programmable Search Engine (whole-web)
  5. Write both values to .env

Usage:
    python scripts/setup_search_api.py
    python scripts/setup_search_api.py --project primr-485912
    python scripts/setup_search_api.py --dry-run
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_PROJECT = "primr-485912"
CUSTOM_SEARCH_SERVICE = "customsearch.googleapis.com"


def _find_gcloud() -> str:
    """Find the gcloud executable, handling Windows .cmd extension."""
    import shutil

    path = shutil.which("gcloud")
    if path:
        return path
    # Windows: try gcloud.cmd explicitly
    if sys.platform == "win32":
        path = shutil.which("gcloud.cmd")
        if path:
            return path
    return "gcloud"


GCLOUD_CMD = _find_gcloud()


def run_gcloud(args: list[str], *, check: bool = True, capture: bool = True) -> str:
    """Run a gcloud command and return stdout."""
    cmd = [GCLOUD_CMD, *args]
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=60,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        raise RuntimeError(f"gcloud command failed: {' '.join(args)}\n{stderr}")
    return result.stdout.strip() if result.stdout else ""


def check_gcloud() -> str:
    """Verify gcloud is installed and authenticated. Returns the active account."""
    try:
        version = run_gcloud(["--version"])
    except (FileNotFoundError, RuntimeError):
        print("ERROR: gcloud CLI not found. Install from https://cloud.google.com/sdk/docs/install")
        sys.exit(1)

    first_line = version.splitlines()[0] if version else "unknown"
    print(f"  gcloud: {first_line}")

    account = run_gcloud(["auth", "list", "--format=value(account)", "--filter=status:ACTIVE"])
    if not account:
        print("ERROR: No active gcloud account. Run: gcloud auth login")
        sys.exit(1)

    print(f"  Account: {account}")
    return account


def verify_project(project_id: str) -> None:
    """Verify the project exists and we have access."""
    try:
        run_gcloud(["projects", "describe", project_id, "--format=value(projectId)"])
        print(f"  Project: {project_id}")
    except RuntimeError as e:
        print(f"ERROR: Cannot access project '{project_id}'.\n{e}")
        sys.exit(1)


def enable_api(project_id: str) -> None:
    """Enable the Custom Search API."""
    # Check if already enabled
    enabled = run_gcloud(
        [
            "services",
            "list",
            f"--project={project_id}",
            "--enabled",
            "--format=value(config.name)",
            f"--filter=config.name:{CUSTOM_SEARCH_SERVICE}",
        ]
    )
    if CUSTOM_SEARCH_SERVICE in enabled:
        print("  Custom Search API: already enabled")
        return

    print("  Enabling Custom Search API...", end=" ", flush=True)
    run_gcloud(
        [
            "services",
            "enable",
            CUSTOM_SEARCH_SERVICE,
            f"--project={project_id}",
        ]
    )
    print("done")


def create_api_key(project_id: str) -> str:
    """Create an API key restricted to Custom Search API only. Returns the key string."""
    display_name = "primr-search"

    # Check for existing primr-search key
    existing = run_gcloud(
        [
            "services",
            "api-keys",
            "list",
            f"--project={project_id}",
            "--format=json",
        ]
    )
    if existing:
        keys = json.loads(existing)
        for key in keys:
            if key.get("displayName") == display_name:
                uid = key["uid"]
                print(f"  Found existing key '{display_name}' (uid: {uid})")
                key_string = run_gcloud(
                    [
                        "services",
                        "api-keys",
                        "get-key-string",
                        key["name"],
                    ]
                )
                # Output is "keyString: <value>"
                match = re.search(r"keyString:\s*(.+)", key_string)
                if match:
                    return match.group(1).strip()
                return key_string.strip()

    # Create new key
    print(f"  Creating restricted API key '{display_name}'...", end=" ", flush=True)
    result = run_gcloud(
        [
            "services",
            "api-keys",
            "create",
            f"--project={project_id}",
            f"--display-name={display_name}",
            f"--api-target=service={CUSTOM_SEARCH_SERVICE}",
            "--format=json",
        ]
    )
    print("done")

    # The create command returns an operation; extract the key name
    op = json.loads(result) if result else {}
    key_name = op.get("response", {}).get("name", "")

    if not key_name:
        # List keys and find the one we just created
        keys_json = run_gcloud(
            [
                "services",
                "api-keys",
                "list",
                f"--project={project_id}",
                "--format=json",
            ]
        )
        keys = json.loads(keys_json) if keys_json else []
        for key in keys:
            if key.get("displayName") == display_name:
                key_name = key["name"]
                break

    if not key_name:
        print("ERROR: Key created but could not retrieve key name.")
        print("  Check https://console.cloud.google.com/apis/credentials")
        sys.exit(1)

    # Get the actual key string
    key_string_raw = run_gcloud(
        [
            "services",
            "api-keys",
            "get-key-string",
            key_name,
        ]
    )
    match = re.search(r"keyString:\s*(.+)", key_string_raw)
    key_string = match.group(1).strip() if match else key_string_raw.strip()

    print("  Key created and restricted to Custom Search API only")
    return key_string


def create_search_engine(api_key: str) -> str:
    """Create a Programmable Search Engine via the CSE API. Returns the search engine ID (cx)."""
    try:
        import httpx
    except ImportError as err:
        # Fall back to urllib

        # We can't create a CSE via the search API alone.
        # Use the cse.url.list endpoint to see if any exist.
        # Fall through to manual instructions.
        raise ImportError("httpx not available") from err

    # The Programmable Search Engine can be created via the
    # www.googleapis.com/customsearch/v1/cse endpoint, but that requires OAuth.
    # Instead, use the newer JSON API approach to list existing engines.

    # Try to find an existing "whole web" engine via the API
    # This endpoint requires OAuth, so we'll use gcloud's access token
    access_token = run_gcloud(["auth", "print-access-token"])

    # List existing search engines
    response = httpx.get(
        "https://www.googleapis.com/customsearch/v1/cse/list",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )

    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])
        for item in items:
            name = item.get("title", "") or item.get("name", "")
            cx = item.get("id", "")
            if cx:
                print(f"  Found existing search engine: '{name}' (cx: {cx})")
                return cx

    # Create a new whole-web search engine
    payload = {
        "title": "Primr Research",
        "language": "en",
        "webSearchProperties": {
            "searchTheWeb": True,
        },
    }
    response = httpx.post(
        "https://www.googleapis.com/customsearch/v1/cse",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )

    if response.status_code in (200, 201):
        data = response.json()
        cx = data.get("id", "")
        if cx:
            print(f"  Created search engine 'Primr Research' (cx: {cx})")
            return cx

    # If API creation fails, try alternate endpoint format
    payload_alt = {
        "title": "Primr Research",
        "oq": "",
        "cx_readonly": False,
    }
    response = httpx.post(
        "https://cse.google.com/api/create_cse",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload_alt,
        timeout=15,
    )

    if response.status_code in (200, 201):
        data = response.json()
        cx = data.get("id", "") or data.get("cx", "")
        if cx:
            print(f"  Created search engine (cx: {cx})")
            return cx

    return ""


def prompt_for_search_engine_id() -> str:
    """Interactively guide user to create a Search Engine ID."""
    print()
    print("  === Search Engine ID (manual step) ===")
    print()
    print("  The Search Engine ID must be created in the Programmable Search Engine console.")
    print("  This takes about 30 seconds:")
    print()
    print("  1. Open: https://programmablesearchengine.google.com/controlpanel/create")
    print('  2. Under "What to search": select "Search the entire web"')
    print('  3. Name it: "Primr Research"')
    print("  4. Click Create")
    print("  5. Copy the Search Engine ID from the overview page")
    print()

    # Try to open the browser
    try:
        import webbrowser

        webbrowser.open("https://programmablesearchengine.google.com/controlpanel/create")
        print("  (Opened browser to the creation page)")
        print()
    except Exception:
        pass

    cx = input("  Paste your Search Engine ID here (or Enter to skip): ").strip()
    return cx


def update_env_file(key_name: str, key_value: str) -> None:
    """Update or add a key in the .env file."""
    if not key_value:
        return

    if not ENV_FILE.exists():
        # Copy from .env.example if available
        example = PROJECT_ROOT / ".env.example"
        if example.exists():
            ENV_FILE.write_text(example.read_text())
            print("  Created .env from .env.example")
        else:
            ENV_FILE.write_text("")

    content = ENV_FILE.read_text()
    pattern = rf"^{re.escape(key_name)}=.*$"

    if re.search(pattern, content, re.MULTILINE):
        # Replace existing value
        content = re.sub(pattern, f"{key_name}={key_value}", content, flags=re.MULTILINE)
    else:
        # Append
        if not content.endswith("\n"):
            content += "\n"
        content += f"{key_name}={key_value}\n"

    ENV_FILE.write_text(content)
    print(f"  .env: {key_name} updated")


def verify_with_doctor() -> None:
    """Run primr doctor to verify the setup."""
    print("\n--- Verification ---\n")
    try:
        subprocess.run(
            [sys.executable, "-m", "primr", "doctor"],
            cwd=str(PROJECT_ROOT),
            timeout=60,
        )
    except Exception as e:
        print(f"  Could not run primr doctor: {e}")
        print("  Run manually: primr doctor")


def main():
    parser = argparse.ArgumentParser(description="Set up Google Custom Search API for Primr")
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"GCP project ID (default: {DEFAULT_PROJECT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--skip-cse",
        action="store_true",
        help="Skip Search Engine ID creation (set up API key only)",
    )
    args = parser.parse_args()

    print("Primr Search API Setup")
    print("=" * 40)

    if args.dry_run:
        print("(DRY RUN - no changes will be made)\n")

    # Step 1: Check gcloud
    print("\n[1/5] Checking gcloud CLI")
    check_gcloud()

    # Step 2: Verify project
    print("\n[2/5] Verifying project")
    verify_project(args.project)

    if args.dry_run:
        print(f"\n[3/5] Would enable: {CUSTOM_SEARCH_SERVICE}")
        print("\n[4/5] Would create API key restricted to Custom Search")
        print("\n[5/5] Would update .env with SEARCH_API_KEY and SEARCH_ENGINE_ID")
        print("\nDry run complete. Run without --dry-run to apply.")
        return

    # Step 3: Enable API
    print("\n[3/5] Custom Search API")
    enable_api(args.project)

    # Step 4: Create API key
    print("\n[4/5] API Key")
    api_key = create_api_key(args.project)
    update_env_file("SEARCH_API_KEY", api_key)

    # Step 5: Search Engine ID
    print("\n[5/5] Search Engine ID")
    cx = ""

    if not args.skip_cse:
        # Try programmatic creation first
        try:
            cx = create_search_engine(api_key)
        except Exception:
            pass  # Fall through to manual

        if not cx:
            cx = prompt_for_search_engine_id()

        if cx:
            update_env_file("SEARCH_ENGINE_ID", cx)
        else:
            print("  Skipped - you can add SEARCH_ENGINE_ID to .env later")
            print("  Create at: https://programmablesearchengine.google.com/controlpanel/create")

    # Verify
    print("\n" + "=" * 40)
    print("Setup complete!")
    print(f"  SEARCH_API_KEY: {'configured' if api_key else 'MISSING'}")
    print(f"  SEARCH_ENGINE_ID: {'configured' if cx else 'MISSING - add to .env'}")

    if api_key:
        verify_with_doctor()


if __name__ == "__main__":
    main()
