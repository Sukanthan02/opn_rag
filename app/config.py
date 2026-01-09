
import os

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
QDRANT_PATH = "./qdrant_data"
QDRANT_COLLECTION = "agent_router"

# =====================
# EMBEDDINGS
# =====================
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1"
VECTOR_SIZE = 768

# =====================
# GROK CLOUD API (Unified LLM Provider)
# =====================a
# Load from environment variable for security
GROK_API_KEY = os.environ.get("GROK_API_KEY", "Grok API key")
GROK_MODEL = "llama-3.3-70b-versatile"  # Recommended for best quality/speed balance
# GROK_BASE_URL = "https://api.groq.com/openai/v1"

# Alternative models available:
# - llama-3.1-8b-instant (faster, less capable)
# - groq/compound (Grok's proprietary model, if available)
# - meta-llama/llama-4-maverick-17b-128e-instruct
# - qwen/qwen3-32b

# =====================
# QUERY VALIDATION
# =====================
# Enable query validation before routing
QUERY_VALIDATION_ENABLED = True

# Confidence threshold for query validation (0.0 to 1.0)
# Queries below this threshold will trigger clarification or rejection
QUERY_VALIDATION_CONFIDENCE_THRESHOLD = 0.7

# =====================
# CONVERSATION MODE
# =====================
# If False: Direct routing and agent inquiry (current behavior)
# If True: Intelligent conversation mode - handles vague queries, asks clarification, maintains context
CONVERSATION_MODE = True

