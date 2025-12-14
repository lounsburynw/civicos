#!/usr/bin/env python3
"""
PDF Parsing Configuration - Backward-Compatible Advanced Tools Integration

This configuration system allows incremental adoption of advanced PDF parsing tools
while maintaining backward compatibility with the current working solution.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum


class PDFParsingTier(Enum):
    """Different tiers of PDF parsing capability"""
    BASIC = "basic"           # Current enhanced PyPDF (free)
    PROFESSIONAL = "pro"      # + LlamaParse ($20-50/month)
    ENTERPRISE = "enterprise" # + Docling + Azure ($100+/month)
    RESEARCH = "research"     # + Mistral OCR (cutting-edge)


@dataclass
class PDFParsingConfig:
    """Configuration for PDF parsing across the platform"""
    tier: PDFParsingTier
    api_keys: Dict[str, str]
    cost_limit_monthly: float
    enable_circuit_breakers: bool = True
    enable_cost_tracking: bool = True
    fallback_to_pypdf: bool = True


class ConfigManager:
    """Manage PDF parsing configuration across the platform"""

    @staticmethod
    def get_foundation_config() -> PDFParsingConfig:
        """Default configuration for foundation-funded deployment"""
        return PDFParsingConfig(
            tier=PDFParsingTier.BASIC,
            api_keys={},
            cost_limit_monthly=0.0,
            enable_circuit_breakers=True,
            enable_cost_tracking=True,
            fallback_to_pypdf=True
        )

    @staticmethod
    def get_professional_config() -> PDFParsingConfig:
        """Configuration for professional deployment with LlamaParse"""
        return PDFParsingConfig(
            tier=PDFParsingTier.PROFESSIONAL,
            api_keys={
                "LLAMAPARSE_API_KEY": os.getenv("LLAMAPARSE_API_KEY", "")
            },
            cost_limit_monthly=50.0,
            enable_circuit_breakers=True,
            enable_cost_tracking=True,
            fallback_to_pypdf=True
        )

    @staticmethod
    def get_enterprise_config() -> PDFParsingConfig:
        """Configuration for enterprise deployment"""
        return PDFParsingConfig(
            tier=PDFParsingTier.ENTERPRISE,
            api_keys={
                "LLAMAPARSE_API_KEY": os.getenv("LLAMAPARSE_API_KEY", ""),
                "AZURE_DOCUMENT_INTELLIGENCE_KEY": os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", ""),
                "AZURE_ENDPOINT": os.getenv("AZURE_ENDPOINT", "")
            },
            cost_limit_monthly=200.0,
            enable_circuit_breakers=True,
            enable_cost_tracking=True,
            fallback_to_pypdf=True
        )

    @staticmethod
    def get_research_config() -> PDFParsingConfig:
        """Configuration for research/cutting-edge deployment"""
        return PDFParsingConfig(
            tier=PDFParsingTier.RESEARCH,
            api_keys={
                "LLAMAPARSE_API_KEY": os.getenv("LLAMAPARSE_API_KEY", ""),
                "MISTRAL_API_KEY": os.getenv("MISTRAL_API_KEY", ""),
                "AZURE_DOCUMENT_INTELLIGENCE_KEY": os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", ""),
                "AZURE_ENDPOINT": os.getenv("AZURE_ENDPOINT", "")
            },
            cost_limit_monthly=500.0,
            enable_circuit_breakers=True,
            enable_cost_tracking=True,
            fallback_to_pypdf=True
        )

    @staticmethod
    def auto_detect_config() -> PDFParsingConfig:
        """Auto-detect best available configuration based on environment"""

        # Check for API keys
        has_llamaparse = bool(os.getenv("LLAMAPARSE_API_KEY"))
        has_azure = bool(os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY"))
        has_mistral = bool(os.getenv("MISTRAL_API_KEY"))

        # Try to import optional libraries
        has_docling = False
        try:
            import docling
            has_docling = True
        except ImportError:
            pass

        has_llamaparse_lib = False
        try:
            import llama_parse
            has_llamaparse_lib = True
        except ImportError:
            pass

        # Determine best tier
        if has_mistral and has_azure and has_llamaparse:
            return ConfigManager.get_research_config()
        elif (has_azure or has_docling) and has_llamaparse:
            return ConfigManager.get_enterprise_config()
        elif has_llamaparse and has_llamaparse_lib:
            return ConfigManager.get_professional_config()
        else:
            return ConfigManager.get_foundation_config()

    @staticmethod
    def validate_config(config: PDFParsingConfig) -> List[str]:
        """Validate configuration and return any warnings"""
        warnings = []

        # Check API keys for tier
        if config.tier == PDFParsingTier.PROFESSIONAL:
            if not config.api_keys.get("LLAMAPARSE_API_KEY"):
                warnings.append("Professional tier requires LLAMAPARSE_API_KEY")

        elif config.tier == PDFParsingTier.ENTERPRISE:
            if not config.api_keys.get("LLAMAPARSE_API_KEY"):
                warnings.append("Enterprise tier should have LLAMAPARSE_API_KEY")
            if not config.api_keys.get("AZURE_DOCUMENT_INTELLIGENCE_KEY"):
                warnings.append("Enterprise tier should have AZURE_DOCUMENT_INTELLIGENCE_KEY")

        elif config.tier == PDFParsingTier.RESEARCH:
            required_keys = ["LLAMAPARSE_API_KEY", "MISTRAL_API_KEY"]
            for key in required_keys:
                if not config.api_keys.get(key):
                    warnings.append(f"Research tier should have {key}")

        # Check library availability
        if config.tier in [PDFParsingTier.PROFESSIONAL, PDFParsingTier.ENTERPRISE, PDFParsingTier.RESEARCH]:
            try:
                import llama_parse
            except ImportError:
                warnings.append("Advanced tiers require 'pip install llama-parse'")

        if config.tier in [PDFParsingTier.ENTERPRISE, PDFParsingTier.RESEARCH]:
            try:
                import docling
            except ImportError:
                warnings.append("Enterprise/Research tiers recommend 'pip install docling'")

        return warnings


# Example usage configurations
DEPLOYMENT_CONFIGS = {
    "foundation": ConfigManager.get_foundation_config(),
    "professional": ConfigManager.get_professional_config(),
    "enterprise": ConfigManager.get_enterprise_config(),
    "research": ConfigManager.get_research_config(),
    "auto": ConfigManager.auto_detect_config()
}


def print_config_info():
    """Print information about available configurations"""
    print("📊 PDF PARSING CONFIGURATION OPTIONS")
    print("=" * 50)

    for name, config in DEPLOYMENT_CONFIGS.items():
        print(f"\n🛠️  {name.upper()} TIER")
        print(f"   Tier: {config.tier.value}")
        print(f"   Monthly Cost Limit: ${config.cost_limit_monthly}")
        print(f"   API Keys Required: {list(config.api_keys.keys()) if config.api_keys else 'None'}")

        warnings = ConfigManager.validate_config(config)
        if warnings:
            print(f"   ⚠️  Warnings: {'; '.join(warnings)}")
        else:
            print(f"   ✅ Ready to use")

    print(f"\n💡 RECOMMENDATION:")
    auto_config = ConfigManager.auto_detect_config()
    print(f"   Auto-detected tier: {auto_config.tier.value}")
    print(f"   Monthly cost: ${auto_config.cost_limit_monthly}")


if __name__ == "__main__":
    print_config_info()