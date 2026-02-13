from pathlib import Path
import json

"""
ChromaDB Client for CV embeddings storage
"""

# For POC: simple file-based storage instead of ChromaDB
# In production, use actual ChromaDB

class SimpleVectorDB:
    """Simple vector database using JSON files"""
    
    def __init__(self, db_dir: Path):
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.db_dir / "index.json"
        self.load_index()
    
    def load_index(self):
        """Load index from file"""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                self.index = json.load(f)
        else:
            self.index = {}
    
    def save_index(self):
        """Save index to file"""
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2)
    
    def add_document(self, doc_id: str, text: str, metadata: dict = None):
        """Add document to vector DB"""
        self.index[doc_id] = {
            "text": text,
            "metadata": metadata or {}
        }
        self.save_index()
    
    def query(self, query_text: str, top_k: int = 5) -> list:
        """Simple text-based query"""
        results = []
        
        query_words = set(query_text.lower().split())
        
        for doc_id, doc_data in self.index.items():
            doc_text = doc_data.get("text", "").lower()
            doc_words = set(doc_text.split())
            
            # Simple intersection-based matching
            matches = len(query_words & doc_words)
            
            if matches > 0:
                results.append({
                    "id": doc_id,
                    "score": matches / len(query_words),
                    "metadata": doc_data.get("metadata", {})
                })
        
        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results[:top_k]
    
    def get_document(self, doc_id: str) -> dict:
        """Get document by ID"""
        return self.index.get(doc_id)
    
    def delete_document(self, doc_id: str):
        """Delete document"""
        if doc_id in self.index:
            del self.index[doc_id]
            self.save_index()

# Initialize global vector DB
_vector_db = None

def get_vector_db(db_dir: Path = None):
    """Get vector database instance"""
    global _vector_db
    
    if _vector_db is None:
        if db_dir is None:
            db_dir = Path(__file__).parent.parent / "data" / "vector_db"
        _vector_db = SimpleVectorDB(db_dir)
    
    return _vector_db
