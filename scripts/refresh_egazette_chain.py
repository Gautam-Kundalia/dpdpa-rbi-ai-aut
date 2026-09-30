"""
Rebuild certs/egazette-chain.pem — the certificate file that lets this project
check e-Gazette's identity properly instead of switching the check off.

Run this when a daily run reports `certificate verify failed` for
egazette.gov.in. See certs/README.md for the full background; the short version
is that the e-Gazette server does not send its intermediate certificate, so we
have to supply it ourselves, and Let's Encrypt rotates which intermediate it
issues from.

What it does:
  1. opens one TLS connection to egazette.gov.in and reads the certificate the
     site is presenting today (no HTTP request is sent);
  2. follows the "caIssuers" address printed inside that certificate to fetch
     the intermediate the server omits, and then the same for its issuer;
  3. checks every signature OFFLINE against certifi's own ISRG Root X1, so a
     tampered download cannot get in;
  4. writes certs/egazette-chain.pem and prints every fingerprint;
  5. proves the result by fetching https://egazette.gov.in/ using only that file.

Usage:
    python scripts/refresh_egazette_chain.py            # dry run: prints, writes nothing
    python scripts/refresh_egazette_chain.py --apply    # rewrites certs/egazette-chain.pem
"""
from __future__ import annotations

import argparse
import hashlib
import socket
import ssl
import sys
from pathlib import Path

import certifi
import requests
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_PEM = PROJECT_ROOT / "certs" / "egazette-chain.pem"
HOST = "egazette.gov.in"
USER_AGENT = "Mozilla/5.0 (compatible; DPDPAChangeMonitor/1.0)"
TRUST_ANCHOR_SUBJECT = "CN=ISRG Root X1,O=Internet Security Research Group,C=US"
MAX_LINKS = 4   # refuse to follow an unbounded chain of caIssuers addresses


def sha256_of(cert: x509.Certificate) -> str:
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def load_any(raw: bytes) -> x509.Certificate:
    try:
        return x509.load_der_x509_certificate(raw)
    except ValueError:
        return x509.load_pem_x509_certificate(raw)


def ca_issuers_url(cert: x509.Certificate) -> str | None:
    try:
        aia = cert.extensions.get_extension_for_class(x509.AuthorityInformationAccess).value
    except x509.ExtensionNotFound:
        return None
    for access in aia:
        if access.access_method._name == "caIssuers":
            return access.access_location.value
    return None


def signed_by(child: x509.Certificate, parent: x509.Certificate) -> bool:
    """Is `child` really signed by `parent`? Checked offline, no network."""
    public_key = parent.public_key()
    try:
        if isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(child.signature, child.tbs_certificate_bytes,
                              ec.ECDSA(child.signature_hash_algorithm))
        else:
            public_key.verify(child.signature, child.tbs_certificate_bytes,
                              padding.PKCS1v15(), child.signature_hash_algorithm)
    except Exception:
        return False
    return True


def certifi_trust_anchor() -> x509.Certificate:
    """ISRG Root X1 as certifi ships it — the one thing here we already trust."""
    blobs, current = [], []
    for line in Path(certifi.where()).read_text(encoding="utf-8").splitlines():
        if line.startswith("-----BEGIN CERTIFICATE-----"):
            current = [line]
        elif line.startswith("-----END CERTIFICATE-----"):
            current.append(line)
            blobs.append("\n".join(current))
            current = []
        elif current:
            current.append(line)
    for blob in blobs:
        try:
            cert = x509.load_pem_x509_certificate(blob.encode())
        except Exception:
            continue
        if cert.subject.rfc4514_string() == TRUST_ANCHOR_SUBJECT:
            return cert
    raise SystemExit(
        f"FATAL: {TRUST_ANCHOR_SUBJECT} is not in certifi ({certifi.where()}). "
        f"Cannot vouch for anything without it — stopping rather than committing a "
        f"certificate nothing verifies."
    )


def leaf_certificate() -> x509.Certificate:
    """The certificate egazette.gov.in presents. One handshake, no HTTP request."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((HOST, 443), timeout=60) as sock:
        with ctx.wrap_socket(sock, server_hostname=HOST) as tls:
            return x509.load_der_x509_certificate(tls.getpeercert(binary_form=True))


def describe(label: str, cert: x509.Certificate) -> None:
    print(f"  {label}")
    print(f"    subject : {cert.subject.rfc4514_string()}")
    print(f"    issuer  : {cert.issuer.rfc4514_string()}")
    print(f"    expires : {cert.not_valid_after_utc.date().isoformat()}")
    print(f"    sha256  : {sha256_of(cert)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="rewrite certs/egazette-chain.pem (default: dry run)")
    args = parser.parse_args()

    anchor = certifi_trust_anchor()
    print("Trust anchor, from certifi (nothing new is being trusted):")
    describe("ISRG Root X1", anchor)

    print(f"\nReading the certificate {HOST} presents today...")
    leaf = leaf_certificate()
    describe("website certificate", leaf)

    # Walk up the caIssuers addresses until we reach something the anchor signed.
    chain: list[x509.Certificate] = []
    cursor = leaf
    for _ in range(MAX_LINKS):
        if signed_by(cursor, anchor):
            break
        url = ca_issuers_url(cursor)
        if not url:
            print(f"\nFATAL: {cursor.subject.rfc4514_string()} carries no caIssuers "
                  f"address, so the missing link cannot be fetched. Nothing written.")
            return 2
        print(f"\nFetching the missing link from {url} ...")
        parent = load_any(requests.get(url, timeout=60).content)
        if not signed_by(cursor, parent):
            print(f"\nFATAL: the certificate at {url} did NOT sign "
                  f"{cursor.subject.rfc4514_string()}. Refusing to trust it. Nothing written.")
            return 2
        describe("fetched", parent)
        chain.append(parent)
        cursor = parent
    else:
        print(f"\nFATAL: followed {MAX_LINKS} links without reaching ISRG Root X1. "
              f"Nothing written — this needs a human look.")
        return 2

    if not signed_by(cursor, anchor):
        print("\nFATAL: the top of the chain is not signed by ISRG Root X1. Nothing written.")
        return 2
    print("\nEvery signature checked offline against certifi's ISRG Root X1. Chain complete.")

    parts = [b"# Trust file for egazette.gov.in - see certs/README.md for provenance\n"]
    for cert in [*reversed(chain), anchor]:
        parts.append(f"# {cert.subject.rfc4514_string()}\n".encode())
        parts.append(f"#   sha256  {sha256_of(cert)}\n".encode())
        parts.append(f"#   expires {cert.not_valid_after_utc.date().isoformat()}\n".encode())
        parts.append(cert.public_bytes(serialization.Encoding.PEM))
    new_bytes = b"".join(parts)

    if not args.apply:
        unchanged = OUT_PEM.exists() and OUT_PEM.read_bytes() == new_bytes
        print(f"\nDry run. {'The committed file is already correct.' if unchanged else 'The committed file WOULD change.'}")
        print("Re-run with --apply to write it.")
        return 0

    OUT_PEM.parent.mkdir(parents=True, exist_ok=True)
    OUT_PEM.write_bytes(new_bytes)
    print(f"\nWrote {OUT_PEM}")

    resp = requests.get(f"https://{HOST}/", headers={"User-Agent": USER_AGENT},
                        timeout=90, verify=str(OUT_PEM))
    print(f"Live check using only that file: HTTP {resp.status_code}")
    print("\nDone. Commit certs/egazette-chain.pem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
