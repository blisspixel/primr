"""Compatibility imports for the lightweight CLI help surface."""

from primr.cli_help import (
    ROOT_HELP,
    _create_scoped_help_parser,
    add_init_doctor_arguments,
    maybe_print_root_help,
    maybe_print_scoped_help,
)

__all__ = [
    "ROOT_HELP",
    "_create_scoped_help_parser",
    "add_init_doctor_arguments",
    "maybe_print_root_help",
    "maybe_print_scoped_help",
]
