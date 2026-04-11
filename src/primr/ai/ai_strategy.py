"""
AI Strategy Analyzer for generating AI opportunity recommendations.

Generates tailored AI use cases based on company research and cloud vendor preference.
"""

from dataclasses import dataclass
from enum import Enum

from primr.utils.logging_config import get_logger

logger = get_logger("ai.ai_strategy")


class CloudVendor(Enum):
    """Cloud vendor for AI technology recommendations."""

    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"
    AGNOSTIC = "agnostic"
    PRIVATE = "private"


class AICategory(Enum):
    """Categories of AI use cases."""

    CONVERSATIONAL = "conversational"  # Chatbots, virtual assistants
    AGENTIC = "agentic"  # Autonomous task coordination
    GEN_BI = "gen_bi"  # Natural language data interaction
    AUTOMATION = "automation"  # Process and decision automation
    PRODUCTIVITY = "productivity"  # Copilot, AI-assisted development
    ML_WORKLOADS = "ml_workloads"  # Model training, deployment


@dataclass
class AIOpportunity:
    """A single AI opportunity recommendation."""

    title: str
    description: str
    category: AICategory
    technologies: list[str]
    business_impact: str
    implementation_complexity: str = "Medium"  # Low, Medium, High
    estimated_timeline: str = "3-6 months"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "technologies": self.technologies,
            "business_impact": self.business_impact,
            "implementation_complexity": self.implementation_complexity,
            "estimated_timeline": self.estimated_timeline,
        }


# Cloud vendor technology mappings
VENDOR_TECHNOLOGIES: dict[CloudVendor, dict[AICategory, list[str]]] = {
    CloudVendor.AZURE: {
        AICategory.CONVERSATIONAL: ["Azure OpenAI", "Copilot Studio", "Azure Bot Service"],
        AICategory.AGENTIC: ["Azure AI Agent Service", "Semantic Kernel", "AutoGen"],
        AICategory.GEN_BI: ["Microsoft Fabric", "Power BI Copilot", "Azure Synapse"],
        AICategory.AUTOMATION: ["Power Automate", "Azure Logic Apps", "AI Builder"],
        AICategory.PRODUCTIVITY: ["Microsoft 365 Copilot", "GitHub Copilot", "Azure AI Studio"],
        AICategory.ML_WORKLOADS: [
            "Azure Machine Learning",
            "Azure OpenAI Service",
            "Azure AI Services",
        ],
    },
    CloudVendor.AWS: {
        AICategory.CONVERSATIONAL: ["Amazon Bedrock", "Amazon Lex", "Amazon Q"],
        AICategory.AGENTIC: ["Amazon Bedrock Agents", "AWS Step Functions", "Amazon Q Developer"],
        AICategory.GEN_BI: ["Amazon QuickSight Q", "Amazon Athena", "AWS Glue"],
        AICategory.AUTOMATION: ["AWS Lambda", "Amazon EventBridge", "AWS Step Functions"],
        AICategory.PRODUCTIVITY: ["Amazon Q Developer", "Amazon CodeWhisperer", "AWS App Studio"],
        AICategory.ML_WORKLOADS: ["Amazon SageMaker", "Amazon Bedrock", "AWS Trainium"],
    },
    CloudVendor.GCP: {
        AICategory.CONVERSATIONAL: ["Vertex AI", "Dialogflow CX", "Gemini API"],
        AICategory.AGENTIC: ["Vertex AI Agent Builder", "LangChain on GCP", "Gemini"],
        AICategory.GEN_BI: ["BigQuery ML", "Looker", "Vertex AI Search"],
        AICategory.AUTOMATION: ["Cloud Functions", "Workflows", "Document AI"],
        AICategory.PRODUCTIVITY: ["Gemini for Workspace", "Duet AI", "Cloud Code"],
        AICategory.ML_WORKLOADS: ["Vertex AI", "TPU", "AutoML"],
    },
    CloudVendor.AGNOSTIC: {
        AICategory.CONVERSATIONAL: [
            "Large Language Models",
            "Conversational AI Platform",
            "Voice AI",
        ],
        AICategory.AGENTIC: ["AI Agents", "Workflow Orchestration", "Multi-Agent Systems"],
        AICategory.GEN_BI: ["Natural Language BI", "Semantic Layer", "Data Visualization AI"],
        AICategory.AUTOMATION: ["Process Automation", "Decision Intelligence", "RPA with AI"],
        AICategory.PRODUCTIVITY: ["AI Coding Assistants", "Document AI", "Meeting AI"],
        AICategory.ML_WORKLOADS: ["ML Platform", "Model Training", "MLOps"],
    },
    CloudVendor.PRIVATE: {
        AICategory.CONVERSATIONAL: ["NVIDIA NIM", "Ollama", "vLLM"],
        AICategory.AGENTIC: ["NVIDIA AI Blueprints", "LangChain", "CrewAI"],
        AICategory.GEN_BI: ["NVIDIA RAPIDS", "Apache Superset", "MindsDB"],
        AICategory.AUTOMATION: ["Kubeflow Pipelines", "Airflow", "Prefect"],
        AICategory.PRODUCTIVITY: ["Continue.dev", "Tabby", "Open-source Copilots"],
        AICategory.ML_WORKLOADS: ["NVIDIA DGX", "NVIDIA AI Enterprise", "Kubeflow"],
    },
}

