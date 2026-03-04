"""Primr A2A (Agent-to-Agent) protocol integration with lazy loading.

Requires optional dependency: pip install primr[a2a]
"""

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    # types.py
    "ExternalAgentConfig": ("primr.a2a.types", "ExternalAgentConfig"),
    "A2ATaskMapping": ("primr.a2a.types", "A2ATaskMapping"),
    # client.py
    "A2AClient": ("primr.a2a.client", "A2AClient"),
    # hooks.py
    "A2AExternalAgentHook": ("primr.a2a.hooks", "A2AExternalAgentHook"),
    "A2AContentSanitizationHook": ("primr.a2a.hooks", "A2AContentSanitizationHook"),
    # agent_card.py
    "build_agent_card": ("primr.a2a.agent_card", "build_agent_card"),
    # task_store.py
    "PrimrTaskStore": ("primr.a2a.task_store", "PrimrTaskStore"),
    # executor.py
    "PrimrAgentExecutor": ("primr.a2a.executor", "PrimrAgentExecutor"),
    # server.py
    "PrimrA2AServer": ("primr.a2a.server", "PrimrA2AServer"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'primr.a2a' has no attribute '{name}'")
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
