import struct
import unittest

from public_binary import redact


def fixture(text: bytes, data: bytes) -> bytes:
    image = bytearray(0x800)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HH", image, 0x84, 0x8664, 2)
    struct.pack_into("<H", image, 0x94, 0xF0)
    struct.pack_into("<H", image, 0x98, 0x20B)
    for i, (name, start) in enumerate([(b".text", 0x400), (b".rdata", 0x600)]):
        offset = 0x188 + i * 40
        image[offset:offset + len(name)] = name
        struct.pack_into("<II", image, offset + 16, 0x200, start)
    image[0x400:0x400 + len(text)] = text
    image[0x600:0x600 + len(data)] = data
    return bytes(image)


class PublicBinaryTests(unittest.TestCase):
    def test_only_diagnostic_data_is_redacted(self):
        original = fixture(b"machine-code", b"C:\\Users\\private\\library\\file.rs")
        public, count = redact(original, "C:\\Users\\private")
        self.assertEqual(count, 1)
        self.assertNotIn(b"private", public)
        self.assertEqual(original[:0x600], public[:0x600])
        self.assertEqual(len(original), len(public))

    def test_code_section_is_never_modified(self):
        with self.assertRaises(ValueError):
            redact(fixture(b"C:\\Users\\private\\file.rs", b""), "C:\\Users\\private")

    def test_non_diagnostic_path_is_refused(self):
        with self.assertRaises(ValueError):
            redact(fixture(b"", b"C:\\Users\\private\\runtime.ttf\0"), "C:\\Users\\private")

    def test_signed_binary_is_refused(self):
        image = bytearray(fixture(b"", b"C:\\Users\\private\\file.rs"))
        struct.pack_into("<II", image, 0x98 + 112 + 4 * 8, 0x1000, 20)
        with self.assertRaises(ValueError):
            redact(bytes(image), "C:\\Users\\private")


if __name__ == "__main__":
    unittest.main()
