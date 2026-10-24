"""Pièces jointes : validation du contenu réel, stockage sur disque, droits.

Sécurité :
* le type est déterminé par les premiers octets du fichier (signature), jamais par l'en-tête envoyé par le client ;
* seules les images (png, jpeg, gif, webp) sont acceptées (pas de SVG : XSS) ; sprint 1 : une image par plainte ;
* le nom stocké sur disque est un uuid : le nom d'origine n'est qu'un libellé nettoyé (pas de path traversal) ;
* taille et nombre de fichiers limités ; en cas d'erreur sur un fichier, aucun fichier du lot n'est conservé.

Pour stocker ailleurs (Supabase Storage, S3...), remplacer l'écriture, `file_path`, `download` et `_remove`.
"""
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Attachment, Complaint, Status, User
from app.services.notification_service import notify

EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
CHUNK = 1024 * 1024


def sniff(head: bytes) -> str | None:
    """Type MIME d'après la signature du fichier (None si non autorisé)."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def clean_filename(raw: str | None, ext: str) -> str:
    name = os.path.basename((raw or "").replace("\\", "/"))
    name = re.sub(r"[^\w.\- ()]", "_", name, flags=re.UNICODE).strip(" .")
    stem = Path(name).stem[:100] or "file"
    return f"{stem}{ext}"  # l'extension affichée correspond toujours au vrai type


def upload_root() -> Path:
    return Path(settings.UPLOAD_DIR)


def file_path(attachment: Attachment) -> Path:
    return upload_root() / str(attachment.complaint_id) / attachment.stored_name


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def save_uploads(db: Session, complaint: Complaint, user: User, files: list[UploadFile]) -> Complaint:
    if complaint.status == Status.CLOSED:
        raise HTTPException(409, "La plainte est clôturée : plus de pièce jointe possible")
    if not files:
        raise HTTPException(422, "Aucun fichier envoyé")
    limit = settings.MAX_FILES_PER_COMPLAINT
    if len(complaint.attachments) + len(files) > limit:
        raise HTTPException(409, f"Maximum {limit} fichiers par plainte")

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    folder = upload_root() / str(complaint.id)
    written: list[Path] = []
    rows: list[Attachment] = []
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for f in files:
            head = f.file.read(32)
            f.file.seek(0)
            ctype = sniff(head)
            if not ctype:
                raise HTTPException(415, f"{f.filename or 'fichier'} : seules les images (png, jpeg, gif, webp) sont acceptées")
            stored = f"{uuid4().hex}{EXTENSIONS[ctype]}"
            path = folder / stored
            size = 0
            with open(path, "wb") as out:
                written.append(path)
                while chunk := f.file.read(CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(413, f"{f.filename or 'fichier'} dépasse {settings.MAX_UPLOAD_MB} Mo")
                    out.write(chunk)
            if size == 0:
                raise HTTPException(422, f"{f.filename or 'fichier'} est vide")
            rows.append(Attachment(
                complaint_id=complaint.id, uploaded_by_id=user.id, stored_name=stored, content_type=ctype,
                size=size, filename=clean_filename(f.filename, EXTENSIONS[ctype]),
            ))
        db.add_all(rows)
        if complaint.assigned_to_id and complaint.assigned_to_id != user.id:
            notify(db, complaint.assigned_to_id, complaint, f"New attachment on {complaint.reference}")
        db.commit()
    except BaseException:
        db.rollback()
        for p in written:  # tout ou rien : aucun fichier orphelin
            _remove(p)
        raise
    db.refresh(complaint)
    return complaint


def get_attachment_or_404(complaint: Complaint, attachment_id: int) -> Attachment:
    for a in complaint.attachments:
        if a.id == attachment_id:
            return a
    raise HTTPException(404, "Pièce jointe introuvable")


def download(attachment: Attachment) -> FileResponse:
    path = file_path(attachment)
    if not path.is_file():
        raise HTTPException(404, "Fichier introuvable sur le serveur")
    return FileResponse(
        path, media_type=attachment.content_type, filename=attachment.filename, content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"},
    )


def delete(db: Session, complaint: Complaint, attachment: Attachment, user: User) -> Complaint:
    if complaint.status == Status.CLOSED:
        raise HTTPException(409, "La plainte est clôturée")
    if attachment.uploaded_by_id != user.id:
        raise HTTPException(403, "Vous ne pouvez supprimer que vos propres pièces jointes")
    path = file_path(attachment)
    db.delete(attachment)
    db.commit()
    _remove(path)
    db.refresh(complaint)
    return complaint


def purge_complaint_files(complaint_id: int) -> None:
    shutil.rmtree(upload_root() / str(complaint_id), ignore_errors=True)