# Industry to AI category relevance mapping
INDUSTRY_CATEGORIES: dict[str, list[AICategory]] = {
    "healthcare": [AICategory.AUTOMATION, AICategory.CONVERSATIONAL, AICategory.ML_WORKLOADS],
    "financial": [AICategory.GEN_BI, AICategory.AUTOMATION, AICategory.AGENTIC],
    "retail": [AICategory.CONVERSATIONAL, AICategory.GEN_BI, AICategory.AUTOMATION],
    "manufacturing": [AICategory.AUTOMATION, AICategory.ML_WORKLOADS, AICategory.GEN_BI],
    "technology": [AICategory.PRODUCTIVITY, AICategory.AGENTIC, AICategory.ML_WORKLOADS],
    "professional services": [
        AICategory.PRODUCTIVITY,
        AICategory.CONVERSATIONAL,
        AICategory.GEN_BI,
    ],
    "education": [AICategory.CONVERSATIONAL, AICategory.PRODUCTIVITY, AICategory.AUTOMATION],
    "logistics": [AICategory.AUTOMATION, AICategory.ML_WORKLOADS, AICategory.GEN_BI],
    "energy": [AICategory.ML_WORKLOADS, AICategory.AUTOMATION, AICategory.GEN_BI],
    "default": [AICategory.PRODUCTIVITY, AICategory.AUTOMATION, AICategory.CONVERSATIONAL],
}

# Business impact templates by category
IMPACT_TEMPLATES: dict[AICategory, str] = {
    AICategory.CONVERSATIONAL: "Reduce customer service costs by 30-50% while improving response times and customer satisfaction scores",
    AICategory.AGENTIC: "Automate complex multi-step workflows, reducing manual coordination effort by 60-80%",
    AICategory.GEN_BI: "Enable self-service analytics for business users, reducing time-to-insight from days to minutes",
    AICategory.AUTOMATION: "Streamline operational processes, reducing manual effort by 40-60% and error rates by 80%",
    AICategory.PRODUCTIVITY: "Boost employee productivity by 20-40% through AI-assisted content creation and code development",
    AICategory.ML_WORKLOADS: "Enable predictive capabilities for demand forecasting, risk assessment, or quality control with 85%+ accuracy",
}


