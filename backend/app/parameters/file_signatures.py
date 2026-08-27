"""Magic-byte check for uploads, on top of the existing extension check in
main.py's _receive_and_parse — catches a mislabeled or malicious file (e.g.
an .html payload renamed to .pdf) before it reaches `unstructured`.

Not a full type-sniffing library: just enough signature coverage for the
extensions main.py.SUPPORTED_EXTENSIONS actually accepts. Text-based formats
(csv/tsv/txt/html/eml) have no reliable magic bytes, so they're not checked
here — extension is the only signal available for those, same as today.
"""

_ZIP_MAGIC = b"PK\x03\x04"  # xlsx, docx, xls (some variants), msg is OLE not zip

_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".docx": (_ZIP_MAGIC,),
    ".xlsx": (_ZIP_MAGIC,),
    ".xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", _ZIP_MAGIC),
    ".doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".msg": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".bmp": (b"BM",),
}


def matches_signature(ext: str, content: bytes) -> bool:
    """True if `content` starts with a known magic byte sequence for `ext`,
    or if `ext` has no signature registered (text-based formats — nothing to
    check, extension is the only available signal)."""
    signatures = _SIGNATURES.get(ext.lower())
    if signatures is None:
        return True
    return any(content.startswith(sig) for sig in signatures)
