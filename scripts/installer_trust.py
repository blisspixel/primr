"""Hash-verified pip bootstrap for the source-checkout setup wizard.

The application certificate bundle and pip's vendored trust store are separate.
Source: https://discuss.python.org/t/109576
"""

from __future__ import annotations

import re
import subprocess
import sys
from importlib import metadata

# Official Python incident notice: hash verification also protects bootstrap
# downloads made by an older pip with an affected vendored CA bundle.
PATCHED_PIP_URL = (
    "https://files.pythonhosted.org/packages/3f/06/"
    "3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/"
    "pip-26.2.2-py3-none-any.whl"
    "#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
)


def ensure_patched_installer() -> None:
    """Repair pip before any index download; failure stops the setup flow."""
    try:
        version = metadata.version("pip")
    except metadata.PackageNotFoundError:
        version = "0"
    parsed = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", version)
    if parsed and tuple(int(part or 0) for part in parsed.groups()) >= (26, 2, 2):
        return
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "--no-cache-dir", PATCHED_PIP_URL],
        check=True,
    )
