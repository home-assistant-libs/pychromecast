"""Helpers for the Cast device authentication tests: a test PKI and fake servers."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import socket
import ssl
import threading
import time
from struct import pack
from typing import Any
from uuid import UUID

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from pychromecast.device_auth import NS_DEVICE_AUTH
from pychromecast.generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    SHA256,
    RSASSA_PKCS1v15,
    AuthError,
    AuthResponse,
    CastMessage,
    DeviceAuthMessage,
)

TEST_UUID = UUID("42feced1-d942-3823-2fba-92623e2682f3")
OTHER_UUID = UUID("8bbb9a81-2b17-907d-afb2-8e74dc4b4428")

# The certificates are valid around the time the tests start, so tests going
# through the system clock see them as valid too
NOW = datetime.now(UTC).replace(microsecond=0)
NOT_BEFORE = NOW - timedelta(days=365)
NOT_AFTER = NOW + timedelta(days=3650)

SHA256_WITH_RSA_ALGID = bytes.fromhex("300d06092a864886f70d01010b0500")
SHA1_WITH_RSA_ALGID = bytes.fromhex("300d06092a864886f70d0101050500")


def rsa_key(key_size: int = 2048) -> rsa.RSAPrivateKey:
    """Return a new RSA key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=key_size)


def key_usage(
    *,
    digital_signature: bool = False,
    key_cert_sign: bool = False,
    crl_sign: bool = False,
) -> x509.KeyUsage:
    """Return a key usage extension."""
    return x509.KeyUsage(
        digital_signature=digital_signature,
        content_commitment=False,
        key_encipherment=False,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=key_cert_sign,
        crl_sign=crl_sign,
        encipher_only=False,
        decipher_only=False,
    )


CA_KEY_USAGE = key_usage(key_cert_sign=True, crl_sign=True)
LEAF_KEY_USAGE = key_usage(digital_signature=True)


def make_cert(
    subject_cn: str,
    issuer_cert: x509.Certificate | None,
    issuer_key: rsa.RSAPrivateKey,
    public_key: rsa.RSAPublicKey | ec.EllipticCurvePublicKey,
    *,
    ca: bool | None,
    path_length: int | None = None,
    ku: x509.KeyUsage | None = None,
    not_before: datetime = NOT_BEFORE,
    not_after: datetime = NOT_AFTER,
    client_auth: bool = False,
) -> x509.Certificate:
    """Return a certificate, self-signed if issuer_cert is None.

    ca None means no basic constraints extension.
    """
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test"),
            x509.NameAttribute(NameOID.COMMON_NAME, subject_cn),
        ]
    )
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject if issuer_cert is None else issuer_cert.subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )
    if ca is not None:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=ca, path_length=path_length), critical=True
        )
    if ku is not None:
        builder = builder.add_extension(ku, critical=True)
    if client_auth:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
    return builder.sign(issuer_key, hashes.SHA256())


def _der_len(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def _der_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(value)) + value


def resign_sha1(
    cert: x509.Certificate, issuer_key: rsa.RSAPrivateKey
) -> x509.Certificate:
    """Return the certificate signed with SHA-1 instead of SHA-256.

    cryptography refuses to create SHA-1 signed certificates, so the
    algorithm identifier in the TBS certificate is replaced and the result is
    signed and assembled by hand.
    """
    tbs = cert.tbs_certificate_bytes
    assert tbs.count(SHA256_WITH_RSA_ALGID) == 1
    tbs = tbs.replace(SHA256_WITH_RSA_ALGID, SHA1_WITH_RSA_ALGID)
    signature = issuer_key.sign(tbs, padding.PKCS1v15(), hashes.SHA1())
    encoded = _der_tlv(
        0x30, tbs + SHA1_WITH_RSA_ALGID + _der_tlv(0x03, b"\x00" + signature)
    )
    result = x509.load_der_x509_certificate(encoded)
    assert result.signature_hash_algorithm is not None
    assert result.signature_hash_algorithm.name == "sha1"
    return result


def make_tls_cert(
    cn: str,
    key: rsa.RSAPrivateKey,
    *,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> x509.Certificate:
    """Return a self-signed TLS certificate, like the ones of cast devices."""
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(
            NOW - timedelta(hours=1) if not_before is None else not_before
        )
        .not_valid_after(NOW + timedelta(days=2) if not_after is None else not_after)
        .sign(key, hashes.SHA256())
    )


