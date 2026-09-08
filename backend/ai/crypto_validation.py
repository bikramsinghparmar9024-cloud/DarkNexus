"""
Cryptocurrency Address Validation.

A regex can tell that something is shaped like a Bitcoin address. It cannot
tell whether it is one. That distinction matters here because addresses reach
this system through lossy channels - OCR of a screenshot, a re-typed forum
post, a truncated listing - and a mangled address still matches the shape:

    real     1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
    OCR read 1A1zP1eP5QGefi2DMPTITL5SLmv7DiviNa    ('f' misread as 'I' and 'i')

Both pass a regex. Only one is an address. Recording the second as evidence
puts a wallet in a case file that belongs to nobody, and a blockchain trace
against it returns nothing - which looks like a dead end rather than a
transcription error.

Bitcoin and Ethereum both carry checksums precisely so this can be caught:

  * base58check (addresses starting 1 or 3) - a 4-byte double-SHA256 checksum
  * bech32 / bech32m (bc1...)               - BIP-173 / BIP-350 polymod
  * EIP-55 (Ethereum)                       - capitalisation encodes a checksum,
                                               verifiable only for mixed-case

Addresses that fail are not discarded. They are recorded separately as
unverified, because "an address was present but could not be read reliably"
is itself worth knowing - it is just not something to trace or to put in a
dossier as fact.
"""

from typing import Any, Dict, List, Optional
import hashlib
import re

# ── base58check (P2PKH "1...", P2SH "3...") ──────────────────────────

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(_B58_ALPHABET)}

# Version byte -> what the address is.
_B58_VERSIONS = {
    0x00: "P2PKH (mainnet)",
    0x05: "P2SH (mainnet)",
    0x6F: "P2PKH (testnet)",
    0xC4: "P2SH (testnet)",
}


def _b58_decode(address: str) -> Optional[bytes]:
    """Decode base58 to raw bytes, preserving leading-zero bytes."""
    number = 0
    for char in address:
        index = _B58_INDEX.get(char)
        if index is None:
            return None
        number = number * 58 + index

    decoded = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    # Each leading '1' encodes one leading zero byte.
    leading_zeros = len(address) - len(address.lstrip("1"))
    return b"\x00" * leading_zeros + decoded


def validate_base58check(address: str) -> Dict[str, Any]:
    raw = _b58_decode(address)
    if raw is None:
        return {"valid": False, "reason": "contains characters outside the base58 alphabet"}
    if len(raw) != 25:
        return {"valid": False,
                "reason": f"decodes to {len(raw)} bytes, expected 25"}

    payload, checksum = raw[:21], raw[21:]
    expected = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    if checksum != expected:
        return {"valid": False,
                "reason": "checksum mismatch - the address is mistyped, "
                          "truncated or misread"}

    version = payload[0]
    return {
        "valid": True,
        "address_type": _B58_VERSIONS.get(version, f"unknown version byte 0x{version:02x}"),
        "network": "testnet" if version in (0x6F, 0xC4) else "mainnet",
    }


# ── bech32 / bech32m (native segwit, "bc1...") ───────────────────────

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_CONST = 1
_BECH32M_CONST = 0x2BC830A3


def _bech32_polymod(values: List[int]) -> int:
    generator = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for i in range(5):
            checksum ^= generator[i] if ((top >> i) & 1) else 0
    return checksum


