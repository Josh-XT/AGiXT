"""
Migration script to move data from ChromaDB to pgvector.
This script should be run once when transitioning from ChromaDB to pgvector.
"""
import logging
import chromadb
from chromadb.config import Settings
import os
from os import getenv
from extensions.pgvector_database import pgvector_database
from tqdm import tqdm

def get_chroma_client():
    chroma_host = getenv("CHROMA_HOST")
    chroma_settings = Settings(
        anonymized_telemetry=False,
    )
    if chroma_host:
        try:
            chroma_api_key = getenv("CHROMA_API_KEY")
            chroma_headers = (
                {"Authorization": f"Bearer {chroma_api_key}"} if chroma_api_key else {}
            )
            return chromadb.HttpClient(
                host=chroma_host,
                port=getenv("CHROMA_PORT"),
                ssl=(False if getenv("CHROMA_SSL").lower() != "true" else True),
                headers=chroma_headers,
                settings=chroma_settings,
            )
        except Exception as e:
            logging.warning(f"Chroma server at {chroma_host} is not available: {e}")
            return None
    
    memories_dir = os.path.join(os.getcwd(), "memories")
    if not os.path.exists(memories_dir):
        return None
    
    return chromadb.PersistentClient(
        path=memories_dir,
        settings=chroma_settings,
    )

def migrate_data():
    chroma_client = get_chroma_client()
    if not chroma_client:
        logging.info("No ChromaDB data found to migrate")
        return
    
    pgvector_client = pgvector_database()
    
    try:
        collections = chroma_client.list_collections()
        for collection in collections:
            print(f"Migrating collection: {collection.name}")
            
            # Get all data from ChromaDB collection
            data = collection.get()
            
            if not data['ids']:
                continue
                
            # Migrate to pgvector in batches
            batch_size = 100
            total_batches = len(data['ids']) // batch_size + (1 if len(data['ids']) % batch_size else 0)
            
            for i in tqdm(range(total_batches)):
                start_idx = i * batch_size
                end_idx = min((i + 1) * batch_size, len(data['ids']))
                
                batch_ids = data['ids'][start_idx:end_idx]
                batch_embeddings = data['embeddings'][start_idx:end_idx]
                batch_metadatas = data['metadatas'][start_idx:end_idx]
                batch_documents = data['documents'][start_idx:end_idx]
                
                pgvector_client.upsert_vectors(
                    collection_name=collection.name,
                    embeddings=batch_embeddings,
                    metadata=[{**meta, 'id': id_} for meta, id_ in zip(batch_metadatas, batch_ids)],
                    contents=batch_documents
                )
            
            print(f"Successfully migrated {len(data['ids'])} records from collection {collection.name}")
            
    except Exception as e:
        logging.error(f"Error during migration: {e}")
        raise

if __name__ == "__main__":
    migrate_data()