@dataclass
class TestPKI:
    """A test PKI, shaped like the Cast PKI."""

    root_key: rsa.RSAPrivateKey
    root: x509.Certificate
    other_root_key: rsa.RSAPrivateKey
    other_root: x509.Certificate
    # Intermediate issued by the root, issues the leaf
    ica_key: rsa.RSAPrivateKey
    ica: x509.Certificate
    # Manufacturer and product intermediates, like the WiiM chain
    mfr_key: rsa.RSAPrivateKey
    mfr: x509.Certificate
    product_key: rsa.RSAPrivateKey
    product: x509.Certificate
    # Device certificate issued by ica
    leaf_key: rsa.RSAPrivateKey
    leaf: x509.Certificate
    # Device certificate issued by product
    product_leaf: x509.Certificate
    # Key of the TLS certificates
    tls_key: rsa.RSAPrivateKey
    tls_cert: x509.Certificate

    __test__ = False

    @property
    def tls_der(self) -> bytes:
        """Return the DER of the TLS certificate."""
        return der(self.tls_cert)

    def make_leaf(self, **kwargs: object) -> x509.Certificate:
        """Return a device certificate issued by ica."""
        options: dict = {
            "ca": False,
            "ku": LEAF_KEY_USAGE,
            "client_auth": True,
            "public_key": self.leaf_key.public_key(),
        }
        options.update(kwargs)
        return make_cert("TEST FA8FCA000000", self.ica, self.ica_key, **options)


def der(cert: x509.Certificate) -> bytes:
    """Return the DER encoding of a certificate."""
    return cert.public_bytes(Encoding.DER)


def make_pki() -> TestPKI:
    """Return a new test PKI."""
    root_key = rsa_key()
    root = make_cert(
        "Test Root CA",
        None,
        root_key,
        root_key.public_key(),
        ca=True,
        path_length=2,
        ku=CA_KEY_USAGE,
    )
    other_root_key = rsa_key()
    other_root = make_cert(
        "Test Root CA",
        None,
        other_root_key,
        other_root_key.public_key(),
        ca=True,
        path_length=2,
        ku=CA_KEY_USAGE,
    )
    ica_key = rsa_key()
    ica = make_cert(
        "Test ICA",
        root,
        root_key,
        ica_key.public_key(),
        ca=True,
        path_length=0,
        ku=key_usage(key_cert_sign=True),
    )
    mfr_key = rsa_key()
    mfr = make_cert(
        "Test Manufacturer Cert",
        root,
        root_key,
        mfr_key.public_key(),
        ca=True,
        path_length=1,
        ku=key_usage(key_cert_sign=True),
    )
    product_key = rsa_key()
    product = make_cert(
        "Test Product",
        mfr,
        mfr_key,
        product_key.public_key(),
        ca=True,
        path_length=0,
        ku=key_usage(key_cert_sign=True),
    )
    leaf_key = rsa_key()
    leaf = make_cert(
        "TEST FA8FCA000000",
        ica,
        ica_key,
        leaf_key.public_key(),
        ca=False,
        ku=LEAF_KEY_USAGE,
        client_auth=True,
    )
    product_leaf = make_cert(
        "TEST FA8FCA000001",
        product,
        product_key,
        leaf_key.public_key(),
        ca=False,
        ku=LEAF_KEY_USAGE,
        client_auth=True,
    )
    tls_key = rsa_key()
    tls_cert = make_tls_cert(str(TEST_UUID), tls_key)
    return TestPKI(
        root_key=root_key,
        root=root,
        other_root_key=other_root_key,
        other_root=other_root,
        ica_key=ica_key,
        ica=ica,
        mfr_key=mfr_key,
        mfr=mfr,
        product_key=product_key,
        product=product,
        leaf_key=leaf_key,
        leaf=leaf,
        product_leaf=product_leaf,
        tls_key=tls_key,
        tls_cert=tls_cert,
    )


