"""
Routing layer for primr's LLM stack.

This module is the single source of truth for two questions every caller
eventually has to answer:

1. **Which model should I use for this stage?** — answered by
   :func:`pick_model_for_role`, which inspects the configured environment
   keys and the registered ``ModelConfig`` entries to pick the right model
   for a named *role*. Roles are split into capability classes:

   - ``UTILITY``: scraping summaries, link selection, QA, generic "fast"
     tasks — cheap-and-cheerful stages where 7B-class quality is sufficient.
   - ``WRITING``: bulk section writing, polish, prose generation — the
     largest token-consuming class, where utility-per-dollar matters most.
   - ``REASONING``: gap analysis, workbook generation, cross-validation,
     strategy reasoning — high-leverage stages where model quality drives
     the final report's analytical depth.
   - ``PRO``: legacy alias kept for back-compat with v1.22 call sites.
     Maps to REASONING for default routing.

   The split into WRITING and REASONING is what makes the v1.24.0 sub-$1
   eval possible: we want to test recipes that pair an expensive reasoning
   model (Grok 4.3 cached, o4-mini) with a cheap writing model
   (Gemini 3.1 Flash-Lite, GPT-5.4-nano), and the routing layer needs to
   distinguish those stages so a recipe override can target each independently.

2. **Which provider talks to that model?** — answered by
   :func:`get_provider_for_model`, which maps a model name to the
   :class:`primr.ai.providers.Provider` instance that knows how to call it.

The dispatch in :func:`primr.ai.llm.llm` and :func:`primr.ai.llm._get_model_for_type`
delegates here, so changing routing policy happens in one place.

Eval-mode recipe override (v1.24.0):
   :func:`set_active_eval_recipe` installs a :class:`ProfileRecipe` that
   overrides the default routing. Used by the eval generation runner to make
   one primr run use the recipe of one specific eval profile slot. The
   override is contextvar-scoped so it doesn't leak across concurrent runs.
   Production calls pass through to the default routing unchanged.
"""

from __future__ import annotations

import contextvars
import os
from enum import Enum
from typing import TYPE_CHECKING

from primr.config.models import PrimrModels

if TYPE_CHECKING:
    from primr.ai.providers import Provider
    from primr.core.model_eval import ProfileRecipe


class Role(str, Enum):
    """Capability classes used by the routing layer.

    See module docstring for the rationale behind the split.
    """

    UTILITY = "utility"
    WRITING = "writing"
    REASONING = "reasoning"
    PRO = "pro"  # Legacy alias for REASONING, kept for v1.22 call-site compat


# Legacy ``model_type`` strings → ``Role`` mapping. Kept here so the
# ``llm.py::_get_model_for_type`` shim doesn't need to know about Role
# semantics — it just translates the input it gets.
LEGACY_TYPE_TO_ROLE: dict[str, Role] = {
    "scraping": Role.UTILITY,
    "link_selection": Role.UTILITY,
    "filtering": Role.UTILITY,
    "fast": Role.UTILITY,
    "research": Role.UTILITY,
    "summarization": Role.UTILITY,
    "section_writing": Role.WRITING,
    "report": Role.WRITING,
    "analysis": Role.REASONING,
    "reasoning": Role.REASONING,
}


# =============================================================================
# Eval-mode recipe override (v1.24.0)
# =============================================================================
#
# When the eval generation runner is producing reports for a specific profile
# slot (e.g., grok43-flashlite), it sets the active recipe before invoking
# primr. pick_model_for_role checks the active recipe first; if a role is
# populated in the recipe, that model wins. Otherwise default routing applies.
#
# contextvars makes this safe under asyncio and concurrent runs — each task
# sees only its own override. Production callers never see a recipe override
# and follow the default routing path.

_active_eval_recipe: contextvars.ContextVar[ProfileRecipe | None] = contextvars.ContextVar(
    "_active_eval_recipe", default=None
)


def set_active_eval_recipe(recipe: ProfileRecipe | None) -> contextvars.Token:
    """Install a recipe to override routing for the current execution context.

    Returns a token that can be passed to :func:`reset_active_eval_recipe` to
    restore the prior value. Most callers use the :class:`EvalRecipeOverride`
    context manager instead.

    Args:
        recipe: The recipe to make active, or None to clear.

    Returns:
        A contextvars Token that captures the previous state.
    """
    return _active_eval_recipe.set(recipe)


def reset_active_eval_recipe(token: contextvars.Token) -> None:
    """Restore a prior eval-recipe state by token (from set_active_eval_recipe)."""
    _active_eval_recipe.reset(token)


def get_active_eval_recipe() -> ProfileRecipe | None:
    """Return the currently active recipe override, or None if no override set."""
    return _active_eval_recipe.get()


