"""
Configuration and model management for QA system.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import json

from primr.config.models import PrimrModels, ModelType

logger = logging.getLogger(__name__)


@dataclass
class QAModelConfig:
    """Configuration for a QA model."""
    name: str
    display_name: str
    provider: str  # e.g., "google", "openai", "anthropic"
    cost_per_1k_tokens: float = 0.0
    max_tokens: int = 8192
    supports_json_mode: bool = False
    recommended_for: List[str] = field(default_factory=list)  # e.g., ["general", "technical", "financial"]
    available: bool = True


@dataclass
class QASystemConfig:
    """Complete QA system configuration."""
    default_model: str = PrimrModels.QA_MODEL
    enabled_by_default: bool = True
    save_detailed_reports: bool = True
    max_retries: int = 3
    retry_base_delay: float = 2.0
    timeout_seconds: int = 120
    models: Dict[str, QAModelConfig] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize default models if none provided."""
        if not self.models:
            self.models = self._get_default_models()
    
    def _get_default_models(self) -> Dict[str, QAModelConfig]:
        """Get default model configurations."""
        from ..config.models import PrimrModels, ModelRegistry
        
        return {
            PrimrModels.QA_MODEL: QAModelConfig(
                name=PrimrModels.QA_MODEL,
                display_name=ModelRegistry.GEMINI_3_FLASH.display_name,
                provider="google",
                cost_per_1k_tokens=0.0005,  # $0.50 per 1M tokens
                max_tokens=65536,
                supports_json_mode=True,
                recommended_for=["general", "fast", "analysis"],
                available=True
            ),
            PrimrModels.REASONING_MODEL: QAModelConfig(
                name=PrimrModels.REASONING_MODEL,
                display_name=ModelRegistry.GEMINI_3_PRO.display_name,
                provider="google",
                cost_per_1k_tokens=0.002,  # $2.00 per 1M tokens
                max_tokens=65536,
                supports_json_mode=True,
                recommended_for=["complex", "detailed", "technical"],
                available=True
            ),
            ModelRegistry.GEMINI_2_5_PRO.name: QAModelConfig(
                name=ModelRegistry.GEMINI_2_5_PRO.name,
                display_name=ModelRegistry.GEMINI_2_5_PRO.display_name,
                provider="google",
                cost_per_1k_tokens=0.00125,
                max_tokens=32768,
                supports_json_mode=True,
                recommended_for=["complex", "detailed", "technical"],
                available=True
            )
        }