def make_reply(
    *,
    nonce: bytes,
    peer_cert_der: bytes,
    leaf: x509.Certificate | bytes,
    leaf_key: rsa.RSAPrivateKey,
    intermediates: tuple[x509.Certificate | bytes, ...] = (),
    echo: bool = True,
    echoed_nonce: bytes | None = None,
    hash_alg: int | None = SHA256,
    sign_over: bytes | None = None,
    error: int | None = None,
    namespace: str = NS_DEVICE_AUTH,
    sig_alg: int = RSASSA_PKCS1v15,
) -> CastMessage:
    """Return a reply to a challenge, by default a valid one.

    hash_alg None leaves the hash algorithm field out.
    """
    if error is not None:
        auth_message = DeviceAuthMessage(error=AuthError(error_type=error))  # type: ignore[arg-type]
    else:
        echoed = nonce if echoed_nonce is None else echoed_nonce
        # An absent hash algorithm means SHA-1, the proto default
        hash_factory = hashes.SHA256 if hash_alg == SHA256 else hashes.SHA1
        if sign_over is None:
            sign_over = (echoed if echo else b"") + peer_cert_der
        signature = leaf_key.sign(sign_over, padding.PKCS1v15(), hash_factory())
        response = AuthResponse(
            signature=signature,
            client_auth_certificate=leaf if isinstance(leaf, bytes) else der(leaf),
            intermediate_certificate=[
                cert if isinstance(cert, bytes) else der(cert) for cert in intermediates
            ],
            signature_algorithm=sig_alg,  # type: ignore[arg-type]
        )
        if echo:
            response.sender_nonce = echoed
        if hash_alg is not None:
            response.hash_algorithm = hash_alg  # type: ignore[assignment]
        auth_message = DeviceAuthMessage(response=response)
    return CastMessage(
        protocol_version=CastMessage.CASTV2_1_0,
        source_id="receiver-0",
        destination_id="sender-0",
        namespace=namespace,
        payload_type=CastMessage.BINARY,
        payload_binary=auth_message.SerializeToString(),
    )


