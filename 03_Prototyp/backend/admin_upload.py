"""
Admin-Upload-Endpoint: Dokumente direkt über die Web-UI hochladen.
Wird in main.py eingebunden via: from admin_upload import router as upload_router
"""

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from auth import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])

UPLOAD_DIR = Path(os.getenv("KNOWLEDGE_BASE_PATH", "./knowledge_base"))
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}
MAX_FILE_SIZE_MB = 10


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    api_key: str = Depends(require_admin),
):
    """Einzelnes Dokument in die Wissensbasis hochladen."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Dateityp nicht erlaubt. Erlaubt: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / file.filename

    size = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 64):
            size += len(chunk)
            if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Datei zu groß. Max. {MAX_FILE_SIZE_MB} MB.",
                )
            f.write(chunk)

    return {"status": "ok", "filename": file.filename, "size_kb": round(size / 1024, 1)}


@router.get("/documents")
def list_documents(api_key: str = Depends(require_admin)):
    """Alle Dokumente in der Wissensbasis auflisten."""
    if not UPLOAD_DIR.exists():
        return {"documents": []}
    docs = [
        {
            "name": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "suffix": f.suffix,
        }
        for f in sorted(UPLOAD_DIR.iterdir())
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
    ]
    return {"documents": docs, "count": len(docs)}


@router.delete("/documents/{filename}")
def delete_document(filename: str, api_key: str = Depends(require_admin)):
    """Einzelnes Dokument aus der Wissensbasis löschen."""
    target = UPLOAD_DIR / filename
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden.")
    target.unlink()
    return {"status": "ok", "deleted": filename}
