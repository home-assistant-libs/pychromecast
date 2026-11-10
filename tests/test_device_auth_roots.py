"""Tests for the bundled Cast device authentication roots."""

import hashlib

from cryptography.hazmat.primitives.serialization import Encoding

from pychromecast.device_auth import default_trust_roots


def test_root_fingerprints() -> None:
    """Test the bundled roots are the Cast Root CA and the Eureka Root CA.

    The SHA-256 fingerprints of the DER encodings, as published by Open Screen.
    """
    fingerprints = [
        hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest().upper()
        for cert in default_trust_roots()
    ]
    assert fingerprints == [
        "809AF14700B3FE2611AD597EB1584D6354313B64CCDB3390F097FA3E5826D6CA",
        "CAF6D1E37B532203E01A76BF07187BB731CCD38801565AB2211A2C0AB7F3BC46",
    ]
