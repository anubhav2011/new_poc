from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..db import crud
from ..config import PERSONAL_DOCUMENTS_DIR

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{worker_id}")
async def get_worker_document(worker_id: str):
    """Get document path for worker (personal document saved by form submit)."""

    worker = crud.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Find document for this worker (form saves to PERSONAL_DOCUMENTS_DIR)
    import os
    docs = [f for f in os.listdir(PERSONAL_DOCUMENTS_DIR) if f.startswith(worker_id)]

    if not docs:
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "worker_id": worker_id,
                "document": None
            }
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "worker_id": worker_id,
            "document": docs[0] if docs else None
        }
    )
