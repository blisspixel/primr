"""Property tests for strategies resource completeness.

Property 6: Strategies Resource Completeness
Validates: FR-5.1, FR-5.2
"""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from primr.mcp_server.types import StrategyType

# Valid strategy type IDs from the enum
VALID_STRATEGY_IDS = {s.value for s in StrategyType}


class TestStrategiesResourceSchema:
    """Test strategies resource response schema."""

    @pytest.fixture
    def strategies_response(self) -> dict:
        """Get strategies resource response."""
        # Import and call the resource handler directly
        from primr.mcp_server.resources import _read_strategies_available

        result = _read_strategies_available()
        assert len(result) == 1
        return json.loads(result[0].content)

    def test_response_is_valid_json(self, strategies_response: dict) -> None:
        """FR-5.2: Response is valid JSON."""
        assert isinstance(strategies_response, dict)

    def test_has_schema_version(self, strategies_response: dict) -> None:
        """FR-5.2: Response includes schema_version."""
        assert "schema_version" in strategies_response
        assert strategies_response["schema_version"] == "1.0"

    def test_has_strategies_array(self, strategies_response: dict) -> None:
        """FR-5.2: Response has strategies array."""
        assert "strategies" in strategies_response
        assert isinstance(strategies_response["strategies"], list)

    def test_strategies_array_has_expected_elements(self, strategies_response: dict) -> None:
        """FR-5.2: strategies array has one entry per StrategyType enum value."""
        assert len(strategies_response["strategies"]) == len(VALID_STRATEGY_IDS)


class TestStrategyFields:
    """Test individual strategy fields."""

    @pytest.fixture
    def strategies_response(self) -> dict:
        """Get strategies resource response."""
        from primr.mcp_server.resources import _read_strategies_available

        result = _read_strategies_available()
        return json.loads(result[0].content)

    def test_each_strategy_has_id(self, strategies_response: dict) -> None:
        """FR-5.2: Each strategy has id field."""
        for strategy in strategies_response["strategies"]:
            assert "id" in strategy
            assert isinstance(strategy["id"], str)

    def test_each_strategy_has_name(self, strategies_response: dict) -> None:
        """FR-5.2: Each strategy has name field."""
        for strategy in strategies_response["strategies"]:
            assert "name" in strategy
            assert isinstance(strategy["name"], str)
            assert len(strategy["name"]) > 0

    def test_each_strategy_has_description(self, strategies_response: dict) -> None:
        """FR-5.2: Each strategy has description field."""
        for strategy in strategies_response["strategies"]:
            assert "description" in strategy
            assert isinstance(strategy["description"], str)
            assert len(strategy["description"]) > 0

    def test_each_strategy_has_requires_platform(self, strategies_response: dict) -> None:
        """FR-5.2: Each strategy has requires_platform field."""
        for strategy in strategies_response["strategies"]:
            assert "requires_platform" in strategy
            assert isinstance(strategy["requires_platform"], bool)

    def test_each_strategy_has_estimated_time(self, strategies_response: dict) -> None:
        """FR-5.2: Each strategy has estimated_time_minutes field."""
        for strategy in strategies_response["strategies"]:
            assert "estimated_time_minutes" in strategy
            assert isinstance(strategy["estimated_time_minutes"], int)
            assert strategy["estimated_time_minutes"] > 0

    def test_each_strategy_has_estimated_cost(self, strategies_response: dict) -> None:
        """FR-5.2: Each strategy has estimated_cost_usd field."""
        for strategy in strategies_response["strategies"]:
            assert "estimated_cost_usd" in strategy
            assert isinstance(strategy["estimated_cost_usd"], (int, float))
            assert strategy["estimated_cost_usd"] > 0


class TestStrategyIdValidity:
    """Test strategy IDs are valid enum values."""

    @pytest.fixture
    def strategies_response(self) -> dict:
        """Get strategies resource response."""
        from primr.mcp_server.resources import _read_strategies_available

        result = _read_strategies_available()
        return json.loads(result[0].content)

    def test_all_ids_are_valid_strategy_types(self, strategies_response: dict) -> None:
        """FR-5.2: Each id is a valid StrategyType enum value."""
        for strategy in strategies_response["strategies"]:
            assert strategy["id"] in VALID_STRATEGY_IDS, f"Invalid strategy ID: {strategy['id']}"

    def test_all_strategy_types_are_present(self, strategies_response: dict) -> None:
        """All StrategyType enum values are represented."""
        response_ids = {s["id"] for s in strategies_response["strategies"]}
        assert response_ids == VALID_STRATEGY_IDS


class TestSpecificStrategies:
    """Test specific strategy configurations."""

    @pytest.fixture
    def strategies_response(self) -> dict:
        """Get strategies resource response."""
        from primr.mcp_server.resources import _read_strategies_available

        result = _read_strategies_available()
        return json.loads(result[0].content)

    def test_ai_strategy_requires_platform(self, strategies_response: dict) -> None:
        """Standalone AI Strategy requires an explicit evaluation emphasis."""
        ai_strategy = next(
            (s for s in strategies_response["strategies"] if s["id"] == "ai_strategy"), None
        )
        assert ai_strategy is not None
        assert ai_strategy["requires_platform"] is True
        assert "Business-first AI portfolio" in ai_strategy["description"]

    def test_other_strategies_dont_require_platform(self, strategies_response: dict) -> None:
        """Non-AI strategies don't require platform."""
        for strategy in strategies_response["strategies"]:
            if strategy["id"] != "ai_strategy":
                assert strategy["requires_platform"] is False, (
                    f"{strategy['id']} should not require platform"
                )


class TestPropertyBasedStrategiesResource:
    """Property-based tests for strategies resource."""

    @settings(max_examples=100)
    @given(st.integers(min_value=1, max_value=100))
    def test_strategies_resource_is_idempotent(self, _iteration: int) -> None:  # noqa: PT019
        """Property 6: Reading resource multiple times returns same result."""
        from primr.mcp_server.resources import _read_strategies_available

        result1 = _read_strategies_available()
        result2 = _read_strategies_available()

        data1 = json.loads(result1[0].content)
        data2 = json.loads(result2[0].content)

        assert data1 == data2

    @settings(max_examples=100)
    @given(st.integers(min_value=1, max_value=100))
    def test_strategies_always_has_expected_elements(self, _iteration: int) -> None:  # noqa: PT019
        """Property 6: strategies array always matches StrategyType enum."""
        from primr.mcp_server.resources import _read_strategies_available

        result = _read_strategies_available()
        data = json.loads(result[0].content)

        assert len(data["strategies"]) == len(VALID_STRATEGY_IDS)

    @settings(max_examples=100)
    @given(st.integers(min_value=1, max_value=100))
    def test_all_strategies_have_required_fields(self, _iteration: int) -> None:  # noqa: PT019
        """Property 6: All strategies have required fields."""
        from primr.mcp_server.resources import _read_strategies_available

        result = _read_strategies_available()
        data = json.loads(result[0].content)

        required_fields = {
            "id",
            "name",
            "description",
            "requires_platform",
            "estimated_time_minutes",
            "estimated_cost_usd",
        }

        for strategy in data["strategies"]:
            assert required_fields.issubset(set(strategy.keys()))