class AIStrategyAnalyzer:
    """
    Generates AI opportunity recommendations tailored to company and cloud vendor.

    Example:
        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze(
            company_name="Acme Corp",
            industry="manufacturing",
            platform=CloudVendor.AZURE
        )
    """

    # Keywords that indicate specific AI opportunity signals
    CONTEXT_SIGNALS = {
        "high_customer_volume": [
            "customer service",
            "support tickets",
            "call center",
            "contact center",
            "customer support",
            "help desk",
            "customer inquiries",
            "support team",
            "customer experience",
            "cx",
            "customer satisfaction",
            "nps",
        ],
        "data_heavy": [
            "analytics",
            "data warehouse",
            "reporting",
            "business intelligence",
            "dashboard",
            "metrics",
            "kpi",
            "data-driven",
            "insights",
            "data lake",
            "big data",
            "data platform",
        ],
        "automation_opportunity": [
            "manual process",
            "repetitive",
            "paperwork",
            "data entry",
            "workflow",
            "approval process",
            "document processing",
            "invoice",
            "claims",
            "onboarding",
            "compliance",
        ],
        "developer_focused": [
            "software development",
            "engineering team",
            "developers",
            "code",
            "api",
            "platform",
            "saas",
            "tech stack",
            "agile",
            "devops",
            "ci/cd",
        ],
        "ml_ready": [
            "prediction",
            "forecast",
            "machine learning",
            "ai",
            "recommendation",
            "personalization",
            "anomaly detection",
            "risk scoring",
            "fraud detection",
            "demand planning",
        ],
    }

    def __init__(self):
        """Initialize the AI Strategy Analyzer."""

    def _extract_context_signals(self, context: str) -> dict[str, bool]:
        """
        Extract business signals from company research context.

        Analyzes the research content to identify indicators that
        suggest specific AI opportunity categories.

        Args:
            context: Company research content

        Returns:
            Dict mapping signal names to boolean (detected or not)
        """
        if not context:
            return {}

        context_lower = context.lower()
        signals = {}

        for signal_name, keywords in self.CONTEXT_SIGNALS.items():
            # Check if any keyword is present
            detected = any(keyword in context_lower for keyword in keywords)
            if detected:
                signals[signal_name] = True
                logger.debug(f"Detected signal: {signal_name}")

        return signals

    def analyze(
        self,
        company_name: str,
        industry: str = "",
        platform: CloudVendor = CloudVendor.AGNOSTIC,
        company_context: str = "",
    ) -> list[AIOpportunity]:
        """
        Generate 5 AI opportunities based on company context and vendor.

        Args:
            company_name: Name of the company
            industry: Industry sector (e.g., "healthcare", "retail")
            platform: Cloud vendor preference
            company_context: Additional context from company research

        Returns:
            List of exactly 5 AIOpportunity objects
        """
        logger.info(f"Analyzing AI opportunities for {company_name} ({industry})")

        # Extract signals from company context
        signals = self._extract_context_signals(company_context)
        logger.debug(f"Detected signals: {list(signals.keys())}")

        # Identify relevant AI categories for this industry
        categories = self._identify_industry_opportunities(industry)

        # Prioritize categories based on detected signals
        categories = self._prioritize_by_signals(categories, signals)

        # Ensure we have at least 5 categories (with fallbacks)
        all_categories = list(AICategory)
        while len(categories) < 5:
            for cat in all_categories:
                if cat not in categories:
                    categories.append(cat)
                    if len(categories) >= 5:
                        break

        # Generate opportunities for top 5 categories
        opportunities = []
        for category in categories[:5]:
            opportunity = self._generate_opportunity(
                category=category,
                company_name=company_name,
                industry=industry,
                vendor=platform,
                context=company_context,
            )
            opportunities.append(opportunity)

        logger.info(f"Generated {len(opportunities)} AI opportunities")
        return opportunities

    def _prioritize_by_signals(
        self, categories: list[AICategory], signals: dict[str, bool]
    ) -> list[AICategory]:
        """
        Reorder categories based on detected context signals.

        Args:
            categories: Initial category list from industry mapping
            signals: Detected signals from company context

        Returns:
            Reordered category list with signal-matched categories first
        """
        # Map signals to categories they should prioritize
        signal_to_category = {
            "high_customer_volume": AICategory.CONVERSATIONAL,
            "data_heavy": AICategory.GEN_BI,
            "automation_opportunity": AICategory.AUTOMATION,
            "developer_focused": AICategory.PRODUCTIVITY,
            "ml_ready": AICategory.ML_WORKLOADS,
        }

        # Build priority list from signals
        priority_categories = []
        for signal, category in signal_to_category.items():
            if signals.get(signal) and category not in priority_categories:
                priority_categories.append(category)

        # Add remaining categories in original order
        for cat in categories:
            if cat not in priority_categories:
                priority_categories.append(cat)

        return priority_categories

    def _identify_industry_opportunities(self, industry: str) -> list[AICategory]:
        """
        Identify most relevant AI categories for an industry.

        Args:
            industry: Industry name

        Returns:
            List of relevant AICategory values
        """
        industry_lower = industry.lower() if industry else ""

        # Try to match industry
        for key, categories in INDUSTRY_CATEGORIES.items():
            if key in industry_lower:
                return list(categories)

        # Default categories
        return list(INDUSTRY_CATEGORIES["default"])

    def _generate_opportunity(
        self,
        category: AICategory,
        company_name: str,
        industry: str,
        vendor: CloudVendor,
        context: str = "",
    ) -> AIOpportunity:
        """
        Generate a specific AI opportunity with vendor-appropriate technologies.

        Args:
            category: AI category for this opportunity
            company_name: Company name
            industry: Industry sector
            vendor: Cloud vendor
            context: Additional context

        Returns:
            AIOpportunity object
        """
        # Get technologies for this vendor and category
        technologies = VENDOR_TECHNOLOGIES.get(vendor, {}).get(
            category, VENDOR_TECHNOLOGIES[CloudVendor.AGNOSTIC][category]
        )

        # Generate title and description based on category
        title, description = self._get_category_content(category, company_name, industry)

        # Get business impact
        business_impact = IMPACT_TEMPLATES.get(category, "Significant operational improvements")

        # Determine complexity based on category
        complexity_map = {
            AICategory.CONVERSATIONAL: "Medium",
            AICategory.AGENTIC: "High",
            AICategory.GEN_BI: "Medium",
            AICategory.AUTOMATION: "Low",
            AICategory.PRODUCTIVITY: "Low",
            AICategory.ML_WORKLOADS: "High",
        }

        timeline_map = {
            AICategory.CONVERSATIONAL: "2-4 months",
            AICategory.AGENTIC: "4-6 months",
            AICategory.GEN_BI: "2-3 months",
            AICategory.AUTOMATION: "1-3 months",
            AICategory.PRODUCTIVITY: "1-2 months",
            AICategory.ML_WORKLOADS: "4-8 months",
        }

        return AIOpportunity(
            title=title,
            description=description,
            category=category,
            technologies=technologies,
            business_impact=business_impact,
            implementation_complexity=complexity_map.get(category, "Medium"),
            estimated_timeline=timeline_map.get(category, "3-6 months"),
        )

    def _get_category_content(
        self, category: AICategory, company_name: str, industry: str
    ) -> tuple:
        """Get title and description for a category."""
        industry_context = f" in {industry}" if industry else ""

        content_map = {
            AICategory.CONVERSATIONAL: (
                "Intelligent Customer Engagement",
                f"Deploy an AI-powered conversational assistant for {company_name} to handle "
                f"customer inquiries, support requests, and sales conversations{industry_context}. "
                "The solution can operate 24/7, handle multiple languages, and seamlessly escalate "
                "complex issues to human agents.",
            ),
            AICategory.AGENTIC: (
                "Autonomous Workflow Orchestration",
                f"Implement AI agents that can autonomously coordinate complex business processes "
                f"for {company_name}. These agents can plan, execute, and adapt multi-step workflows "
                "across systems, reducing manual coordination and accelerating process completion.",
            ),
            AICategory.GEN_BI: (
                "Natural Language Business Intelligence",
                f"Enable business users at {company_name} to query data and generate insights using "
                "natural language. Democratize analytics by allowing anyone to ask questions like "
                "'What were our top products last quarter?' and receive instant visualizations.",
            ),
            AICategory.AUTOMATION: (
                "Intelligent Process Automation",
                f"Automate repetitive operational tasks at {company_name} using AI-powered document "
                "processing, decision automation, and workflow optimization. Reduce manual effort "
                "while improving accuracy and compliance.",
            ),
            AICategory.PRODUCTIVITY: (
                "AI-Powered Productivity Suite",
                f"Enhance employee productivity at {company_name} with AI assistants for content "
                "creation, code development, meeting summarization, and email drafting. Enable "
                "teams to focus on high-value work while AI handles routine tasks.",
            ),
            AICategory.ML_WORKLOADS: (
                "Predictive Analytics Platform",
                f"Build custom ML models for {company_name} to enable predictive capabilities "
                f"{industry_context}. Applications include demand forecasting, risk scoring, "
                "anomaly detection, and recommendation systems tailored to your business needs.",
            ),
        }

        return content_map.get(category, ("AI Initiative", "Custom AI solution"))


def analyze_ai_strategy(
    company_name: str,
    industry: str = "",
    platform: str = "agnostic",
    company_context: str = "",
) -> list[AIOpportunity]:
    """
    Convenience function to analyze AI opportunities.

    Args:
        company_name: Name of the company
        industry: Industry sector
        platform: Cloud vendor string ("azure", "aws", "gcp", "agnostic")
        company_context: Additional context

    Returns:
        List of 5 AIOpportunity objects
    """
    vendor_map = {
        "azure": CloudVendor.AZURE,
        "aws": CloudVendor.AWS,
        "gcp": CloudVendor.GCP,
        "agnostic": CloudVendor.AGNOSTIC,
    }
    vendor = vendor_map.get(platform.lower(), CloudVendor.AGNOSTIC)

    analyzer = AIStrategyAnalyzer()
    return analyzer.analyze(
        company_name=company_name,
        industry=industry,
        platform=vendor,
        company_context=company_context,
    )
