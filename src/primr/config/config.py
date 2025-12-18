# config.py
import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_project_root():
    """
    Returns the project root directory.
    Works whether running from package or directly.
    """
    # Start from this file's location and go up to find project root
    current = Path(__file__).resolve()
    # Go up: config.py -> config/ -> primr/ -> src/ -> project_root
    for _ in range(4):
        current = current.parent
        # Check if we're at project root by looking for key files
        if (current / ".env").exists() or (current / "pyproject.toml").exists():
            return current
    # Fallback to current working directory
    return Path.cwd()


PROJECT_ROOT = get_project_root()

### **API Keys & Authentication** ###
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Google AI API Key (for consumer API)
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")  # Google Custom Search API Key
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")  # Google Custom Search Engine ID

# Validate API Keys - GOOD!
if not GEMINI_API_KEY:
    raise ValueError("[ERROR] Missing Gemini API Key in .env")
if not SEARCH_API_KEY or not SEARCH_ENGINE_ID:
    raise ValueError("[ERROR] Missing Google Search API Key or Engine ID in .env")

### **Search & Scraping Configuration** ###
NUM_SEARCH_RESULTS = 3
PARALLEL_SEARCH_LIMIT = 2
INITIAL_RETRY_DELAY = 5

# Scraping Settings
MAX_SCRAPE_RETRIES = 2
SCRAPE_TIMEOUT = 15
SCRAPE_MAX_DEPTH = 2
EXCLUDED_SITES = ["login", "captcha", "privacy-policy", "terms-of-service"]

### **AI Model Configuration** ###
AI_RESEARCH_MODEL = "gemini-3-pro-preview"  # Most capable model for deep research
AI_REPORT_MODEL = "gemini-3-pro-preview"    # Can be the same or different

MAX_RETRIES = 3
GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT = 80

### **File Handling & Output Settings** ###
# Use project root for runtime directories
OUTPUT_DIR = str(PROJECT_ROOT / "output")
WORKING_DIR = str(PROJECT_ROOT / "working")
LOGS_DIR = str(PROJECT_ROOT / "logs" / "chat_history")

# Ensure necessary directories exist - GOOD!
for directory in [OUTPUT_DIR, WORKING_DIR, LOGS_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

### **Document Processing Settings** ###
SUPPORTED_FILE_TYPES = [".pdf", ".docx", ".txt", ".xlsx"]
CONVERT_TO_PDF = True
