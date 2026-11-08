"""Remove local Rust diagnostic source prefixes without changing executable code."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import struct


def sections(data: bytes) -> list[tuple[str, int, int]]:
    if data[:2] != b"MZ":
        raise ValueError("Not a PE executable")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Invalid PE header")
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    # Editing a signed executable would invalidate its signature.
    if struct.unpack_from("<H", data, pe + 24)[0] != 0x20B:
        raise ValueError("Expected a PE32+ executable")
    if struct.unpack_from("<II", data, pe + 24 + 112 + 4 * 8) != (0, 0):
        raise ValueError("Refusing to modify a signed executable")
    result = []
    for index in range(count):
        offset = pe + 24 + optional + index * 40
        name = data[offset:offset + 8].rstrip(b"\0").decode("ascii")
        size, start = struct.unpack_from("<II", data, offset + 16)
        result.append((name, start, start + size))
    return result


def redact(data: bytes, private_prefix: str) -> tuple[bytes, int]:
    layout = sections(data)
    output = bytearray(data)
    replacements = 0
    variants = {private_prefix, private_prefix.replace("\\", "/")}
    for prefix in variants:
        needle = prefix.encode("utf-8")
        if not needle:
            raise ValueError("An empty private prefix is invalid")
        public = b"C:\\Build\\" if "\\" in prefix else b"/build/"
        replacement = (public + b"_" * len(needle))[:len(needle)]
        for match in re.finditer(re.escape(needle), data):
            start, end = match.span()
            owner = next((s for s in layout if s[1] <= start and end <= s[2]), None)
            # Only known Rust diagnostic paths in read-only data may be changed. Equal byte
            # lengths preserve pointers and string lengths; all machine code stays identical.
            tail = data[end:min(end + 192, len(data))]
            if owner is None or owner[0] != ".rdata" or b".rs" not in tail:
                raise ValueError("A private path is not a recognized Rust diagnostic string")
            output[start:end] = replacement
            replacements += 1
    result = bytes(output)
    if len(result) != len(data) or sections(result) != layout:
        raise ValueError("PE layout changed")
    for name, start, end in layout:
        if name != ".rdata" and result[start:end] != data[start:end]:
            raise ValueError("Executable code or another PE section changed")
    return result, replacements


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--private-prefix", default=str(Path.home()))
    args = parser.parse_args()
    result, count = redact(args.source.read_bytes(), args.private_prefix)
    args.destination.write_bytes(result)
    print(f"Anonymized {count} diagnostic source prefixes; machine code and PE layout unchanged.")


if __name__ == "__main__":
    main()
