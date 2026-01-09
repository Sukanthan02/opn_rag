import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =====================
# DATABASE
# =====================
MYSQL_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "localhost"),
    "user": os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", "yakkay"),
    "database": os.environ.get("MYSQL_DB", "agent_router")
}

# =====================
# QDRANT
# =====================
QDRANT_PATH = os.environ.get("QDRANT_PATH", "./qdrant_data")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "agent_router")

# =====================
# EMBEDDINGS
# =====================
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1")
VECTOR_SIZE = int(os.environ.get("VECTOR_SIZE", "768"))

# =====================
# GROK CLOUD API (Unified LLM Provider)
# =====================
# Load from environment variable for security
GROK_API_KEY = os.environ.get("GROK_API_KEY", "Grok API key")
GROK_MODEL = os.environ.get("GROK_MODEL", "llama-3.3-70b-versatile")
# GROK_BASE_URL = os.environ.get("GROK_BASE_URL", "https://api.groq.com/openai/v1")

# =====================
# QUERY VALIDATION
# =====================
# Enable query validation before routing
QUERY_VALIDATION_ENABLED = os.environ.get("QUERY_VALIDATION_ENABLED", "True").lower() == "true"

# Confidence threshold for query validation (0.0 to 1.0)
QUERY_VALIDATION_CONFIDENCE_THRESHOLD = float(os.environ.get("QUERY_VALIDATION_CONFIDENCE_THRESHOLD", "0.7"))

# =====================
# CONVERSATION MODE
# =====================
CONVERSATION_MODE = os.environ.get("CONVERSATION_MODE", "True").lower() == "true"

