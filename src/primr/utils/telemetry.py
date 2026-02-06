"""
OpenTelemetry-based telemetry system for distributed tracing.

This module provides:
- TelemetryConfig for configuration
- TelemetrySystem for tracer initialization and span management
- span() context manager for creating traced spans
- record_event() for recording significant operations
- Async context propagation for correlation_id

The telemetry system is opt-in and works gracefully when OpenTelemetry
is not installed. When disabled or unavailable, all operations become
no-ops without affecting application behavior.

Example:
    from primr.utils.telemetry import TelemetrySystem, TelemetryConfig

    # Initialize with configuration
    config = TelemetryConfig(enabled=True, service_name="primr")
    telemetry = TelemetrySystem(config)

    # Create spans for operations
    with telemetry.span("scrape_page", phase="scraping") as span:
        result = scrape_url(url)
        telemetry.record_event("page_scraped", {"url": url, "size": len(result)})

    # Async context propagation
    async with telemetry.async_span("ai_call", phase="generation") as span:
        response = await call_ai_api()
"""

from __future__ import annotations

import contextvars
import logging
import traceback
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

logger = logging.getLogger(__name__)

# Try to import OpenTelemetry - it's an optional dependency
_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )
    from opentelemetry.trace import Span as OTelSpan
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    _OTEL_AVAILABLE = True
except ImportError:
    # OpenTelemetry not installed - telemetry will be disabled
    trace = None  # type: ignore
    TracerProvider = None  # type: ignore
    BatchSpanProcessor = None  # type: ignore
    ConsoleSpanExporter = None  # type: ignore
    SimpleSpanProcessor = None  # type: ignore
    Resource = None  # type: ignore
    Status = None  # type: ignore
    StatusCode = None  # type: ignore
    OTelSpan = None  # type: ignore
    TraceContextTextMapPropagator = None  # type: ignore


# =============================================================================
# EXPORTER TYPE ENUM
# =============================================================================

class ExporterType(str, Enum):
    """Supported telemetry exporter types."""
    CONSOLE = "console"
    OTLP = "otlp"
    JAEGER = "jaeger"
    NONE = "none"


# =============================================================================
# TELEMETRY CONFIGURATION
# =============================================================================

@dataclass
class TelemetryConfig:
    """
    Configuration for the telemetry system.

    Attributes:
        enabled: Whether telemetry is enabled (default: False for opt-in)
        service_name: Name of the service for tracing (default: "primr")
        exporter_type: Type of span exporter (console, otlp, jaeger, none)
        otlp_endpoint: Endpoint for OTLP exporter (default: localhost:4317)
        sampling_rate: Fraction of traces to sample (0.0-1.0, default: 1.0)

    Example:
        config = TelemetryConfig(
            enabled=True,
            service_name="primr-research",
            exporter_type="otlp",
            otlp_endpoint="http://jaeger:4317",
            sampling_rate=0.5
        )
    """

    enabled: bool = False  # Opt-in by default
    service_name: str = "primr"
    exporter_type: str = "console"
    otlp_endpoint: str = "http://localhost:4317"
    sampling_rate: float = 1.0

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 <= self.sampling_rate <= 1.0:
            raise ValueError(f"sampling_rate must be between 0.0 and 1.0, got {self.sampling_rate}")

        # Validate exporter_type
        valid_types = {e.value for e in ExporterType}
        if self.exporter_type not in valid_types:
            raise ValueError(
                f"exporter_type must be one of {valid_types}, got {self.exporter_type}"
            )


# =============================================================================
# NULL SPAN (for when telemetry is disabled)
# =============================================================================

