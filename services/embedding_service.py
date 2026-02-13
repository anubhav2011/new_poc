import json
from typing import List

"""
Embedding Service - Generate and store embeddings in ChromaDB
"""

def create_cv_embedding_text(worker_data: dict, experience_data: dict) -> str:
    """Create text for embedding from CV data"""
    
    parts = [
        f"Worker: {worker_data.get('name', '')}",
        f"Primary skill: {experience_data.get('primary_skill', '')}",
        f"Experience: {experience_data.get('experience_years', 0)} years",
        f"Skills: {', '.join(experience_data.get('skills', []))}",
        f"Location: {experience_data.get('preferred_location', '')}",
        f"Address: {worker_data.get('address', '')}",
    ]
    
    return " ".join(parts)

def prepare_for_chromadb(
    worker_id: str, 
    worker_data: dict, 
    experience_data: dict
) -> dict:
    """
    Prepare CV data for ChromaDB storage
    """
    
    embedding_text = create_cv_embedding_text(worker_data, experience_data)
    
    # Metadata
    metadata = {
        "worker_id": worker_id,
        "name": worker_data.get('name', ''),
        "primary_skill": experience_data.get('primary_skill', ''),
        "experience_years": experience_data.get('experience_years', 0),
        "location": experience_data.get('preferred_location', ''),
    }
    
    return {
        "id": worker_id,
        "document": embedding_text,
        "metadata": metadata
    }

def generate_mock_embedding(text: str) -> List[float]:
    """
    Generate mock embedding vector.
    In production, use a real embedding model.
    """
    # For POC: return a fixed-size vector based on text hash
    import hashlib
    
    hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
    embedding = []
    
    for i in range(384):  # 384-dimensional embedding
        embedding.append((hash_val >> i % 32) & 1)
        hash_val = hash(str(hash_val))
    
    # Normalize to float
    return [float(x) / 384 for x in embedding]
