"""
The committed certificate file for egazette.gov.in (audit finding C-4).

Everything here is OFFLINE: it checks that the file holds the certificates we
think it holds and that each one really is signed by the one above it, ending at
`ISRG Root X1` as `certifi` ships it. No network, so this runs in CI and on a
plane.

Why it matters: this file is what lets the project check e-Gazette's identity
instead of switching the check off. If somebody swapped a certificate into it,
or it silently lost its trust anchor, the check would be theatre. See
certs/README.md for the whole story, including the part the audit got wrong
(the server omits its intermediate; the root was never missing).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

certifi = pytest.importorskip("certifi")
x509 = pytest.importorskip("cryptography.x509")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, padding  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CHAIN_PEM = REPO_ROOT / "certs" / "egazette-chain.pem"

TRUST_ANCHOR = "CN=ISRG Root X1,O=Internet Security Research Group,C=US"

# Recorded when the file was built, 30 September 2026. A change here is not
# necessarily wrong — Let's Encrypt rotates intermediates — but it must be a
# deliberate, reviewed change, made with scripts/refresh_egazette_chain.py,
# which re-checks every signature before writing.
EXPECTED = {
    "CN=ISRG Root X1,O=Internet Security Research Group,C=US":
        "96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6",
    "CN=Root YR,O=ISRG,C=US":
        "072639d0b140d5bffae16ad9c3f6cc6086040621f51ee61a6d46a8915c07cf76",
    "CN=YR2,O=Let's Encrypt,C=US":
        "238b85a0099c65b970477d5724f1a1d475ce5058cffe4efa8733899bdb863c47",
}


def _load_pem_certs(text: str):
    blobs, current = [], []
    for line in text.splitlines():
        if line.startswith("-----BEGIN CERTIFICATE-----"):
            current = [line]
        elif line.startswith("-----END CERTIFICATE-----"):
            current.append(line)
            blobs.append("\n".join(current))
            current = []
        elif current:
            current.append(line)
    out = []
    for blob in blobs:
        try:
            out.append(x509.load_pem_x509_certificate(blob.encode()))
        except Exception:
            continue
    return out


def _sha256(cert) -> str:
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def _signed_by(child, parent) -> bool:
    key = parent.public_key()
    try:
        if isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(child.signature, child.tbs_certificate_bytes,
                       ec.ECDSA(child.signature_hash_algorithm))
        else:
            key.verify(child.signature, child.tbs_certificate_bytes,
                       padding.PKCS1v15(), child.signature_hash_algorithm)
    except Exception:
        return False
    return True


@pytest.fixture(scope="module")
def chain():
    assert CHAIN_PEM.exists(), f"{CHAIN_PEM} is missing — see certs/README.md"
    return _load_pem_certs(CHAIN_PEM.read_text(encoding="utf-8"))


def test_the_file_holds_exactly_the_reviewed_certificates(chain):
    got = {cert.subject.rfc4514_string(): _sha256(cert) for cert in chain}
    assert got == EXPECTED, (
        "certs/egazette-chain.pem is not what was reviewed. If Let's Encrypt has "
        "rotated the intermediate, rebuild it with "
        "`python scripts/refresh_egazette_chain.py --apply` and update EXPECTED here."
    )


def test_the_trust_anchor_is_the_one_certifi_ships(chain):
    """
    The root in this file must be byte-identical to certifi's own ISRG Root X1.
    If it is not, the file is introducing a new trust anchor, which is exactly
    what must never happen.
    """
    ours = {c.subject.rfc4514_string(): _sha256(c) for c in chain}[TRUST_ANCHOR]
    from_certifi = {
        c.subject.rfc4514_string(): _sha256(c)
        for c in _load_pem_certs(Path(certifi.where()).read_text(encoding="utf-8"))
    }
    assert TRUST_ANCHOR in from_certifi, "certifi no longer ships ISRG Root X1"
    assert ours == from_certifi[TRUST_ANCHOR]


def test_every_link_is_really_signed_by_the_one_above_it(chain):
    by_subject = {c.subject.rfc4514_string(): c for c in chain}
    anchor = by_subject[TRUST_ANCHOR]
    root_yr = by_subject["CN=Root YR,O=ISRG,C=US"]
    yr2 = by_subject["CN=YR2,O=Let's Encrypt,C=US"]
    assert _signed_by(root_yr, anchor), "Root YR is not signed by ISRG Root X1"
    assert _signed_by(yr2, root_yr), "YR2 is not signed by Root YR"
    assert anchor.issuer == anchor.subject, "the trust anchor must be self-signed"


def test_nothing_in_the_file_has_expired(chain):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    stale = [
        f"{c.subject.rfc4514_string()} expired {c.not_valid_after_utc.date()}"
        for c in chain if c.not_valid_after_utc <= now
    ]
    assert stale == [], (
        "expired certificate(s) in certs/egazette-chain.pem — rebuild with "
        "`python scripts/refresh_egazette_chain.py --apply`:\n" + "\n".join(stale)
    )


def test_the_discovery_module_points_at_this_file():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "src"))
    import discover_documents as dd
    assert dd.EGAZETTE_CHAIN_PEM == CHAIN_PEM
    assert dd._verify_arg("https://egazette.gov.in/WriteReadData/2025/268455.pdf") == str(CHAIN_PEM)
    assert dd._verify_arg("https://example.test/x.pdf") is True, \
        "every other host uses the ordinary trust store, not this file"
