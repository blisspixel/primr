"""
Unit tests for QA configuration management.

**Validates: Requirements 4.1, 4.2, 4.3, 4.5**
"""

import json
import tempfile
from pathlib import Path

from src.primr.config.models import PrimrModels
from src.primr.qa.config import QAConfigManager, QAModelConfig, get_qa_config, reset_qa_config


class TestQAConfigManager:
    """Unit tests for QA configuration management."""

    def test_default_model_selection(self):
        """
        Test default model selection.
        **Validates: Requirements 4.1, 4.2**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "qa_config.json"
            config_manager = QAConfigManager(config_path)

            # Should have default model (from centralized config)
            assert config_manager.config.default_model == PrimrModels.QA_MODEL

            # Should have default models configured
            assert len(config_manager.config.models) > 0
            assert PrimrModels.QA_MODEL in config_manager.config.models

            # Default model should be available
            default_model = config_manager.get_model_config(config_manager.config.default_model)
            assert default_model is not None
            assert default_model.available

    def test_custom_model_configuration(self):
        """
        Test custom model configuration.
        **Validates: Requirements 4.2, 4.3**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "qa_config.json"
            config_manager = QAConfigManager(config_path)

            # Add custom model
            custom_model = QAModelConfig(
                name="custom-model",
                display_name="Custom Test Model",
                provider="test",
                cost_per_1k_tokens=0.01,
                max_tokens=4096,
                supports_json_mode=True,
                recommended_for=["testing"],
                available=True,
            )

            success = config_manager.add_custom_model(custom_model)
            assert success, "Should successfully add custom model"

            # Should be able to retrieve custom model
            retrieved_model = config_manager.get_model_config("custom-model")
            assert retrieved_model is not None
            assert retrieved_model.name == "custom-model"
            assert retrieved_model.display_name == "Custom Test Model"
            assert retrieved_model.provider == "test"
            assert retrieved_model.cost_per_1k_tokens == 0.01

            # Should appear in available models
            available_models = config_manager.get_available_models()
            custom_models = [m for m in available_models if m.name == "custom-model"]
            assert len(custom_models) == 1

    def test_invalid_configuration_handling(self):
        """
        Test invalid configuration handling.
        **Validates: Requirements 4.3, 4.5**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "qa_config.json"

            # Create invalid JSON config file
            with open(config_path, "w") as f:
                f.write("{ invalid json }")

            # Should handle invalid JSON gracefully
            config_manager = QAConfigManager(config_path)
            assert config_manager.config is not None
            assert len(config_manager.config.models) > 0  # Should fall back to defaults

            # Test model validation
            is_valid, error_msg = config_manager.validate_model("non-existent-model")
            assert not is_valid
            assert "not configured" in error_msg

            # Test setting invalid default model
            success = config_manager.set_default_model("non-existent-model")
            assert not success

    def test_model_validation_and_availability_checking(self):
        """
        Test model validation and availability checking.
        **Validates: Requirements 4.1, 4.3**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "qa_config.json"
            config_manager = QAConfigManager(config_path)

            # Test valid model validation (use centralized config)
            is_valid, error_msg = config_manager.validate_model(PrimrModels.QA_MODEL)
            assert is_valid
            assert error_msg == ""

            # Test invalid model validation
            is_valid, error_msg = config_manager.validate_model("invalid-model")
            assert not is_valid
            assert "not configured" in error_msg

            # Test unavailable model
            unavailable_model = QAModelConfig(
                name="unavailable-model",
                display_name="Unavailable Model",
                provider="test",
                available=False,
            )
            config_manager.add_custom_model(unavailable_model)

            is_valid, error_msg = config_manager.validate_model("unavailable-model")
            assert not is_valid
            assert "unavailable" in error_msg

            # Test available models list
            available_models = config_manager.get_available_models()
            available_names = [m.name for m in available_models]
            assert PrimrModels.QA_MODEL in available_names
            assert "unavailable-model" not in available_names

    def test_cost_estimation(self):
        """
        Test cost estimation for different model choices.
        **Validates: Requirements 4.4, 4.5**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "qa_config.json"
            config_manager = QAConfigManager(config_path)

            # Test cost estimation for QA model (should have low cost)
            qa_cost = config_manager.estimate_cost(PrimrModels.QA_MODEL, 1000)
            assert qa_cost >= 0.0  # May have small cost now

            # Add paid model for testing
            paid_model = QAModelConfig(
                name="paid-model",
                display_name="Paid Model",
                provider="test",
                cost_per_1k_tokens=0.01,  # $0.01 per 1k tokens
                available=True,
            )
            config_manager.add_custom_model(paid_model)

            # Test cost estimation for paid model
            paid_cost = config_manager.estimate_cost("paid-model", 2000)  # 2k tokens
            assert paid_cost == 0.02  # $0.02

            # Test cost estimation for non-existent model
            no_cost = config_manager.estimate_cost("non-existent", 1000)
            assert no_cost == 0.0

    def test_recommended_models_for_use_cases(self):
        """
        Test getting recommended models for different use cases.
        **Validates: Requirements 4.2, 4.5**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "qa_config.json"
            config_manager = QAConfigManager(config_path)

            # Test general use case - should have at least one model
            general_models = config_manager.get_recommended_models("general")
            assert len(general_models) > 0

            # Test analysis use case (QA model is recommended for analysis)
            analysis_models = config_manager.get_recommended_models("analysis")
            assert len(analysis_models) > 0

            # Test non-existent use case
            nonexistent_models = config_manager.get_recommended_models("nonexistent")
            assert len(nonexistent_models) == 0

    def test_configuration_persistence(self):
        """
        Test configuration saving and loading.
        **Validates: Requirements 4.1, 4.5**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "qa_config.json"

            # Create and configure manager
            config_manager1 = QAConfigManager(config_path)

            # Add a custom model to test persistence
            custom_model = QAModelConfig(
                name="test-persist-model",
                display_name="Test Persist Model",
                provider="test",
                cost_per_1k_tokens=0.001,
                available=True,
            )
            config_manager1.add_custom_model(custom_model)
            config_manager1.set_default_model("test-persist-model")
            config_manager1.config.max_retries = 5

            # Save configuration
            success = config_manager1.save_config()
            assert success
            assert config_path.exists()

            # Load configuration in new manager
            config_manager2 = QAConfigManager(config_path)
            assert config_manager2.config.default_model == "test-persist-model"
            assert config_manager2.config.max_retries == 5

            # Verify JSON structure
            with open(config_path) as f:
                config_data = json.load(f)

            assert config_data["default_model"] == "test-persist-model"
            assert config_data["max_retries"] == 5
            assert "models" in config_data
            assert len(config_data["models"]) > 0

    def test_configuration_summary(self):
        """
        Test configuration summary generation.
        **Validates: Requirements 4.5**
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "qa_config.json"
            config_manager = QAConfigManager(config_path)

            summary = config_manager.get_config_summary()

            # Should contain expected keys
            expected_keys = [
                "default_model",
                "enabled_by_default",
                "total_models",
                "available_models",
                "model_names",
                "config_path",
                "max_retries",
                "timeout_seconds",
            ]

            for key in expected_keys:
                assert key in summary, f"Summary should contain {key}"

            # Should have reasonable values
            assert isinstance(summary["total_models"], int)
            assert summary["total_models"] > 0
            assert isinstance(summary["available_models"], int)
            assert isinstance(summary["model_names"], list)
            assert len(summary["model_names"]) > 0
            assert summary["default_model"] in summary["model_names"]

    def test_global_config_manager(self):
        """
        Test global configuration manager functions.
        **Validates: Requirements 4.1**
        """
        # Reset to ensure clean state
        reset_qa_config()

        # Get global config manager
        config1 = get_qa_config()
        config2 = get_qa_config()

        # Should return same instance
        assert config1 is config2

        # Should have valid configuration
        assert config1.config is not None
        assert len(config1.config.models) > 0

        # Reset should clear global instance
        reset_qa_config()
        config3 = get_qa_config()
        assert config3 is not config1
