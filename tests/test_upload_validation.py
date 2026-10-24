import io
import unittest
import zipfile

from werkzeug.datastructures import FileStorage

from tests._load import load

uv = load("app/services/upload_validation.py", "upload_validation")


def _storage(data: bytes) -> FileStorage:
    return FileStorage(stream=io.BytesIO(data), filename="cv")


def _docx_bytes(include_document=True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        if include_document:
            z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


class UploadValidationTests(unittest.TestCase):
    def test_accepts_pdf_with_correct_magic_bytes(self):
        uv.validate_upload(_storage(b"%PDF-1.4 body"), "pdf")

    def test_rejects_executable_renamed_to_pdf(self):
        with self.assertRaises(uv.UploadRejected):
            uv.validate_upload(_storage(b"MZ\x90\x00payload"), "pdf")

    def test_accepts_real_docx(self):
        uv.validate_upload(_storage(_docx_bytes()), "docx")

    def test_rejects_zip_without_word_document(self):
        with self.assertRaises(uv.UploadRejected):
            uv.validate_upload(_storage(_docx_bytes(include_document=False)), "docx")

    def test_rejects_non_zip_as_docx(self):
        with self.assertRaises(uv.UploadRejected):
            uv.validate_upload(_storage(b"PK\x03\x04not really a zip"), "docx")

    def test_rejects_empty_file(self):
        with self.assertRaises(uv.UploadRejected):
            uv.validate_upload(_storage(b""), "pdf")

    def test_rejects_oversized_file(self):
        too_big = b"%PDF-" + b"0" * (uv.MAX_UPLOAD_BYTES + 1)
        with self.assertRaises(uv.UploadRejected):
            uv.validate_upload(_storage(too_big), "pdf")

    def test_rejects_unsupported_extension(self):
        with self.assertRaises(uv.UploadRejected):
            uv.validate_upload(_storage(b"%PDF-1.4"), "exe")

    def test_stream_is_rewound_after_success(self):
        storage = _storage(b"%PDF-1.4 body")
        uv.validate_upload(storage, "pdf")
        self.assertEqual(storage.stream.tell(), 0)


if __name__ == "__main__":
    unittest.main()
