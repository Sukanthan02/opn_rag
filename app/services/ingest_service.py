import uuid

from qdrant_client.models import PointStruct

from app.db.mysql import SessionLocal
from app.db.qdrant import get_qdrant_client
from app.embeddings.nomic_local import get_embedding
from app.config import QDRANT_COLLECTION
from app.logger import logger

from app.models.agent import Agent
from app.models.subagent import SubAgent


def ingest_agent(name: str, description: str, capabilities: dict = None) -> int:
    db = SessionLocal()

    try:
        vector_id = str(uuid.uuid4())
        embedding = get_embedding(f"{name}. {description}")

        agent = Agent(
            name=name,
            description=description,
            vector_id=vector_id,
            capabilities=capabilities or []
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        client = get_qdrant_client()
        client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[
                PointStruct(
                    id=vector_id,
                    vector=embedding,
                    payload={
                        "type": "agent",
                        "agent_id": agent.id,
                        "subagent_id": None,
                        "name": name,
                        "description": description
                    }
                )
            ]
        )

        logger.info(f"Agent ingested: {name}")
        return agent.id

    except Exception as e:
        db.rollback()
        logger.exception("Failed to ingest agent")
        raise e

    finally:
        db.close()


def ingest_subagent(agent_id: int, name: str, description: str, capabilities: dict = None) -> None:
    db = SessionLocal()

    try:
        vector_id = str(uuid.uuid4())
        embedding = get_embedding(f"{name}. {description}")

        subagent = SubAgent(
            agent_id=agent_id,
            name=name,
            description=description,
            vector_id=vector_id,
            capabilities=capabilities or []
        )

        db.add(subagent)
        db.commit()
        db.refresh(subagent)

        client = get_qdrant_client()
        client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[
                PointStruct(
                    id=vector_id,
                    vector=embedding,
                    payload={
                        "type": "subagent",
                        "agent_id": agent_id,
                        "subagent_id": subagent.id,
                        "name": name,
                        "description": description
                    }
                )
            ]
        )

        logger.info(f"SubAgent ingested: {name}")

    except Exception as e:
        db.rollback()
        logger.exception("Failed to ingest subagent")
        raise e

    finally:
        db.close()
