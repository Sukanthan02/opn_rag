import logging
import os
from datetime import datetime

# Create logs directories if they don't exist
log_dir = "logs"
user_log_dir = "user_logs"
os.makedirs(log_dir, exist_ok=True)
os.makedirs(user_log_dir, exist_ok=True)

# Create log filename with timestamp
log_filename = os.path.join(log_dir, f"rag_agent_router_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
user_log_filename = os.path.join(user_log_dir, f"user_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# Enhanced logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        # File handler - logs everything
        logging.FileHandler(log_filename),
        # Console handler - logs INFO and above
        logging.StreamHandler()
    ]
)

# Create main logger
logger = logging.getLogger("RAG_AGENT_ROUTER")
logger.setLevel(logging.DEBUG)

# Create specialized loggers for different components
llm_logger = logging.getLogger("RAG_AGENT_ROUTER.LLM")
conversation_logger = logging.getLogger("RAG_AGENT_ROUTER.CONVERSATION")
routing_logger = logging.getLogger("RAG_AGENT_ROUTER.ROUTING")
ingest_logger = logging.getLogger("RAG_AGENT_ROUTER.INGEST")
retrieval_logger = logging.getLogger("RAG_AGENT_ROUTER.RETRIEVAL")

# Create user logger for user-facing chat logs
user_logger = logging.getLogger("USER_CHAT")
user_logger.setLevel(logging.INFO)
user_logger.handlers = []  # Clear default handlers
user_logger.addHandler(logging.FileHandler(user_log_filename))
user_logger.propagate = False  # Don't propagate to root logger

# Log system startup
logger.info("=" * 80)
logger.info("RAG AGENT ROUTER SYSTEM STARTED")
logger.info("=" * 80)
logger.debug(f"Log file: {log_filename}")
