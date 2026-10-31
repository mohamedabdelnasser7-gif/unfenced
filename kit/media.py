"""Customer photos: check one before the model sees it, and shape it for the model call.

Written new on 30 October 2026 for the event, from what its callers need, not from older code.
A photo is bytes from WhatsApp, which are untrusted: its type is read from its first bytes and
must match what WhatsApp said, and it must be a JPEG, PNG or WebP of at most 5 MB whose header
goes one field past the magic bytes (a JPEG marker, the PNG IHDR chunk, a WebP VP8 chunk).
"""
import base64
import hashlib

IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
HEAD_BYTES = 16  # the magic bytes plus the one field after them that sniff reads
WEBP_CHUNKS = (b"VP8 ", b"VP8L", b"VP8X")

OK, EMPTY, SIZE, TYPE, MISMATCH = "ok", "empty", "size", "type", "mismatch"


def _raw(data):
    """The bytes of data as one flat byte view, or None for anything that is not bytes-like."""
    try:
        return memoryview(data).cast("B")
    except (TypeError, ValueError):
        return None


def sniff(data):
    """The image type its first bytes show, or None when they show none of IMAGE_TYPES."""
    raw = _raw(data)
    head = bytes(raw[:HEAD_BYTES]) if raw is not None else b""
    if len(head) < HEAD_BYTES:
        return None
    marker = head[3:].lstrip(b"\xff")[:1]  # fill bytes (0xFF) may come before the first marker
    if head.startswith(b"\xff\xd8\xff") and marker and 0xc0 <= marker[0] <= 0xfe:
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n") and head[12:16] == b"IHDR":
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP" and head[12:16] in WEBP_CHUNKS:
        return "image/webp"
    return None


def check_image(data, mime):
    """(True, "ok") for a photo the model may see, else (False, why): empty, size, type or mismatch.
    The size is counted in bytes, and anything that is not bytes-like is refused as the wrong type."""
    raw = _raw(data)
    if raw is None:
        return False, TYPE
    if not raw.nbytes:
        return False, EMPTY
    if raw.nbytes > MAX_IMAGE_BYTES:
        return False, SIZE
    if mime not in IMAGE_TYPES:
        return False, TYPE
    if sniff(raw) != mime:
        return False, MISMATCH
    return True, OK


def image_part(data, mime):
    """One image part of a chat message, the photo inline as base64."""
    return {"type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}}


def fingerprint(kind, data, mime):
    """What the chat log keeps of a photo or voice note: its kind, its SHA-256 and its type, never the bytes."""
    return {"kind": kind, "sha256": hashlib.sha256(data).hexdigest(), "mime": mime}
