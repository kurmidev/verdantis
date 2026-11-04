"""Prefixed ULIDs (A-101): 48-bit ms timestamp + 80 random bits, Crockford base32."""
import secrets
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str) -> str:
    n = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(_ALPHABET[n & 31])
        n >>= 5
    return f"{prefix}_{''.join(reversed(chars))}"