class EvalRecipeOverride:
    """Context manager that installs a recipe for the duration of a block.

    Usage in the eval generation runner::

        from primr.core.model_eval import get_eval_profile
        from primr.ai.routing import EvalRecipeOverride

        slot = get_eval_profile("grok43-flashlite")
        with EvalRecipeOverride(slot.recipe):
            # All pick_model_for_role calls inside this block return models
            # from slot.recipe instead of the production defaults.
            run_primr(...)
    """

    def __init__(self, recipe: ProfileRecipe | None) -> None:
        self._recipe = recipe
        self._token: contextvars.Token | None = None

    def __enter__(self) -> EvalRecipeOverride:
        self._token = set_active_eval_recipe(self._recipe)
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._token is not None:
            reset_active_eval_recipe(self._token)
            self._token = None


# Maps Role → recipe field name. Recipe entries take precedence over default
# routing when the override is active.
_ROLE_TO_RECIPE_FIELD: dict[Role, str] = {
    Role.UTILITY: "utility",
    Role.WRITING: "writing",
    Role.REASONING: "reasoning",
    Role.PRO: "reasoning",  # PRO is a legacy alias — recipe field is reasoning
}


def pick_model_for_role(role: Role | str) -> str:
    """Pick the right model name for a named role given configured keys.

    Resolution order:

    1. **Active eval recipe override** — if set_active_eval_recipe() has
       installed a :class:`ProfileRecipe` and it has a non-None entry for
       this role, return that model. Used by the eval generation runner to
       make one primr run use a specific profile slot's recipe.
    2. **Default routing by role + env keys** — provider-aware fallback chain
       installed in v1.24.0 once the cross-provider eval picked winners per
       role. The full per-role priority is in the inline comment below;
       summary:

       - UTILITY: GEMINI > OPENAI > ANTHROPIC > XAI > FLASH fallback.
       - WRITING: GEMINI > OPENAI > ANTHROPIC > XAI > PRO fallback.
         (v1.24.0 stage-1 winner: gemini-3.1-flash-lite at $0.79/run.)
       - REASONING / PRO: XAI > GEMINI > OPENAI > ANTHROPIC > PRO fallback.
         (XAI wins on cached-input price when continuous-reasoning session
         lands a high cache hit rate.)
    """
    if isinstance(role, str):
        role = Role(role)

    # 1. Recipe override (eval mode)
    recipe = _active_eval_recipe.get()
    if recipe is not None:
        field = _ROLE_TO_RECIPE_FIELD.get(role)
        if field is not None:
            override_model = getattr(recipe, field, None)
            if override_model:
                return override_model
        # Also check the recipe's extra dict for forward-compat role names
        if recipe.extra:
            extra_model = recipe.extra.get(role.value)
            if extra_model:
                return extra_model

    # 2. Default routing — provider-aware fallback chain (v1.24.0 + v1.24.x)
    #
    # The chain order reflects the v1.24.0 stage 1 eval winner (Gemini +
    # XAI → grok43-flashlite at $0.79) and extends to single-provider
    # configurations so users with only OpenAI or Anthropic keys still get
    # a viable pipeline.
    #
    # Priority logic per role:
    #
    # UTILITY  (scrape summaries, link selection, generic "fast"):
    #   GEMINI > OPENAI > ANTHROPIC > XAI > FLASH_MODEL fallback
    #   Cheapest-per-quality wins; Gemini Flash is the validated default.
    #
    # WRITING  (bulk section writing):
    #   GEMINI > OPENAI > ANTHROPIC > XAI > PRO_MODEL fallback
    #   Same shape as UTILITY but writes use higher-output models.
    #
    # REASONING / PRO  (analysis, workbook, cross-validation, strategy):
    #   XAI > GEMINI > OPENAI > ANTHROPIC > PRO_MODEL fallback
    #   XAI wins because Grok 4.3's $0.20 cached input is unbeatable when
    #   the continuous-reasoning session lands a high cache hit rate.
    #   Without XAI, primr uses each provider's flagship reasoner.

    from primr.config.models import ModelRegistry as _Registry

    if role is Role.UTILITY:
        if os.getenv("GEMINI_API_KEY"):
            return PrimrModels.FLASH_MODEL
        if os.getenv("OPENAI_API_KEY"):
            return _Registry.OPENAI_GPT_5_4_NANO.name
        if os.getenv("ANTHROPIC_API_KEY"):
            return _Registry.ANTHROPIC_HAIKU.name
        if os.getenv("XAI_API_KEY"):
            return PrimrModels.GROK_MODEL_WRITING
        return PrimrModels.FLASH_MODEL

    if role is Role.WRITING:
        # v1.24.0 measured winner: gemini-3.1-flash-lite at $0.79/run on
        # the v1.24.0 stage-1 eval target (vs $3.49 baseline; trust gate
        # PASS; LLM judge score 89.05 vs baseline 79-84). See
        # docs/EVAL_V1_24_0.md.
        if os.getenv("GEMINI_API_KEY"):
            return _Registry.GEMINI_3_1_FLASH_LITE.name
        # OpenAI fallback: gpt-5.4-nano is the cheapest cross-provider writer
        # ($0.20/$1.25). Verified working at $0.78/run in eval as grok43-nano.
        # 16K output cap may force per-section sizing on long reports.
        if os.getenv("OPENAI_API_KEY"):
            return _Registry.OPENAI_GPT_5_4_NANO.name
        # Anthropic fallback: Haiku 4.5 ($1.00/$5.00). Not directly measured
        # in v1.24.0 (eval cell hung in pre-validation) but registered as a
        # viable mid-cost writer for Anthropic-only users.
        if os.getenv("ANTHROPIC_API_KEY"):
            return _Registry.ANTHROPIC_HAIKU.name
        # XAI-only legacy path: Grok 4.20-NR. ~$4.27/run on the standard
        # corpus. Kept for users who don't want the Gemini dependency.
        if os.getenv("XAI_API_KEY"):
            return PrimrModels.GROK_MODEL_WRITING
        return PrimrModels.PRO_MODEL

    # Role.REASONING and Role.PRO
    # XAI wins universally — Grok 4.3 with $0.20 cached input is the cheapest
    # reasoning flagship across providers. Without XAI, fall through to the
    # next available provider's flagship reasoner.
    if os.getenv("XAI_API_KEY"):
        return PrimrModels.GROK_MODEL_43
    if os.getenv("GEMINI_API_KEY"):
        return PrimrModels.PRO_MODEL
    if os.getenv("OPENAI_API_KEY"):
        return _Registry.OPENAI_O4_MINI.name
    if os.getenv("ANTHROPIC_API_KEY"):
        return _Registry.ANTHROPIC_SONNET.name
    return PrimrModels.PRO_MODEL


