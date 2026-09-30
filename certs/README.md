# `certs/` — the certificate file for egazette.gov.in

## In one paragraph

When a program fetches a page over `https://`, it checks a chain of digital
certificates to be sure it is really talking to that website and not to
somebody in the middle pretending to be it. For `egazette.gov.in` that check
used to be **switched off** in this project, which the 30 September 2026 audit
flagged as its finding **C-4**. It is now switched on, and this folder holds
the one extra file the check needs.

## What was actually wrong (this is not what the audit assumed)

The README, the code comments and the audit all said the same thing: that
e-Gazette's certificate chains up to a root certificate authority that Windows
trusts but that Python's bundled list (`certifi`) does not.

Measured on **30 September 2026, that is not the fault.** e-Gazette now uses a
certificate from **Let's Encrypt**, whose roots are trusted everywhere. The real
problem is that **the e-Gazette server does not send its intermediate
certificate**. A certificate chain has three links — the website's own
certificate, an "intermediate" that signed it, and a "root" that signed the
intermediate — and the server is only sending the first. Windows papers over
this by quietly going and fetching the missing middle link itself. Python's TLS
library does not, so it reports:

```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

Evidence, from one TLS handshake on 30 September 2026:

| Link | Subject | Issued by | Expires | SHA-256 |
|---|---|---|---|---|
| website | `CN=egazette.gov.in` | `CN=YR2, O=Let's Encrypt` | 2026-10-19 | `369357fe8bff45f64b5ea0c51ee0726d94934d9d21a29b9c9964fbe4fd338ea8` |
| intermediate (**not sent by the server**) | `CN=YR2, O=Let's Encrypt` | `CN=Root YR, O=ISRG` | 2028-09-02 | `238b85a0099c65b970477d5724f1a1d475ce5058cffe4efa8733899bdb863c47` |
| root, cross-signed (**not sent by the server**) | `CN=Root YR, O=ISRG` | `CN=ISRG Root X1` | 2032-09-02 | `072639d0b140d5bffae16ad9c3f6cc6086040621f51ee61a6d46a8915c07cf76` |
| trust anchor (already trusted) | `CN=ISRG Root X1` | itself | 2035-06-04 | `96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6` |

The server presents exactly **one** certificate (the first row). That was
confirmed by reading the handshake directly.

## What `egazette-chain.pem` contains, and why you can trust it

The three certificates in the bottom three rows of that table: the missing
intermediate, the cross-signed root, and `ISRG Root X1` itself.

- `ISRG Root X1` was taken from **`certifi`** (version 2026.07.22), which is
  already the list of trusted authorities this whole project relies on. Nothing
  new is being trusted.
- The other two were downloaded from the addresses printed inside the
  certificates themselves (`http://yr2.i.lencr.org/` and `http://yr.i.lencr.org/`,
  both Let's Encrypt's own hosts).
- **Those downloads are over plain `http://`, and that is fine** — before the
  file was written, each certificate's cryptographic signature was checked
  offline against `ISRG Root X1`: `Root YR` is signed by `ISRG Root X1`, and
  `YR2` is signed by `Root YR`. A tampered certificate would fail that check.
  So this is not "trust whatever the network handed us"; the trust still comes
  from `certifi`.
- Final proof: fetching `https://egazette.gov.in/` with **only this file** as
  the trust list returns HTTP 200.

## Runbook — what to do if you see a certificate error

> **If a run reports `certificate verify failed` for `egazette.gov.in`, the
> pinned chain in `certs/egazette-chain.pem` is out of date. Rebuild it (see
> below) and commit the new file.**

This will happen sooner or later, because Let's Encrypt issues from several
intermediates and rotates them. It is the safe direction to fail: document
discovery only ever sends you an alert to look at, and the failure is reported
in the daily email rather than swallowed.

To rebuild:

1. Run `python scripts/refresh_egazette_chain.py`. It re-reads the certificate
   the site is presenting today, follows the addresses inside it to fetch the
   missing links, re-checks every signature against `certifi`'s `ISRG Root X1`,
   and rewrites `certs/egazette-chain.pem` — printing every fingerprint so you
   can see what changed.
2. Run `python -m pytest tests/test_egazette_chain.py`.
3. Commit the new `certs/egazette-chain.pem`.

## What is still NOT verified, and why

The document-discovery step that reads e-Gazette's "Search by Ministry" form
uses a headless Chrome browser, and that browser still runs with certificate
checking off (`ignore_https_errors=True` in `src/discover_documents.py`).

- It reads a **list of document titles and Gazette ID numbers**. It can cause
  an alert email; it can never change a word of stored legal text.
- Giving headless Chrome an extra certificate requires building an NSS
  certificate database on the GitHub Actions runner — a lot of moving parts for
  an alert-only read.

**Open item:** teach the Playwright step to use `certs/egazette-chain.pem` too,
or drop the browser step in favour of a plain verified HTTP request if e-Gazette
ever exposes one.