class NullSpan:
    """
    A no-op span implementation for when telemetry is disabled.

    This allows code to use the span API without checking if telemetry
    is enabled at every call site.
    """

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op: Set an attribute on the span."""

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        """No-op: Set multiple attributes on the span."""

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """No-op: Add an event to the span."""

    def record_exception(
        self,
        exception: BaseException,
        attributes: dict[str, Any] | None = None,
        timestamp: int | None = None,
        escaped: bool = False
    ) -> None:
        """No-op: Record an exception on the span."""

    def set_status(self, status: Any, description: str | None = None) -> None:
        """No-op: Set the status of the span."""

    def is_recording(self) -> bool:
        """Return False since this is a null span."""
        return False

    def get_span_context(self) -> None:
        """Return None since this is a null span."""
        return None


# =============================================================================
# CONTEXT VARIABLE FOR ASYNC PROPAGATION
# =============================================================================

# Context variable for propagating correlation_id across async boundaries
_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'correlation_id', default=None
)


def get_async_correlation_id() -> str | None:
    """
    Get the correlation ID from async context.

    Returns:
        The correlation ID if set in async context, None otherwise.
    """
    return _correlation_id_var.get()


def set_async_correlation_id(correlation_id: str) -> contextvars.Token[str | None]:
    """
    Set the correlation ID in async context.

    Args:
        correlation_id: The correlation ID to set.

    Returns:
        A token that can be used to reset the context variable.
    """
    return _correlation_id_var.set(correlation_id)


def reset_async_correlation_id(token: contextvars.Token[str | None]) -> None:
    """
    Reset the correlation ID to its previous value.

    Args:
        token: The token returned by set_async_correlation_id.
    """
    _correlation_id_var.reset(token)


# =============================================================================
# TELEMETRY SYSTEM
# =============================================================================

class TelemetrySystem:
    """
    OpenTelemetry-based observability system.

    Provides distributed tracing with automatic correlation ID injection,
    error recording, and support for multiple exporters.

    The system is designed to be opt-in and gracefully handles the case
    where OpenTelemetry is not installed.

    Attributes:
        config: Telemetry configuration

    Example:
        telemetry = TelemetrySystem(TelemetryConfig(enabled=True))

        with telemetry.span("operation", phase="processing") as span:
            # Do work
            telemetry.record_event("checkpoint", {"step": 1})
    """

    def __init__(self, config: TelemetryConfig | None = None) -> None:
        """
        Initialize the telemetry system.

        Args:
            config: Telemetry configuration. If None, uses defaults (disabled).
        """
        self.config = config or TelemetryConfig()
        self._tracer: Any = None
        self._provider: Any = None
        self._initialized = False

        if self.config.enabled and _OTEL_AVAILABLE:
            self._initialize_tracer()

    def _initialize_tracer(self) -> None:
        """Initialize the OpenTelemetry tracer with configured exporter."""
        if not _OTEL_AVAILABLE:
            logger.warning(
                "OpenTelemetry not installed. Telemetry will be disabled. "
                "Install with: pip install opentelemetry-api opentelemetry-sdk"
            )
            return

        try:
            # Create resource with service name
            resource = Resource.create({
                "service.name": self.config.service_name,
            })

            # Create tracer provider
            self._provider = TracerProvider(resource=resource)

            # Add exporter based on configuration
            exporter = self._create_exporter()
            if exporter is not None:
                # Use SimpleSpanProcessor for console (immediate output)
                # Use BatchSpanProcessor for network exporters (better performance)
                if self.config.exporter_type == ExporterType.CONSOLE.value:
                    processor = SimpleSpanProcessor(exporter)
                else:
                    processor = BatchSpanProcessor(exporter)
                self._provider.add_span_processor(processor)

            # Set as global tracer provider
            trace.set_tracer_provider(self._provider)

            # Get tracer
            self._tracer = trace.get_tracer(
                self.config.service_name,
                schema_url="https://opentelemetry.io/schemas/1.21.0"
            )

            self._initialized = True
            logger.debug(
                f"Telemetry initialized with {self.config.exporter_type} exporter"
            )

        except Exception as e:
            logger.warning(f"Failed to initialize telemetry: {e}")
            self._tracer = None
            self._initialized = False

    def _create_exporter(self) -> Any:
        """Create the appropriate span exporter based on configuration."""
        if not _OTEL_AVAILABLE:
            return None

        exporter_type = self.config.exporter_type

        if exporter_type == ExporterType.CONSOLE.value:
            return ConsoleSpanExporter()

        elif exporter_type == ExporterType.OTLP.value:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                return OTLPSpanExporter(endpoint=self.config.otlp_endpoint)
            except ImportError:
                logger.warning(
                    "OTLP exporter not available. Install with: "
                    "pip install opentelemetry-exporter-otlp"
                )
                return ConsoleSpanExporter()

        elif exporter_type == ExporterType.JAEGER.value:
            try:
                from opentelemetry.exporter.jaeger.thrift import JaegerExporter
                return JaegerExporter()
            except ImportError:
                logger.warning(
                    "Jaeger exporter not available. Install with: "
                    "pip install opentelemetry-exporter-jaeger"
                )
                return ConsoleSpanExporter()

        elif exporter_type == ExporterType.NONE.value:
            return None

        else:
            logger.warning(f"Unknown exporter type: {exporter_type}, using console")
            return ConsoleSpanExporter()

    @property
    def is_enabled(self) -> bool:
        """Check if telemetry is enabled and initialized."""
        return self.config.enabled and self._initialized and self._tracer is not None

    def _get_correlation_id(self) -> str:
        """
        Get the current correlation ID from context.

        Checks async context first, then falls back to thread-local context.

        Returns:
            The current correlation ID or a generated one.
        """
        # First check async context
        async_corr_id = get_async_correlation_id()
        if async_corr_id is not None:
            return async_corr_id

        # Fall back to observability module
        try:
            from primr.utils.observability import get_correlation_id
            return get_correlation_id()
        except ImportError:
            import uuid
            return str(uuid.uuid4())[:8]

    @contextmanager
    def span(
        self,
        name: str,
        phase: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[NullSpan | Any, None, None]:
        """
        Create a traced span for an operation.

        The span automatically includes correlation_id and operation name.
        If a phase is provided, it's also included as an attribute.
        Exceptions raised within the span are automatically recorded.

        Args:
            name: Name of the operation (becomes the span name)
            phase: Optional pipeline phase (scraping, generation, output)
            attributes: Optional additional attributes to set on the span

        Yields:
            The span object (NullSpan if telemetry is disabled)

        Example:
            with telemetry.span("fetch_page", phase="scraping") as span:
                span.set_attribute("url", url)
                result = fetch(url)
        """
        if not self.is_enabled:
            yield NullSpan()
            return

        # Build attributes
        correlation_id = self._get_correlation_id()
        span_attrs: dict[str, Any] = {
            "correlation_id": correlation_id,
            "operation_name": name,
        }

        if phase is not None:
            span_attrs["phase"] = phase

        if attributes:
            span_attrs.update(attributes)

        # Create span
        with self._tracer.start_as_current_span(name, attributes=span_attrs) as span:
            try:
                yield span
            except Exception as e:
                # Record exception with stack trace
                self._record_exception_on_span(span, e)
                raise

    @asynccontextmanager
    async def async_span(
        self,
        name: str,
        phase: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> AsyncGenerator[NullSpan | Any, None]:
        """
        Create a traced span for an async operation with context propagation.

        This ensures correlation_id propagates correctly across async boundaries.

        Args:
            name: Name of the operation (becomes the span name)
            phase: Optional pipeline phase (scraping, generation, output)
            attributes: Optional additional attributes to set on the span

        Yields:
            The span object (NullSpan if telemetry is disabled)

        Example:
            async with telemetry.async_span("ai_call", phase="generation") as span:
                response = await call_ai()
        """
        # Propagate correlation_id to async context
        correlation_id = self._get_correlation_id()
        token = set_async_correlation_id(correlation_id)

        try:
            if not self.is_enabled:
                yield NullSpan()
                return

            # Build attributes
            span_attrs: dict[str, Any] = {
                "correlation_id": correlation_id,
                "operation_name": name,
            }

            if phase is not None:
                span_attrs["phase"] = phase

            if attributes:
                span_attrs.update(attributes)

            # Create span
            with self._tracer.start_as_current_span(name, attributes=span_attrs) as span:
                try:
                    yield span
                except Exception as e:
                    # Record exception with stack trace
                    self._record_exception_on_span(span, e)
                    raise
        finally:
            reset_async_correlation_id(token)

    def _record_exception_on_span(self, span: Any, exception: Exception) -> None:
        """
        Record an exception on a span with full details.

        Args:
            span: The span to record the exception on
            exception: The exception to record
        """
        if span is None or isinstance(span, NullSpan):
            return

        # Get stack trace
        tb_str = traceback.format_exc()

        # Record exception with attributes
        span.record_exception(
            exception,
            attributes={
                "exception.type": type(exception).__name__,
                "exception.message": str(exception),
                "exception.stacktrace": tb_str,
            }
        )

        # Set span status to error
        if _OTEL_AVAILABLE and Status is not None and StatusCode is not None:
            span.set_status(Status(StatusCode.ERROR, str(exception)))

    def record_event(
        self,
        name: str,
        attributes: dict[str, Any] | None = None
    ) -> None:
        """
        Record an event on the current span.

        Events are used to record significant operations within a span,
        such as API calls, cache hits, or tier escalations.

        Args:
            name: Name of the event
            attributes: Optional attributes for the event

        Example:
            telemetry.record_event("cache_hit", {"key": cache_key})
            telemetry.record_event("tier_escalation", {"from": "basic", "to": "premium"})
        """
        if not self.is_enabled:
            return

        span = trace.get_current_span()
        if span is not None and span.is_recording():
            event_attrs = attributes or {}
            # Add correlation_id to event
            event_attrs["correlation_id"] = self._get_correlation_id()
            span.add_event(name, attributes=event_attrs)

    def record_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        operation: str | None = None,
        cost_tracker: CostTracker | None = None
    ) -> float:
        """
        Record token usage and calculate cost, attaching attributes to the current span.

        This method calculates the cost based on the model pricing and token counts,
        then attaches cost-related attributes to the current span for observability.
        It also emits a cost event with the correlation_id for aggregation.

        Args:
            model: The AI model name (e.g., "gemini-1.5-pro")
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            operation: Optional operation name for categorization
            cost_tracker: Optional CostTracker instance. If None, uses default pricing.

        Returns:
            The calculated cost in USD.

        Example:
            with telemetry.span("ai_generation", phase="generation") as span:
                response = await call_ai_api()
                cost = telemetry.record_cost(
                    model="gemini-1.5-pro",
                    input_tokens=1000,
                    output_tokens=500,
                    operation="generate_report"
                )
                print(f"API call cost: ${cost:.6f}")

        **Validates: Requirements 5.1, 5.3, 5.4, 5.5**
        """
        # Use provided cost tracker or create a default one
        tracker = cost_tracker or CostTracker()

        # Calculate cost
        cost = tracker.calculate_cost(model, input_tokens, output_tokens)

        # Get correlation_id for metrics
        correlation_id = self._get_correlation_id()

        # Attach cost attributes to current span
        span = self.get_current_span()
        if span is not None and not isinstance(span, NullSpan):
            span.set_attributes({
                "ai.model": model,
                "ai.input_tokens": input_tokens,
                "ai.output_tokens": output_tokens,
                "ai.cost_usd": cost,
            })
            if operation:
                span.set_attribute("ai.operation", operation)

        # Emit cost event with correlation_id for aggregation
        self.record_event(
            "ai_cost_recorded",
            {
                "ai.model": model,
                "ai.input_tokens": input_tokens,
                "ai.output_tokens": output_tokens,
                "ai.cost_usd": cost,
                "ai.operation": operation or "unknown",
                "correlation_id": correlation_id,
            }
        )

        return cost

    def get_current_span(self) -> NullSpan | Any:
        """
        Get the current active span.

        Returns:
            The current span or NullSpan if telemetry is disabled.
        """
        if not self.is_enabled:
            return NullSpan()

        span = trace.get_current_span()
        return span if span is not None else NullSpan()

    def shutdown(self) -> None:
        """
        Shutdown the telemetry system and flush any pending spans.

        Should be called when the application is shutting down to ensure
        all spans are exported.
        """
        if self._provider is not None and hasattr(self._provider, 'shutdown'):
            try:
                self._provider.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down telemetry: {e}")

        self._initialized = False
        self._tracer = None


# =============================================================================
# ASYNC CONTEXT PROPAGATION UTILITIES
# =============================================================================

@asynccontextmanager
async def propagate_correlation_id(correlation_id: str) -> AsyncGenerator[None, None]:
    """
    Context manager to propagate correlation_id across async boundaries.

    This ensures that async tasks spawned within this context will have
    access to the same correlation_id.

    Args:
        correlation_id: The correlation ID to propagate

    Example:
        async with propagate_correlation_id("abc12345"):
            # All async operations here will see "abc12345"
            await some_async_operation()
    """
    token = set_async_correlation_id(correlation_id)
    try:
        yield
    finally:
        reset_async_correlation_id(token)


async def run_with_correlation_id(
    correlation_id: str,
    coro: Any
) -> Any:
    """
    Run a coroutine with a specific correlation_id in context.

    Args:
        correlation_id: The correlation ID to use
        coro: The coroutine to run

    Returns:
        The result of the coroutine

    Example:
        result = await run_with_correlation_id("abc12345", fetch_data())
    """
    token = set_async_correlation_id(correlation_id)
    try:
        return await coro
    finally:
        reset_async_correlation_id(token)


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# =============================================================================

# Global telemetry instance (lazy initialization)
_global_telemetry: TelemetrySystem | None = None


def get_telemetry() -> TelemetrySystem:
    """
    Get the global telemetry instance.

    Creates a disabled telemetry system if not initialized.

    Returns:
        The global TelemetrySystem instance.
    """
    global _global_telemetry
    if _global_telemetry is None:
        _global_telemetry = TelemetrySystem()
    return _global_telemetry


def init_telemetry(config: TelemetryConfig) -> TelemetrySystem:
    """
    Initialize the global telemetry system with configuration.

    Args:
        config: Telemetry configuration

    Returns:
        The initialized TelemetrySystem instance.
    """
    global _global_telemetry
    _global_telemetry = TelemetrySystem(config)
    return _global_telemetry


def is_otel_available() -> bool:
    """
    Check if OpenTelemetry is available.

    Returns:
        True if OpenTelemetry packages are installed.
    """
    return _OTEL_AVAILABLE


# =============================================================================
# COST TRACKER
# =============================================================================

@dataclass
class CostTracker:
    """
    Tracks and calculates AI API costs based on token usage.

    The CostTracker maintains pricing tables for different AI models and
    calculates costs based on input/output token counts. It integrates
    with the TelemetrySystem to attach cost attributes to spans.

    Attributes:
        pricing: Dictionary mapping model names to (input_price, output_price)
                 tuples, where prices are per 1 million tokens.

    Example:
        tracker = CostTracker()
        cost = tracker.calculate_cost("gemini-1.5-pro", input_tokens=1000, output_tokens=500)
        print(f"Cost: ${cost:.6f}")

        # With custom pricing
        custom_pricing = {
            "custom-model": (2.0, 8.0),  # $2/1M input, $8/1M output
        }
        tracker = CostTracker(pricing=custom_pricing)

    **Validates: Requirements 5.2, 5.6**
    """

    # Default pricing per 1M tokens (input_price, output_price)
    pricing: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        "gemini-1.5-pro": (1.25, 5.00),
        "gemini-1.5-flash": (0.075, 0.30),
        "gemini-2.0-flash": (0.10, 0.40),
    })

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Calculate the cost for token usage based on model pricing.

        The cost is calculated using the formula:
        cost = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price

        Args:
            model: The AI model name (must be in pricing table)
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated

        Returns:
            The calculated cost in USD. Returns 0.0 if the model is not
            in the pricing table.

        Example:
            tracker = CostTracker()
            # 1000 input tokens + 500 output tokens with gemini-1.5-pro
            # Cost = (1000/1M) * 1.25 + (500/1M) * 5.00 = 0.00125 + 0.0025 = 0.00375
            cost = tracker.calculate_cost("gemini-1.5-pro", 1000, 500)

        **Validates: Requirements 5.2**
        """
        if model not in self.pricing:
            return 0.0

        input_price, output_price = self.pricing[model]
        input_cost = (input_tokens / 1_000_000) * input_price
        output_cost = (output_tokens / 1_000_000) * output_price
        return input_cost + output_cost

    def get_supported_models(self) -> list[str]:
        """
        Get the list of models with pricing information.

        Returns:
            List of model names that have pricing configured.
        """
        return list(self.pricing.keys())

    def add_model_pricing(
        self,
        model: str,
        input_price: float,
        output_price: float
    ) -> None:
        """
        Add or update pricing for a model.

        Args:
            model: The model name
            input_price: Price per 1M input tokens in USD
            output_price: Price per 1M output tokens in USD

        Example:
            tracker = CostTracker()
            tracker.add_model_pricing("gpt-4", 30.0, 60.0)

        **Validates: Requirements 5.6**
        """
        self.pricing[model] = (input_price, output_price)

    def get_model_pricing(self, model: str) -> tuple[float, float] | None:
        """
        Get the pricing for a specific model.

        Args:
            model: The model name

        Returns:
            Tuple of (input_price, output_price) per 1M tokens, or None
            if the model is not in the pricing table.
        """
        return self.pricing.get(model)
