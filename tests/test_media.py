"""kit/media.py: the photo check and the shapes the model call and the chat log take."""
import base64
import hashlib
import unittest

from kit import media

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 20
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR" + b"\x00" * 20
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 8


class Sniff(unittest.TestCase):
    def test_reads_the_type_from_the_first_bytes(self):
        self.assertEqual(media.sniff(JPEG), "image/jpeg")
        self.assertEqual(media.sniff(PNG), "image/png")
        self.assertEqual(media.sniff(WEBP), "image/webp")

    def test_anything_else_is_none(self):
        for data in (b"", b"GIF89a" + b"\x00" * 10, b"RIFF\x10\x00\x00\x00WAVE", b"RIFFWEBP", b"<svg>", b"%PDF-1.7"):
            self.assertIsNone(media.sniff(data), data)

    def test_every_magic_byte_counts(self):
        """Review t261030m round 1: a shortened magic or a dropped RIFF is no image."""
        for data in (b"\xff\xd8\x00\xe0" + b"\x00" * 20, b"\x00\xd8\xff\xe0" + b"\x00" * 20,
                     b"\x89PNG\x00\x00\x00\x00\x00\x00\x00\x0dIHDR" + b"\x00" * 8,
                     b"\x89PNG\r\n\x1a\x00\x00\x00\x00\x0dIHDR" + b"\x00" * 8,
                     b"XXXX\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 8):
            self.assertIsNone(media.sniff(data), data)

    def test_a_header_cut_after_the_magic_is_no_image(self):
        """Review t261030m round 1, finding 2: the field after the magic bytes must be there and right."""
        for data in (b"\xff\xd8\xff", b"\xff\xd8\xff\xe0", b"\x89PNG\r\n\x1a\n", b"RIFF\x00\x00\x00\x00WEBP",
                     b"\xff\xd8\xff\x00" + b"\x00" * 20, b"\x89PNG\r\n\x1a\n" + b"\x00" * 20,
                     b"RIFF\x10\x00\x00\x00WEBPJUNK" + b"\x00" * 8):
            self.assertIsNone(media.sniff(data), data)
            self.assertFalse(media.check_image(data, "image/jpeg")[0], data)

    def test_every_real_header_kind_passes(self):
        """Review t261030m round 2: each JPEG first marker, fill bytes, and all three WebP chunks."""
        for marker in (b"\xc0", b"\xdb", b"\xe0", b"\xe1", b"\xee", b"\xfe", b"\xff\xff\xe0"):
            self.assertEqual(media.sniff(b"\xff\xd8\xff" + marker + b"\x00" * 16), "image/jpeg", marker)
        for marker in (b"\xbf", b"\x00", b"\xff" * 13):
            self.assertIsNone(media.sniff(b"\xff\xd8\xff" + marker + b"\x00" * 16), marker)
        for chunk in (b"VP8 ", b"VP8L", b"VP8X"):
            self.assertEqual(media.sniff(b"RIFF\x10\x00\x00\x00WEBP" + chunk + b"\x00" * 8), "image/webp", chunk)
        self.assertIsNone(media.sniff(b"RIFF\x10\x00\x00\x00WAVEVP8 " + b"\x00" * 8))

    def test_bytearray_and_memoryview_read_the_same(self):
        for data in (bytearray(JPEG), memoryview(JPEG)):
            self.assertEqual(media.sniff(data), "image/jpeg")


class Check(unittest.TestCase):
    def test_a_good_photo_passes(self):
        for data, mime in ((JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")):
            self.assertEqual(media.check_image(data, mime), (True, "ok"))

    def test_refusals_name_why(self):
        self.assertEqual(media.check_image(b"", "image/jpeg"), (False, "empty"))
        self.assertEqual(media.check_image(JPEG, "image/gif"), (False, "type"))
        self.assertEqual(media.check_image(PNG, "image/jpeg"), (False, "mismatch"))
        self.assertEqual(media.check_image(b"<svg onload=x>", "image/png"), (False, "mismatch"))

    def test_the_type_must_come_normalised(self):
        """The channel normalises the type; check_image takes it as given, so the data: URI stays clean."""
        for mime in ("IMAGE/JPEG", "image/jpeg; q=1", " image/jpeg", None):
            self.assertEqual(media.check_image(JPEG, mime), (False, "type"), mime)

    def test_the_size_is_counted_in_bytes_not_items(self):
        """Review t261030m round 1, finding 1: a wide-item view of a big photo is still too big."""
        import array
        big = JPEG + b"\x00" * (media.MAX_IMAGE_BYTES - len(JPEG) + 4)
        self.assertEqual(media.check_image(memoryview(big).cast("I"), "image/jpeg"), (False, "size"))
        self.assertEqual(media.check_image(array.array("I", big), "image/jpeg"), (False, "size"))
        self.assertEqual(media.check_image(list(JPEG), "image/jpeg"), (False, "type"))
        self.assertEqual(media.check_image("not bytes", "image/jpeg"), (False, "type"))

    def test_the_size_cap_is_exact(self):
        at = JPEG + b"\x00" * (media.MAX_IMAGE_BYTES - len(JPEG))
        self.assertEqual(media.check_image(at, "image/jpeg"), (True, "ok"))
        self.assertEqual(media.check_image(at + b"\x00", "image/jpeg"), (False, "size"))


class Shapes(unittest.TestCase):
    def test_image_part_is_inline_base64(self):
        part = media.image_part(PNG, "image/png")
        self.assertEqual(part["type"], "image_url")
        url = part["image_url"]["url"]
        self.assertTrue(url.startswith("data:image/png;base64,"))
        self.assertEqual(base64.b64decode(url.split(",", 1)[1]), PNG)

    def test_fingerprint_keeps_no_bytes(self):
        fp = media.fingerprint("image", JPEG, "image/jpeg")
        self.assertEqual(fp, {"kind": "image", "sha256": hashlib.sha256(JPEG).hexdigest(), "mime": "image/jpeg"})


if __name__ == "__main__":
    unittest.main()
