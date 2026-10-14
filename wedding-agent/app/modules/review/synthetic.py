"""内存生成双人几何示意图；不冒充真人或真实人脸评测素材。"""

import struct
import zlib


def make_couple_png() -> bytes:
    width, height = 256, 192
    rows = []
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            color = (235, 228, 220)
            for center, clothes in [(85, (40, 48, 65)), (170, (255, 255, 255))]:
                if ((x - center) / 20) ** 2 + ((y - 65) / 24) ** 2 <= 1:
                    color = (215, 173, 145)
                if 92 <= y <= 180 and abs(x - center) < 28:
                    color = clothes
                if y in (61, 62) and abs(abs(x - center) - 7) < 2:
                    color = (40, 40, 40)
            row.extend(color)
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")