def _bech32_hrp_expand(hrp: str) -> List[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def validate_bech32(address: str) -> Dict[str, Any]:
    lowered = address.lower()
    if address != lowered and address != address.upper():
        return {"valid": False, "reason": "bech32 addresses must not mix case"}

    if "1" not in lowered:
        return {"valid": False, "reason": "missing separator"}

    position = lowered.rfind("1")
    hrp, data_part = lowered[:position], lowered[position + 1:]
    if hrp not in ("bc", "tb") or len(data_part) < 6:
        return {"valid": False, "reason": "unrecognised human-readable part"}

    data = []
    for char in data_part:
        index = _BECH32_CHARSET.find(char)
        if index == -1:
            return {"valid": False, "reason": "invalid bech32 character"}
        data.append(index)

    checksum = _bech32_polymod(_bech32_hrp_expand(hrp) + data)
    witness_version = data[0]

    # Version 0 uses bech32; versions 1+ (taproot and later) use bech32m.
    expected = _BECH32_CONST if witness_version == 0 else _BECH32M_CONST
    if checksum != expected:
        return {"valid": False,
                "reason": "checksum mismatch - the address is mistyped, "
                          "truncated or misread"}

    return {
        "valid": True,
        "address_type": "P2WPKH/P2WSH (segwit v0)" if witness_version == 0
                        else f"segwit v{witness_version}",
        "network": "mainnet" if hrp == "bc" else "testnet",
    }


def validate_btc_address(address: str) -> Dict[str, Any]:
    """Validate a Bitcoin address of any common form."""
    address = (address or "").strip()
    if not address:
        return {"valid": False, "reason": "empty"}

    if address.lower().startswith(("bc1", "tb1")):
        result = validate_bech32(address)
    elif address[0] in "123mn2":
        result = validate_base58check(address)
    else:
        result = {"valid": False, "reason": "unrecognised address prefix"}

    result["address"] = address
    result["currency"] = "BTC"
    return result


# ── Ethereum (EIP-55) ────────────────────────────────────────────────

_ETH_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def validate_eth_address(address: str) -> Dict[str, Any]:
    """
    Validate an Ethereum address.

    An all-lowercase or all-uppercase address carries no checksum, so it can
    only be confirmed well-formed. A mixed-case address encodes an EIP-55
    checksum in its capitalisation and can be verified properly.
    """
    address = (address or "").strip()
    result: Dict[str, Any] = {"address": address, "currency": "ETH"}

    if not _ETH_RE.match(address):
        result.update({"valid": False, "reason": "not a 40-character hex address"})
        return result

    body = address[2:]
    if body == body.lower() or body == body.upper():
        result.update({
            "valid": True,
            "checksum_verified": False,
            "reason": "well-formed, but single-case addresses carry no "
                      "EIP-55 checksum to verify against",
        })
        return result

    digest = hashlib.sha3_256  # placeholder, replaced below
    try:
        # EIP-55 uses Keccak-256, which is not SHA3-256. Fall back gracefully
        # when a Keccak implementation is unavailable.
        from Crypto.Hash import keccak  # type: ignore
        hasher = keccak.new(digest_bits=256)
        hasher.update(body.lower().encode())
        hashed = hasher.hexdigest()
    except Exception:
        result.update({
            "valid": True,
            "checksum_verified": False,
            "reason": "well-formed; EIP-55 verification needs a Keccak-256 "
                      "implementation (pip install pycryptodome)",
        })
        return result

    expected = "".join(
        char.upper() if int(hashed[i], 16) >= 8 else char.lower()
        for i, char in enumerate(body.lower())
    )
    if expected != body:
        result.update({
            "valid": False,
            "checksum_verified": False,
            "reason": "EIP-55 checksum mismatch - the address is mistyped or misread",
        })
        return result

    result.update({"valid": True, "checksum_verified": True})
    return result


def validate_address(address: str, currency: str = "BTC") -> Dict[str, Any]:
    """Validate an address of the given currency."""
    if currency.upper() == "ETH":
        return validate_eth_address(address)
    return validate_btc_address(address)


def partition_addresses(addresses: List[str], currency: str = "BTC"):
    """
    Split candidates into verified and unverified.

    Verified addresses are safe to trace, link and cite. Unverified ones are
    kept with the reason they failed, because the fact that an address was
    present is itself intelligence even when the transcription is unusable.
    """
    verified: List[str] = []
    unverified: List[Dict[str, Any]] = []

    for address in addresses or []:
        result = validate_address(address, currency)
        if result.get("valid"):
            verified.append(address)
        else:
            unverified.append({
                "address": address,
                "currency": currency.upper(),
                "reason": result.get("reason", "failed validation"),
            })

    return verified, unverified