def _write_pem(
    tmp_path: Path, name: str, cert: x509.Certificate, key: rsa.RSAPrivateKey
) -> tuple[Path, Path]:
    cert_path = tmp_path / f"{name}.crt"
    key_path = tmp_path / f"{name}.key"
    cert_path.write_bytes(cert.public_bytes(Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    return cert_path, key_path


class TLSServer:
    """A TLS server on localhost, handling each connection in a thread."""

    def __init__(
        self, tmp_path: Path, name: str, cert: x509.Certificate, key: rsa.RSAPrivateKey
    ) -> None:
        cert_path, key_path = _write_pem(tmp_path, name, cert, key)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(cert_path, key_path)
        self.stop = threading.Event()
        self.server = socket.create_server(("127.0.0.1", 0))
        self.server.settimeout(0.05)
        self.port = self.server.getsockname()[1]
        self.handlers: list[threading.Thread] = []
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()

    def _accept(self) -> None:
        while not self.stop.is_set():
            try:
                conn, _ = self.server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            handler = threading.Thread(target=self._serve, args=(conn,), daemon=True)
            self.handlers.append(handler)
            handler.start()

    def _serve(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(2)
            tls = self.context.wrap_socket(conn, server_side=True)
        except OSError:
            conn.close()
            return
        try:
            tls.settimeout(0.05)
            self.handle(tls)
        except OSError:
            pass
        finally:
            tls.close()

    def handle(self, tls: ssl.SSLSocket) -> None:
        """Handle a connection."""
        raise NotImplementedError

    def wait_idle(self, timeout: float = 5) -> None:
        """Wait for all connections to be closed."""
        deadline = time.monotonic() + timeout
        for handler in list(self.handlers):
            handler.join(max(deadline - time.monotonic(), 0))
            assert not handler.is_alive()

    def close(self) -> None:
        """Stop the server."""
        self.stop.set()
        self.server.close()
        self._thread.join(2)
        for handler in self.handlers:
            handler.join(2)


def eureka_info(
    groups: list[dict[str, Any]] | None = None,
    dynamic_groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return eureka_info with multizone information."""
    return {
        "name": "Living room",
        "multizone": {
            "groups": groups or [],
            "dynamic_groups": dynamic_groups or [],
        },
    }


class EurekaServer(TLSServer):
    """A fake HTTPS eureka_info endpoint of a cast device.

    Like the devices, it keeps the connection open after responding.
    """

    def __init__(
        self,
        tmp_path: Path,
        cert: x509.Certificate,
        key: rsa.RSAPrivateKey,
        *,
        body: Any = None,
        status: int = 200,
        mode: str = "respond",
    ) -> None:
        self.body = eureka_info() if body is None else body
        self.status = status
        self.mode = mode
        # The request lines received
        self.requests: list[bytes] = []
        super().__init__(tmp_path, "eureka", cert, key)

    def _recv(self, tls: ssl.SSLSocket) -> bytes | None:
        """Receive data, None when the connection is closed or stopping."""
        while not self.stop.is_set():
            try:
                return tls.recv(65536)
            except TimeoutError:
                continue
        return None

    def handle(self, tls: ssl.SSLSocket) -> None:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self._recv(tls)
            if not chunk:
                return
            data += chunk
        self.requests.append(data.split(b"\r\n", 1)[0])
        if self.mode == "close":
            return
        if self.mode in ("respond", "slow"):
            if isinstance(self.body, bytes):
                body = self.body
            else:
                body = json.dumps(self.body).encode()
            head = (
                f"HTTP/1.1 {self.status} Status\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            if self.mode == "slow":
                # Each part arrives in time on its own, not both together
                time.sleep(0.4)
                tls.sendall(head)
                time.sleep(0.4)
                tls.sendall(body)
            else:
                tls.sendall(head + body)
        # Keep the connection open until the client closes it
        while self._recv(tls):
            pass


def frame(message: CastMessage) -> bytes:
    """Return a message framed like on the wire."""
    payload = message.SerializeToString()
    return pack(">I", len(payload)) + payload


def group_entry(port: int | None, **kwargs: Any) -> dict[str, Any]:
    """Return an eureka_info group entry for TEST_UUID led by the device.

    Keys set to None are left out.
    """
    entry: dict[str, Any] = {
        "uuid": str(TEST_UUID),
        "name": "Ground floor",
        "elected_leader": "self",
        "leader": "",
        "cast_port": port,
    }
    entry.update(kwargs)
    return {key: value for key, value in entry.items() if value is not None}


@contextmanager
def refused_port() -> Generator[int]:
    """Return a port on localhost which refuses connections.

    The port is bound but not listening, so it can't be reused meanwhile.
    """
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        yield sock.getsockname()[1]
    finally:
        sock.close()


# A real device certificate chain, for tests against the bundled roots. It is
# public: the device certificate, CN=WDFT3 FA8FCA895D59 (SHA-1 signed, valid
# 2013-10-15 to 2033-10-10), leaked with the shanocast unofficial receiver,
# whose source publishes it. It is issued by "Eureka Gen1 ICA" (SHA-1 signed,
# valid 2012-12-19 to 2032-12-14), which chains up to the Eureka Root CA.
SHANOCAST_DEVICE_CERT_PEM = """\
-----BEGIN CERTIFICATE-----
MIIDqzCCApOgAwIBAgIEUl20yDANBgkqhkiG9w0BAQUFADB9MQswCQYDVQQGEwJV
UzETMBEGA1UECAwKQ2FsaWZvcm5pYTEWMBQGA1UEBwwNTW91bnRhaW4gVmlldzET
MBEGA1UECgwKR29vZ2xlIEluYzESMBAGA1UECwwJR29vZ2xlIFRWMRgwFgYDVQQD
DA9FdXJla2EgR2VuMSBJQ0EwHhcNMTMxMDE1MjEzNDAwWhcNMzMxMDEwMjEzNDAw
WjCBgDETMBEGA1UEChMKR29vZ2xlIEluYzETMBEGA1UECBMKQ2FsaWZvcm5pYTEL
MAkGA1UEBhMCVVMxFjAUBgNVBAcTDU1vdW50YWluIFZpZXcxEjAQBgNVBAsTCUdv
b2dsZSBUVjEbMBkGA1UEAxMSV0RGVDMgRkE4RkNBODk1RDU5MIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAyuJeiL3ku+mTK2EwOdbqf0APEeqqa0HOTA0V
CXQXGOJdEXboCnNkSb46A0Cn1OO7/2R7Ex0OlhSoYv/2xKgbOpLSp3gqXl1aRNMN
D1i+YVdDzdS6F9IWvx1iTYSuPsxUSH5ECzEl5lvDSWXPIn54AmkVG04xuVETfLLQ
y8dbZsjh89ODPTDRLDODf78lfKagvHmFnWPXBdPPoUYokmLH3Iuxp7zl9G7oxL/+
P6VPkgylAzGqnSvmtMdDs6Lz/GZ2KX5WMKB8n+c2g1UMjPgaiut67wf/V6ltvQXN
95uue9JiHBECgZWbYTadI9aIpdbExwbCdpeRFs8vsx5ITmFlLwIDAQABoy8wLTAJ
BgNVHRMEAjAAMAsGA1UdDwQEAwIHgDATBgNVHSUEDDAKBggrBgEFBQcDAjANBgkq
hkiG9w0BAQUFAAOCAQEAc/T1hQ01kjkETg2lLXPIcYG3nP5RXIyDwnXlNWsHVzZl
z/Vvqq/rLmQwJjdQjVWjP+mZlw6Y3O8q0cVKUEWVtk4GGk6WHfCM+s/jeznaeEGg
3LI2TuUCyD2RkbaQozSQGjvU1NXyI/fYNBociBfkf594pnRS/sXOUisuo8IyuwN/
o3CeiX+FAkizYiXhrUYCvPQpFtOgHQbSuNeDE2R/HKyOKkW/DlDRWO9tQa+O9SLi
/UqCsaAxOqlOg32PW1rt1fR5CgTT5A3kfExXoA4n0LJ+CEH8UenddEuh5KZ+xuUP
WkxPQTOEAE0MscxdtvrtOxb9ZpTfUahdnTeu2E4PkQ==
-----END CERTIFICATE-----
"""
SHANOCAST_ICA_PEM = """\
-----BEGIN CERTIFICATE-----
MIIDhzCCAm+gAwIBAgIBATANBgkqhkiG9w0BAQUFADB8MQswCQYDVQQGEwJVUzET
MBEGA1UECAwKQ2FsaWZvcm5pYTEWMBQGA1UEBwwNTW91bnRhaW4gVmlldzETMBEG
A1UECgwKR29vZ2xlIEluYzESMBAGA1UECwwJR29vZ2xlIFRWMRcwFQYDVQQDDA5F
dXJla2EgUm9vdCBDQTAeFw0xMjEyMTkwMDQ3MTJaFw0zMjEyMTQwMDQ3MTJaMH0x
CzAJBgNVBAYTAlVTMRMwEQYDVQQIDApDYWxpZm9ybmlhMRYwFAYDVQQHDA1Nb3Vu
dGFpbiBWaWV3MRMwEQYDVQQKDApHb29nbGUgSW5jMRIwEAYDVQQLDAlHb29nbGUg
VFYxGDAWBgNVBAMMD0V1cmVrYSBHZW4xIElDQTCCASIwDQYJKoZIhvcNAQEBBQAD
ggEPADCCAQoCggEBALwigL2A9johADuudl41fz3DZFxVlIY0LwWHKM33aYwXs1Cn
uIL638dDLdZ+q6BvtxNygKRHFcEgmVDN7BRiCVukmM3SQbY2Tv/oLjIwSoGoQqNs
mzNuyrL1U2bgJ1OGGoUepzk/SneO+1RmZvtYVMBeOcf1UAYL4IrUzuFqVR+LFwDm
aaMn5gglaTwSnY0FLNYuojHetFJQ1iBJ3nGg+a0gQBLx3SXr1ea4NvTWj3/KQ9zX
EFvmP1GKhbPz//YDLcsjT5ytGOeTBYysUpr3TOmZer5ufk0K48YcqZP6OqWRXRy9
ZuvMYNyGdMrP+JIcmH1X+mFHnquAt+RIgCqSxRsCAwEAAaMTMBEwDwYDVR0TBAgw
BgEB/wIBATANBgkqhkiG9w0BAQUFAAOCAQEAi9Shsc9dzXtsSEpBH1MvGC0yRf+e
q9NzPh8i1+r6AeZzAw8rxiW7pe7F9UXLJBIqrcJdBfR69cKbEBZa0QpzxRY5oBDK
0WiFnvueJoOOWPN3oE7l25e+LQBf9ZTbsZ1la/3w0QRR38ySppktcfVN1SP+Mxyp
tKvFvxq40YDvicniH5xMSDui+gIK3IQBiocC+1nup0wEfXSZh2olRK0WquxONRt8
e4TJsT/hgnDlDefZbfqVtsXkHugRm9iy86T9E/ODT/cHFCC7IqWmj9a126l0eOKT
DeUjLwUX4LKXZzRND5x2Q3umIUpWBfYqfPJ/EpSCJikH8AtsbHkUsHTVbA==
-----END CERTIFICATE-----
"""
