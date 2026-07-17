"""Dependency-leaf settings for inference routing and host billing consent.

The CLI, capability router, and host transports all need the same process-level
names. Keeping those names and their small normalization helpers here avoids a
core-to-AI import cycle and makes stale per-run consent straightforward to
clear. This module deliberately knows nothing about models, runners, or CLI
configuration objects.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping

INFERENCE_PROFILE_ENV = "PRIMR_INFERENCE_PROFILE"
HOST_AGENT_MAY_BILL_ENV = "PRIMR_ACKNOWLEDGE_HOST_AGENT_MAY_BILL"
EXPERIMENTAL_HOST_PROMOTION_STATUS = "experimental_eval_pending"


def host_agent_may_bill_acknowledged(
    environment: Mapping[str, str] | None = None,
) -> bool:
    """Return whether this process explicitly accepts uncertain host billing.

    Only the exact value ``1`` enables the route. This is intentionally stricter
    than a general truthy parser because the setting authorizes work whose
    billing basis Primr cannot inspect.
    """

    values = os.environ if environment is None else environment
    return values.get(HOST_AGENT_MAY_BILL_ENV) == "1"


def configure_inference_environment(
    inference_profile: str,
    acknowledge_host_agent_may_bill: bool,
    *,
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Apply one run's profile and clear any stale host-billing consent.

    CLI processes can parse and execute more than one command in tests and
    embedded hosts. Removing the consent variable when the current command did
    not opt in prevents a prior run from silently authorizing a later one.
    """

    values = os.environ if environment is None else environment
    values[INFERENCE_PROFILE_ENV] = inference_profile
    if acknowledge_host_agent_may_bill:
        values[HOST_AGENT_MAY_BILL_ENV] = "1"
    else:
        values.pop(HOST_AGENT_MAY_BILL_ENV, None)
