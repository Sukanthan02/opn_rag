from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import MYSQL_CONFIG
from app.models.base import Base
from app.logger import logger

DATABASE_URL = (
    f"mysql+mysqlconnector://{MYSQL_CONFIG['user']}:"
    f"{MYSQL_CONFIG['password']}@"
    f"{MYSQL_CONFIG['host']}/"
    f"{MYSQL_CONFIG['database']}"
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    logger.info("Creating database tables if not exist")
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()