class QAConfigManager:
    """Manages QA system configuration."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file (optional)
        """
        self.config_path = config_path or Path.home() / ".primr" / "qa_config.json"
        self.config = self._load_config()
    
    def _load_config(self) -> QASystemConfig:
        """Load configuration from file or create default."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # Convert model configs
                models = {}
                for name, model_data in config_data.get('models', {}).items():
                    models[name] = QAModelConfig(**model_data)
                
                config = QASystemConfig(
                    default_model=config_data.get('default_model', PrimrModels.QA_MODEL),
                    enabled_by_default=config_data.get('enabled_by_default', True),
                    save_detailed_reports=config_data.get('save_detailed_reports', True),
                    max_retries=config_data.get('max_retries', 3),
                    retry_base_delay=config_data.get('retry_base_delay', 2.0),
                    timeout_seconds=config_data.get('timeout_seconds', 120),
                    models=models
                )
                
                logger.info(f"Loaded QA configuration from {self.config_path}")
                return config
                
            except Exception as e:
                logger.warning(f"Failed to load QA config from {self.config_path}: {e}")
                logger.info("Using default QA configuration")
        
        return QASystemConfig()
    
    def save_config(self) -> bool:
        """
        Save current configuration to file.
        
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Ensure config directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to serializable format
            config_data = {
                'default_model': self.config.default_model,
                'enabled_by_default': self.config.enabled_by_default,
                'save_detailed_reports': self.config.save_detailed_reports,
                'max_retries': self.config.max_retries,
                'retry_base_delay': self.config.retry_base_delay,
                'timeout_seconds': self.config.timeout_seconds,
                'models': {}
            }
            
            for name, model in self.config.models.items():
                config_data['models'][name] = {
                    'name': model.name,
                    'display_name': model.display_name,
                    'provider': model.provider,
                    'cost_per_1k_tokens': model.cost_per_1k_tokens,
                    'max_tokens': model.max_tokens,
                    'supports_json_mode': model.supports_json_mode,
                    'recommended_for': model.recommended_for,
                    'available': model.available
                }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
            
            logger.info(f"Saved QA configuration to {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save QA config to {self.config_path}: {e}")
            return False
    
    def get_model_config(self, model_name: str) -> Optional[QAModelConfig]:
        """
        Get configuration for a specific model.
        
        Args:
            model_name: Name of the model
            
        Returns:
            Model configuration or None if not found
        """
        return self.config.models.get(model_name)
    
    def get_available_models(self) -> List[QAModelConfig]:
        """
        Get list of available models.
        
        Returns:
            List of available model configurations
        """
        return [model for model in self.config.models.values() if model.available]
    
    def get_recommended_models(self, use_case: str) -> List[QAModelConfig]:
        """
        Get models recommended for a specific use case.
        
        Args:
            use_case: Use case (e.g., "general", "technical", "financial")
            
        Returns:
            List of recommended model configurations
        """
        return [
            model for model in self.get_available_models()
            if use_case in model.recommended_for
        ]
    
    def validate_model(self, model_name: str) -> tuple[bool, str]:
        """
        Validate that a model is available and properly configured.
        
        Args:
            model_name: Name of the model to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if model_name not in self.config.models:
            return False, f"Model '{model_name}' is not configured"
        
        model = self.config.models[model_name]
        
        if not model.available:
            return False, f"Model '{model_name}' is marked as unavailable"
        
        # Additional validation could be added here
        # (e.g., checking API keys, testing connectivity)
        
        return True, ""
    
    def estimate_cost(self, model_name: str, estimated_tokens: int) -> float:
        """
        Estimate cost for using a model with given token count.
        
        Args:
            model_name: Name of the model
            estimated_tokens: Estimated number of tokens
            
        Returns:
            Estimated cost in dollars
        """
        model = self.get_model_config(model_name)
        if not model:
            return 0.0
        
        return (estimated_tokens / 1000) * model.cost_per_1k_tokens
    
    def set_default_model(self, model_name: str) -> bool:
        """
        Set the default model for QA analysis.
        
        Args:
            model_name: Name of the model to set as default
            
        Returns:
            True if set successfully, False otherwise
        """
        is_valid, error_msg = self.validate_model(model_name)
        if not is_valid:
            logger.error(f"Cannot set default model: {error_msg}")
            return False
        
        self.config.default_model = model_name
        logger.info(f"Set default QA model to: {model_name}")
        return True
    
    def add_custom_model(self, model_config: QAModelConfig) -> bool:
        """
        Add a custom model configuration.
        
        Args:
            model_config: Model configuration to add
            
        Returns:
            True if added successfully, False otherwise
        """
        try:
            self.config.models[model_config.name] = model_config
            logger.info(f"Added custom model: {model_config.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to add custom model: {e}")
            return False
    
    def get_config_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current configuration.
        
        Returns:
            Dictionary with configuration summary
        """
        available_models = self.get_available_models()
        
        return {
            'default_model': self.config.default_model,
            'enabled_by_default': self.config.enabled_by_default,
            'total_models': len(self.config.models),
            'available_models': len(available_models),
            'model_names': [model.name for model in available_models],
            'config_path': str(self.config_path),
            'max_retries': self.config.max_retries,
            'timeout_seconds': self.config.timeout_seconds
        }


# Global configuration manager instance
_config_manager: Optional[QAConfigManager] = None


def get_qa_config() -> QAConfigManager:
    """Get the global QA configuration manager."""
    global _config_manager
    if _config_manager is None:
        _config_manager = QAConfigManager()
    return _config_manager


def reset_qa_config():
    """Reset the global configuration manager (mainly for testing)."""
    global _config_manager
    _config_manager = None