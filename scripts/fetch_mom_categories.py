"""Download the per-category SLOSH MOM GeoTIFFs (high tide, Cat 1-5) from
NOAA's national zip without downloading the whole 1.6 GB archive: read the
zip's central directory with HTTP range requests, then stream each member's
compressed bytes and inflate them to data/raw/mom/catN.tif.

    python scripts/fetch_mom_categories.py [1 2 3 4 5]
"""

from __future__ import annotations

import io
import struct
import sys
import zipfile
import zlib
from pathlib import Path

import httpx

from surge_exposure.config import settings

DEST = Path("data") / "raw" / "mom"


class HttpRangeFile(io.RawIOBase):
    """Minimal seekable read-only file over HTTP Range requests (enough for zipfile's directory scan)."""

    def __init__(self, url: str, client: httpx.Client):
        self.url, self.client, self.pos = url, client, 0
        self.size = int(client.head(url).headers["content-length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size or not len(b):
            return 0
        end = min(self.pos + len(b), self.size) - 1
        data = self.client.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}).content
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def fetch(category: int, client: httpx.Client, members: dict[str, zipfile.ZipInfo]) -> Path:
    name = next(n for n in members if n.lower().endswith(f"category{category}_mom_inundation_high.tif"))
    info = members[name]
    out = DEST / f"cat{category}.tif"
    if out.exists() and out.stat().st_size == info.file_size:
        print(f"cat{category}: cached")
        return out
    # Local file header: 30 fixed bytes + filename + extra field, then the compressed data.
    url = settings.storm_surge_download_url
    head = client.get(url, headers={"Range": f"bytes={info.header_offset}-{info.header_offset + 29}"}).content
    name_len, extra_len = struct.unpack("<HH", head[26:30])
    start = info.header_offset + 30 + name_len + extra_len
    end = start + info.compress_size - 1
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise RuntimeError(f"unsupported compression {info.compress_type} for {name}")
    inflater = zlib.decompressobj(-15) if info.compress_type == zipfile.ZIP_DEFLATED else None
    DEST.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    crc = 0
    with client.stream("GET", url, headers={"Range": f"bytes={start}-{end}"}) as resp, open(tmp, "wb") as f:
        resp.raise_for_status()
        for chunk in resp.iter_bytes(1 << 20):
            data = inflater.decompress(chunk) if inflater else chunk
            crc = zlib.crc32(data, crc)
            f.write(data)
        if inflater:
            tail = inflater.flush()
            crc = zlib.crc32(tail, crc)
            f.write(tail)
    if crc != info.CRC or tmp.stat().st_size != info.file_size:
        tmp.unlink()
        raise RuntimeError(f"cat{category}: CRC/size mismatch")
    tmp.replace(out)
    print(f"cat{category}: {info.file_size:,} bytes -> {out}")
    return out


def main() -> None:
    categories = [int(c) for c in sys.argv[1:]] or [1, 2, 3, 4, 5]
    with httpx.Client(timeout=600, follow_redirects=True) as client:
        zf = zipfile.ZipFile(io.BufferedReader(HttpRangeFile(settings.storm_surge_download_url, client), 1 << 16))
        members = {i.filename: i for i in zf.infolist()}
        for c in categories:
            fetch(c, client, members)


if __name__ == "__main__":
    main()
