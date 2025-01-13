import logging
from sqlalchemy import create_engine, text, Column, String, Integer, DateTime, JSON, Text, Index, UniqueConstraint
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.sql import func
from Extensions import Extensions
from datetime import datetime
import os
from typing import List, Optional, Dict, Any

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    import sys
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pgvector"])
    from pgvector.sqlalchemy import Vector

Base = declarative_base()

class VectorCollection(Base):
    __tablename__ = 'vector_collections'
    
    id = Column(Integer, primary_key=True)
    collection_name = Column(String, nullable=False)
    embedding = Column(Vector(1536))  # Assuming default embedding size
    metadata = Column(JSON)
    content = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        Index('idx_vector_collections_embedding', embedding, postgresql_using='ivfflat'),
        UniqueConstraint('collection_name', 'content', name='uix_collection_content')
    )

class pgvector_database(Extensions):
    def __init__(
        self,
        PGVECTOR_HOST: str = None,
        PGVECTOR_PORT: str = None,
        PGVECTOR_DATABASE: str = None,
        PGVECTOR_USER: str = None,
        PGVECTOR_PASSWORD: str = None,
    ):
        self.PGVECTOR_HOST = PGVECTOR_HOST or os.getenv("PGVECTOR_HOST", "localhost")
        self.PGVECTOR_PORT = PGVECTOR_PORT or os.getenv("PGVECTOR_PORT", "5432")
        self.PGVECTOR_DATABASE = PGVECTOR_DATABASE or os.getenv("PGVECTOR_DATABASE", "agixt")
        self.PGVECTOR_USER = PGVECTOR_USER or os.getenv("PGVECTOR_USER", "postgres")
        self.PGVECTOR_PASSWORD = PGVECTOR_PASSWORD or os.getenv("PGVECTOR_PASSWORD", "postgres")
        
        self.engine = self._create_engine()
        Base.metadata.create_all(self.engine)

    def _create_engine(self):
        return create_engine(
            f"postgresql+psycopg2://{self.PGVECTOR_USER}:{self.PGVECTOR_PASSWORD}@"
            f"{self.PGVECTOR_HOST}:{self.PGVECTOR_PORT}/{self.PGVECTOR_DATABASE}"
        )

    def upsert_vectors(self, collection_name: str, embeddings: List[List[float]], 
                      metadata: List[Dict[str, Any]], contents: List[str]):
        with Session(self.engine) as session:
            for embedding, meta, content in zip(embeddings, metadata, contents):
                vector = VectorCollection(
                    collection_name=collection_name,
                    embedding=embedding,
                    metadata=meta,
                    content=content
                )
                session.merge(vector)
            session.commit()

    def query_collection(self, collection_name: str, query_embedding: List[float], 
                        limit: int = 10) -> List[Dict[str, Any]]:
        with Session(self.engine) as session:
            results = session.query(VectorCollection).filter(
                VectorCollection.collection_name == collection_name
            ).order_by(
                VectorCollection.embedding.cosine_distance(query_embedding)
            ).limit(limit).all()
            
            return [{
                'content': r.content,
                'metadata': r.metadata,
                'distance': r.embedding.cosine_distance(query_embedding)
            } for r in results]

    def list_collections(self) -> List[str]:
        with Session(self.engine) as session:
            collections = session.query(VectorCollection.collection_name).distinct().all()
            return [c[0] for c in collections]

    def delete_collection(self, collection_name: str):
        with Session(self.engine) as session:
            session.query(VectorCollection).filter(
                VectorCollection.collection_name == collection_name
            ).delete()
            session.commit()

    def get_collection(self, collection_name: str) -> List[Dict[str, Any]]:
        with Session(self.engine) as session:
            results = session.query(VectorCollection).filter(
                VectorCollection.collection_name == collection_name
            ).all()
            return [{
                'content': r.content,
                'metadata': r.metadata,
                'embedding': r.embedding.tolist()
            } for r in results]