def pick_model_for_legacy_type(model_type: str) -> str:
    """Translate a legacy ``model_type`` string into a model name."""
    role = LEGACY_TYPE_TO_ROLE.get(model_type, Role.UTILITY)
    return pick_model_for_role(role)


# ---------------------------------------------------------------------------
# Provider lookup
# ---------------------------------------------------------------------------

# Module-level cached provider instances (singletons)
_openai_provider: Provider | None = None
_anthropic_provider: Provider | None = None
_ollama_provider: Provider | None = None


def _get_openai_provider() -> Provider:
    """Return a cached OpenAI provider instance."""
    global _openai_provider
    if _openai_provider is None:
        from primr.ai.providers.openai_compatible import OpenAICompatibleProvider

        _openai_provider = OpenAICompatibleProvider(
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
        )
    return _openai_provider


def _get_anthropic_provider() -> Provider:
    """Return a cached Anthropic provider instance."""
    global _anthropic_provider
    if _anthropic_provider is None:
        from primr.ai.providers.anthropic import AnthropicProvider

        _anthropic_provider = AnthropicProvider()
    return _anthropic_provider


def _get_ollama_provider() -> Provider:
    """Return a cached Ollama provider instance.

    Respects OLLAMA_BASE_URL env var for non-default Ollama endpoints.
    Falls back to http://localhost:11434/v1.
    """
    global _ollama_provider
    if _ollama_provider is None:
        from primr.ai.providers.openai_compatible import OpenAICompatibleProvider

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"

        _ollama_provider = OpenAICompatibleProvider(
            name="ollama",
            base_url=base_url,
            api_key_env="OLLAMA_API_KEY",
            api_key_default="ollama",
        )
    return _ollama_provider


def get_provider_for_model(model_name: str) -> Provider:
    """Return the provider instance that knows how to call ``model_name``.

    Looks up the model's provider field in the ``ModelRegistry`` and returns
    the matching singleton. Raises ``KeyError`` for unregistered model names
    and ``ValueError`` for registered models whose provider has no routing
    entry yet.
    """
    config = PrimrModels.get_model_config(model_name)
    if config is None:
        raise KeyError(f"Unknown model: {model_name}")

    provider_name = config.provider
    if provider_name == "xai":
        from primr.ai.grok_client import _get_provider

        return _get_provider()
    if provider_name == "google":
        from primr.ai.llm import _get_gemini_provider

        return _get_gemini_provider()
    if provider_name == "openai":
        return _get_openai_provider()
    if provider_name == "anthropic":
        return _get_anthropic_provider()
    if provider_name == "ollama":
        return _get_ollama_provider()

    raise ValueError(
        f"Model {model_name!r} has provider {provider_name!r} which has no "
        "routing entry. Register it in primr.ai.routing.get_provider_for_model."
    )
