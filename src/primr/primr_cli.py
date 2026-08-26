"""Compatibility module for launching Primr with ``python -m primr.primr_cli``."""

from primr.cli_entry import main

if __name__ == "__main__":
    raise SystemExit(main())
