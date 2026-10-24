"""
Content validation for uploaded CVs.

Extension checks alone are not enough: a renamed file can carry anything.
We verify the file's magic bytes (PDF) or ZIP/OOXML structure (DOCX) and
enforce a size cap before the file is written to disk or parsed.
"""
import zipfile
from typing import Tuple

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # keep in sync with MAX_CONTENT_LENGTH


class UploadRejected(Exception):
    """Raised when an uploaded file fails content validation."""


def _read_head(stream, n: int) -> bytes:
    pos = stream.tell()
    head = stream.read(n)
    stream.seek(pos)
    return head


def _size_of(stream) -> int:
    pos = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(pos)
    return size


def validate_upload(file_storage, ext: str) -> None:
    """
    Validate an uploaded FileStorage object. Raises UploadRejected on failure.
    Leaves the stream positioned at 0 on success.
    """
    stream = file_storage.stream
    size = _size_of(stream)
    if size == 0:
        raise UploadRejected("The uploaded file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise UploadRejected("File is too large. The maximum size is 10 MB.")

    ext = (ext or "").lower()
    if ext == "pdf":
        if not _read_head(stream, 5).startswith(b"%PDF-"):
            raise UploadRejected("That file does not look like a valid PDF.")
    elif ext == "docx":
        if not _read_head(stream, 4).startswith(b"PK"):
            raise UploadRejected("That file does not look like a valid Word document.")
        try:
            pos = stream.tell()
            stream.seek(0)
            with zipfile.ZipFile(stream) as zf:
                names = set(zf.namelist())
                if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                    raise UploadRejected("That file is not a valid Word (.docx) document.")
                # Guard against zip bombs: cap total uncompressed size.
                total = sum(i.file_size for i in zf.infolist())
                if total > 50 * 1024 * 1024:
                    raise UploadRejected("That Word document is too large to process.")
            stream.seek(pos)
        except zipfile.BadZipFile:
            raise UploadRejected("That file does not look like a valid Word document.")
    else:
        raise UploadRejected("Only PDF and DOCX files are supported.")

    stream.seek(0)
