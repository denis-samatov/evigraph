"""Canonical text, content hashes and MinHash signatures.

Evidence offsets are defined over the canonical text in Unicode code points, so the
canonical form must be stable: NFC, unified line breaks, no trailing spaces.
"""

import hashlib
import re
import unicodedata

import numpy as np
from datasketch import LeanMinHash, MinHash

SHINGLE = 5
SCHEME = "affine32"
SEED = 1
_TOKEN = re.compile(r"\w+", re.UNICODE)


def canonicalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def shingles(text: str) -> set[bytes]:
    toks = _TOKEN.findall(text.lower())
    if len(toks) < SHINGLE:
        return {" ".join(toks).encode()}
    return {" ".join(toks[i : i + SHINGLE]).encode() for i in range(len(toks) - SHINGLE + 1)}


def minhash(text: str, num_perm: int) -> np.ndarray:
    m = MinHash(num_perm=num_perm, seed=SEED, scheme=SCHEME)
    m.update_batch(list(shingles(text)))
    return np.asarray(m.hashvalues, dtype=np.uint64)


def to_bytes(sig: np.ndarray) -> bytes:
    return sig.astype("<u8").tobytes()


def from_bytes(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="<u8").astype(np.uint64)


def jaccard(a: np.ndarray, b: np.ndarray) -> float:
    return LeanMinHash(seed=SEED, hashvalues=a, scheme=SCHEME).jaccard(
        LeanMinHash(seed=SEED, hashvalues=b, scheme=SCHEME)
    )


def band_buckets(sig: np.ndarray, bands: int) -> list[int]:
    """LSH bucket per band as a signed 64-bit integer (fits a BIGINT column)."""
    rows = len(sig) // bands
    out = []
    for b in range(bands):
        digest = hashlib.blake2b(sig[b * rows : (b + 1) * rows].tobytes(), digest_size=8)
        out.append(int.from_bytes(digest.digest(), "big", signed=True))
    return out
