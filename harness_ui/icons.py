"""Raster sizes of the app's simple H mark for Android installation."""
from functools import lru_cache
import struct
import zlib


@lru_cache(maxsize=3)
def png(size):
    if size not in (180, 192, 512):
        raise ValueError('unsupported icon size')
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    data = bytearray()
    for y in range(size):
        data.append(0)
        for x in range(size):
            px, py = x * 192 / size, y * 192 / size
            mark = (40 <= px <= 60 or 132 <= px <= 152) and 45 <= py <= 147 or 40 <= px <= 152 and 86 <= py <= 106
            data.extend((79, 195, 161) if mark else (17, 20, 19))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', size, size, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes(data))) + chunk(b'IEND', b'')
