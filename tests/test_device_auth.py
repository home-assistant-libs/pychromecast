"""Tests for pychromecast.device_auth."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import socket
from struct import pack, unpack
import threading
import time
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
from device_auth_helpers import (
    NOW,
    OTHER_UUID,
    TEST_UUID,
    EurekaServer,
    eureka_info,
    frame,
    group_entry,
    LEAF_KEY_USAGE,
    SHANOCAST_DEVICE_CERT_PEM,
    SHANOCAST_ICA_PEM,
    TestPKI,
    der,
    refused_port,
    key_usage,
    make_cert,
    make_reply,
    make_tls_cert,
    resign_sha1,
    rsa_key,
)
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from pychromecast import device_auth
from pychromecast.device_auth import (
    MAX_EUREKA_INFO_SIZE,
    MAX_SIGNATURE_CHECKS,
    NONCE_LENGTH,
    NS_DEVICE_AUTH,
    DeviceAuthFailureClass,
    DeviceAuthResult,
    DeviceAuthStatus,
    authenticate,
    build_challenge,
    _common_name,
    _find_path,
    default_trust_roots,
    verify_auth_reply,
    verify_group_leader,
    verify_not_group_endpoint,
)
from pychromecast.generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    SHA1,
    SHA256,
    RSASSA_PSS,
    RSASSA_PKCS1v15,
    AuthError,
    CastMessage,
    DeviceAuthMessage,
)

NONCE = bytes(range(16))
_UNSET: Any = object()


def _reply(pki: TestPKI, **kwargs: Any) -> CastMessage:
    """Return a valid reply, modified by kwargs."""
    options: dict[str, Any] = {
        "nonce": NONCE,
        "peer_cert_der": pki.tls_der,
        "leaf": pki.leaf,
        "leaf_key": pki.leaf_key,
        "intermediates": (pki.ica,),
    }
    options.update(kwargs)
    return make_reply(**options)


def _verify(
    pki: TestPKI,
    reply: CastMessage,
    *,
    peer_cert_der: bytes | None = _UNSET,
    expected_uuid: UUID | None = TEST_UUID,
    trust_roots: list | None = _UNSET,
    now: Any = NOW,
) -> DeviceAuthResult:
    return verify_auth_reply(
        reply,
        nonce=NONCE,
        peer_cert_der=pki.tls_der if peer_cert_der is _UNSET else peer_cert_der,
        expected_uuid=expected_uuid,
        trust_roots=[pki.root] if trust_roots is _UNSET else trust_roots,
        now=now,
    )


def _mutate_response(
    reply: CastMessage, mutate: Callable[[DeviceAuthMessage], None]
) -> CastMessage:
    """Return the reply with its device auth message changed."""
    auth_message = DeviceAuthMessage()
    auth_message.ParseFromString(reply.payload_binary)
    mutate(auth_message)
    reply.payload_binary = auth_message.SerializePartialToString()
    return reply


def test_build_challenge() -> None:
    """Test the challenge message."""
    message = build_challenge(NONCE)

    assert message.source_id == "sender-0"
    assert message.destination_id == "receiver-0"
    assert message.namespace == NS_DEVICE_AUTH
    assert message.payload_type == CastMessage.BINARY
    auth_message = DeviceAuthMessage()
    auth_message.ParseFromString(message.payload_binary)
    assert auth_message.HasField("challenge")
    assert auth_message.challenge.sender_nonce == NONCE
    assert auth_message.challenge.hash_algorithm == SHA256
    assert auth_message.challenge.signature_algorithm == RSASSA_PKCS1v15


def test_valid_chain_one_intermediate(pki: TestPKI) -> None:
    """Test a genuine device is verified."""
    result = _verify(pki, _reply(pki))

    assert result.status is DeviceAuthStatus.VERIFIED
    assert result.verified
    assert result.trust_root == "Test Root CA"
    assert result.device_cert_subject == "CN=TEST FA8FCA000000,O=Test"
    assert result.tls_cert_cn == str(TEST_UUID)
    assert result.uuid_checked
    assert result.hash_algorithm == "sha256"


def test_zero_intermediates(pki: TestPKI) -> None:
    """Test a device certificate issued by the root."""
    leaf = make_cert(
        "TEST FA8FCA000000",
        pki.root,
        pki.root_key,
        pki.leaf_key.public_key(),
        ca=False,
        ku=LEAF_KEY_USAGE,
    )
    result = _verify(pki, _reply(pki, leaf=leaf, intermediates=()))
    assert result.status is DeviceAuthStatus.VERIFIED


def test_two_intermediates(pki: TestPKI) -> None:
    """Test a chain with two intermediates, like the WiiM AMP's."""
    reply = _reply(pki, leaf=pki.product_leaf, intermediates=(pki.product, pki.mfr))
    assert _verify(pki, reply).status is DeviceAuthStatus.VERIFIED


def test_two_intermediates_unordered(pki: TestPKI) -> None:
    """Test the intermediates may be sent in any order, among unrelated ones."""
    reply = _reply(
        pki, leaf=pki.product_leaf, intermediates=(pki.ica, pki.mfr, pki.product)
    )
    assert _verify(pki, reply).status is DeviceAuthStatus.VERIFIED


def test_sha1_signed_leaf(pki: TestPKI) -> None:
    """Test a SHA-1 signed device certificate, like the Chromecast Audio's."""
    leaf = resign_sha1(pki.leaf, pki.ica_key)
    assert _verify(pki, _reply(pki, leaf=leaf)).status is DeviceAuthStatus.VERIFIED


def test_sha1_signed_intermediate(pki: TestPKI) -> None:
    """Test a SHA-1 signed intermediate."""
    ica = resign_sha1(pki.ica, pki.root_key)
    result = _verify(pki, _reply(pki, intermediates=(ica,)))
    assert result.status is DeviceAuthStatus.VERIFIED


def test_wrong_root(pki: TestPKI) -> None:
    """Test a chain to another root with the same name is untrusted."""
    result = _verify(pki, _reply(pki), trust_roots=[pki.other_root])
    assert result.status is DeviceAuthStatus.CHAIN_UNTRUSTED


def test_bundled_roots_by_default(pki: TestPKI) -> None:
    """Test the bundled roots are used by default, which don't trust the test PKI."""
    result = _verify(pki, _reply(pki), trust_roots=None)
    assert result.status is DeviceAuthStatus.CHAIN_UNTRUSTED


def test_missing_intermediate(pki: TestPKI) -> None:
    """Test a chain without its intermediate is untrusted."""
    result = _verify(pki, _reply(pki, intermediates=()))
    assert result.status is DeviceAuthStatus.CHAIN_UNTRUSTED


def test_forged_intermediate(pki: TestPKI) -> None:
    """Test an intermediate with the right names but the wrong signature."""
    forged_key = rsa_key()
    forged = make_cert(
        "Test ICA",
        pki.root,
        pki.other_root_key,
        forged_key.public_key(),
        ca=True,
        path_length=0,
        ku=key_usage(key_cert_sign=True),
    )
    leaf = make_cert(
        "TEST FA8FCA000000",
        forged,
        forged_key,
        pki.leaf_key.public_key(),
        ca=False,
        ku=LEAF_KEY_USAGE,
    )
    result = _verify(pki, _reply(pki, leaf=leaf, intermediates=(forged,)))
    assert result.status is DeviceAuthStatus.CHAIN_UNTRUSTED


def _ica(pki: TestPKI, **kwargs: Any) -> Any:
    """Return a variant of the ICA, with the same name and key."""
    options: dict[str, Any] = {
        "ca": True,
        "path_length": 0,
        "ku": key_usage(key_cert_sign=True),
    }
    options.update(kwargs)
    return make_cert(
        "Test ICA", pki.root, pki.root_key, pki.ica_key.public_key(), **options
    )


def test_expired_intermediate(pki: TestPKI) -> None:
    """Test an expired intermediate."""
    ica = _ica(pki, not_after=NOW - timedelta(days=1))
    result = _verify(pki, _reply(pki, intermediates=(ica,)))
    assert result.status is DeviceAuthStatus.CERT_EXPIRED
    assert "CN=Test ICA" in result.detail
    assert "expired at" in result.detail
    assert (NOW - timedelta(days=1)).date().isoformat() in result.detail


def test_not_yet_valid_intermediate(pki: TestPKI) -> None:
    """Test an intermediate which is not valid yet."""
    ica = _ica(pki, not_before=NOW + timedelta(days=1))
    result = _verify(pki, _reply(pki, intermediates=(ica,)))
    assert result.status is DeviceAuthStatus.CERT_EXPIRED


def test_expired_leaf(pki: TestPKI) -> None:
    """Test an expired device certificate."""
    leaf = pki.make_leaf(not_after=NOW - timedelta(seconds=1))
    result = _verify(pki, _reply(pki, leaf=leaf))
    assert result.status is DeviceAuthStatus.CERT_EXPIRED
    assert "device certificate" in result.detail


def test_not_yet_valid_leaf(pki: TestPKI) -> None:
    """Test a device certificate which is not valid yet."""
    leaf = pki.make_leaf(not_before=NOW + timedelta(seconds=1))
    result = _verify(pki, _reply(pki, leaf=leaf))
    assert result.status is DeviceAuthStatus.CERT_EXPIRED


@pytest.mark.parametrize("ca", [False, None])
def test_intermediate_not_ca(pki: TestPKI, ca: bool | None) -> None:
    """Test an intermediate which is not a CA."""
    ica = _ica(pki, ca=ca, path_length=None)
    result = _verify(pki, _reply(pki, intermediates=(ica,)))
    assert result.status is DeviceAuthStatus.CERT_INVALID


def test_intermediate_ku_without_cert_sign(pki: TestPKI) -> None:
    """Test an intermediate not allowed to sign certificates."""
    ica = _ica(pki, ku=key_usage(digital_signature=True))
    result = _verify(pki, _reply(pki, intermediates=(ica,)))
    assert result.status is DeviceAuthStatus.CERT_INVALID


def test_intermediate_without_ku(pki: TestPKI) -> None:
    """Test an intermediate without a key usage extension is accepted."""
    ica = _ica(pki, ku=None)
    result = _verify(pki, _reply(pki, intermediates=(ica,)))
    assert result.status is DeviceAuthStatus.VERIFIED


def test_pathlen_violation(pki: TestPKI) -> None:
    """Test an intermediate with path length 0 above another intermediate."""
    ica2_key = rsa_key()
    ica2 = make_cert(
        "Test ICA 2",
        pki.ica,
        pki.ica_key,
        ica2_key.public_key(),
        ca=True,
        ku=key_usage(key_cert_sign=True),
    )
    leaf = make_cert(
        "TEST FA8FCA000000",
        ica2,
        ica2_key,
        pki.leaf_key.public_key(),
        ca=False,
        ku=LEAF_KEY_USAGE,
    )
    result = _verify(pki, _reply(pki, leaf=leaf, intermediates=(ica2, pki.ica)))
    assert result.status is DeviceAuthStatus.CERT_INVALID
    assert "path length" in result.detail


@pytest.mark.parametrize("ku", [key_usage(key_cert_sign=True), None])
def test_leaf_without_digital_signature(pki: TestPKI, ku: Any) -> None:
    """Test a device certificate not allowed to sign."""
    leaf = pki.make_leaf(ku=ku)
    result = _verify(pki, _reply(pki, leaf=leaf))
    assert result.status is DeviceAuthStatus.CERT_INVALID


def test_small_rsa_key(pki: TestPKI) -> None:
    """Test a device certificate with a 1024 bit key."""
    key = rsa_key(1024)
    leaf = pki.make_leaf(public_key=key.public_key())
    result = _verify(pki, _reply(pki, leaf=leaf, leaf_key=key))
    assert result.status is DeviceAuthStatus.CERT_INVALID
    assert "1024" in result.detail


def test_non_rsa_leaf(pki: TestPKI) -> None:
    """Test a device certificate with an EC key."""
    key = ec.generate_private_key(ec.SECP256R1())
    leaf = pki.make_leaf(public_key=key.public_key())
    result = _verify(pki, _reply(pki, leaf=leaf))
    assert result.status is DeviceAuthStatus.CERT_INVALID


def test_unparsable_leaf(pki: TestPKI) -> None:
    """Test a device certificate which can't be parsed."""
    result = _verify(pki, _reply(pki, leaf=b"not a certificate"))
    assert result.status is DeviceAuthStatus.CERT_INVALID


def test_unparsable_intermediate(pki: TestPKI) -> None:
    """Test an intermediate which can't be parsed."""
    result = _verify(pki, _reply(pki, intermediates=(b"garbage", pki.ica)))
    assert result.status is DeviceAuthStatus.CERT_INVALID


def test_expired_root_still_accepted(pki: TestPKI) -> None:
    """Test the validity of the root is not checked."""
    root = make_cert(
        "Test Root CA",
        None,
        pki.root_key,
        pki.root_key.public_key(),
        ca=True,
        path_length=2,
        not_before=NOW - timedelta(days=7300),
        not_after=NOW - timedelta(days=1),
    )
    result = _verify(pki, _reply(pki), trust_roots=[root])
    assert result.status is DeviceAuthStatus.VERIFIED


def test_bad_signature(pki: TestPKI) -> None:
    """Test a reply whose signature has a flipped bit."""

    def flip(auth_message: DeviceAuthMessage) -> None:
        signature = bytearray(auth_message.response.signature)
        signature[-1] ^= 1
        auth_message.response.signature = bytes(signature)

    result = _verify(pki, _mutate_response(_reply(pki), flip))
    assert result.status is DeviceAuthStatus.SIGNATURE_INVALID


def test_signature_over_other_tls_cert(pki: TestPKI) -> None:
    """Test a relay, the signature is over the genuine device's TLS certificate."""
    relay_cert = make_tls_cert(str(TEST_UUID), rsa_key())
    # The genuine device signs its own TLS certificate
    reply = _reply(pki, peer_cert_der=pki.tls_der)
    # The sender sees the relay's TLS certificate
    result = _verify(pki, reply, peer_cert_der=der(relay_cert))
    assert result.status is DeviceAuthStatus.SIGNATURE_INVALID


def test_signature_wrong_order(pki: TestPKI) -> None:
    """Test a signature over the TLS certificate followed by the nonce."""
    result = _verify(pki, _reply(pki, sign_over=pki.tls_der + NONCE))
    assert result.status is DeviceAuthStatus.SIGNATURE_INVALID


def test_missing_nonce_echo_shanocast(pki: TestPKI) -> None:
    """Test a reply without the nonce, like the replayed shanocast reply."""
    result = _verify(pki, _reply(pki, echo=False))
    assert result.status is DeviceAuthStatus.NONCE_MISSING


def test_wrong_nonce(pki: TestPKI) -> None:
    """Test a validly signed reply for another nonce."""
    result = _verify(pki, _reply(pki, echoed_nonce=b"\x01" * NONCE_LENGTH))
    assert result.status is DeviceAuthStatus.NONCE_MISMATCH


def _tls_reply(pki: TestPKI, tls_der: bytes) -> DeviceAuthResult:
    """Verify a valid reply for another TLS certificate."""
    return _verify(pki, _reply(pki, peer_cert_der=tls_der), peer_cert_der=tls_der)


def test_tls_cert_expired(pki: TestPKI) -> None:
    """Test an expired TLS certificate."""
    cert = make_tls_cert(
        str(TEST_UUID),
        pki.tls_key,
        not_before=NOW - timedelta(days=2),
        not_after=NOW - timedelta(seconds=1),
    )
    result = _tls_reply(pki, der(cert))
    assert result.status is DeviceAuthStatus.TLS_CERT_INVALID
    assert "system clock" in result.detail


def test_tls_cert_not_yet_valid(pki: TestPKI) -> None:
    """Test a TLS certificate which is not valid yet."""
    cert = make_tls_cert(
        str(TEST_UUID), pki.tls_key, not_before=NOW + timedelta(seconds=1)
    )
    result = _tls_reply(pki, der(cert))
    assert result.status is DeviceAuthStatus.TLS_CERT_INVALID


def test_tls_cert_remaining_validity_too_long(pki: TestPKI) -> None:
    """Test a TLS certificate valid for more than four more days."""
    cert = make_tls_cert(
        str(TEST_UUID),
        pki.tls_key,
        not_after=NOW + timedelta(days=4, minutes=1),
    )
    result = _tls_reply(pki, der(cert))
    assert result.status is DeviceAuthStatus.TLS_CERT_INVALID


def test_tls_cert_remaining_validity_boundary(pki: TestPKI) -> None:
    """Test a TLS certificate valid for exactly four more days."""
    cert = make_tls_cert(str(TEST_UUID), pki.tls_key, not_after=NOW + timedelta(days=4))
    result = _tls_reply(pki, der(cert))
    assert result.status is DeviceAuthStatus.VERIFIED


def test_unparsable_tls_cert(pki: TestPKI) -> None:
    """Test a TLS certificate which can't be parsed."""
    result = _tls_reply(pki, b"not a certificate")
    assert result.status is DeviceAuthStatus.TLS_CERT_MALFORMED
    assert result.failure_class is DeviceAuthFailureClass.NOT_GENUINE


def test_no_peer_cert(pki: TestPKI) -> None:
    """Test a device without a TLS certificate."""
    result = _verify(pki, _reply(pki), peer_cert_der=None)
    assert result.status is DeviceAuthStatus.TLS_CERT_MALFORMED


def test_auth_error_reply(pki: TestPKI) -> None:
    """Test a device replying with an error."""
    reply = _reply(pki, error=AuthError.SIGNATURE_ALGORITHM_UNAVAILABLE)
    result = _verify(pki, reply)
    assert result.status is DeviceAuthStatus.AUTH_ERROR_REPLY
    assert "SIGNATURE_ALGORITHM_UNAVAILABLE" in result.detail


def test_reply_without_response_or_error(pki: TestPKI) -> None:
    """Test a reply with neither a response nor an error."""
    reply = _reply(pki)
    reply.payload_binary = DeviceAuthMessage().SerializeToString()
    assert _verify(pki, reply).status is DeviceAuthStatus.MALFORMED_REPLY


def test_response_missing_required_fields(pki: TestPKI) -> None:
    """Test a response without the required signature."""

    def clear(auth_message: DeviceAuthMessage) -> None:
        auth_message.response.ClearField("signature")

    result = _verify(pki, _mutate_response(_reply(pki), clear))
    assert result.status is DeviceAuthStatus.MALFORMED_REPLY


def test_garbage_payload(pki: TestPKI) -> None:
    """Test a reply whose payload can't be parsed."""
    reply = _reply(pki)
    reply.payload_binary = b"\x0a\xff\xff"
    assert _verify(pki, reply).status is DeviceAuthStatus.MALFORMED_REPLY


def test_string_payload(pki: TestPKI) -> None:
    """Test a reply with a string payload."""
    reply = _reply(pki)
    reply.payload_type = CastMessage.STRING
    reply.payload_utf8 = "{}"
    assert _verify(pki, reply).status is DeviceAuthStatus.MALFORMED_REPLY


def test_wrong_namespace(pki: TestPKI) -> None:
    """Test a message on another namespace."""
    reply = _reply(pki, namespace="urn:x-cast:com.google.cast.receiver")
    assert _verify(pki, reply).status is DeviceAuthStatus.UNEXPECTED_MESSAGE


def test_pss_rejected(pki: TestPKI) -> None:
    """Test a reply claiming an RSASSA-PSS signature."""
    result = _verify(pki, _reply(pki, sig_alg=RSASSA_PSS))
    assert result.status is DeviceAuthStatus.UNSUPPORTED_ALGORITHM


def test_sha1_response_hash(pki: TestPKI) -> None:
    """Test a reply signed with SHA-1 is accepted."""
    result = _verify(pki, _reply(pki, hash_alg=SHA1))
    assert result.status is DeviceAuthStatus.VERIFIED
    assert result.hash_algorithm == "sha1"


def test_hash_field_absent_defaults_sha1(pki: TestPKI) -> None:
    """Test a reply without a hash algorithm is verified as SHA-1."""
    result = _verify(pki, _reply(pki, hash_alg=None))
    assert result.status is DeviceAuthStatus.VERIFIED
    assert result.hash_algorithm == "sha1"


def test_hash_mismatch(pki: TestPKI) -> None:
    """Test a reply signed with SHA-1 but claiming SHA-256."""

    def claim_sha256(auth_message: DeviceAuthMessage) -> None:
        auth_message.response.hash_algorithm = SHA256

    reply = _mutate_response(_reply(pki, hash_alg=SHA1), claim_sha256)
    assert _verify(pki, reply).status is DeviceAuthStatus.SIGNATURE_INVALID


def test_uuid_mismatch(pki: TestPKI) -> None:
    """Test a genuine device whose TLS certificate is for another UUID."""
    cert = make_tls_cert(str(OTHER_UUID), pki.tls_key)
    result = _tls_reply(pki, der(cert))
    assert result.status is DeviceAuthStatus.UUID_MISMATCH
    assert str(OTHER_UUID) in result.detail
    assert str(TEST_UUID) in result.detail
    assert result.tls_cert_cn == str(OTHER_UUID)
    assert result.trust_root == "Test Root CA"
    assert not result.uuid_checked
    assert not result.verified


def test_uuid_checked_last(pki: TestPKI) -> None:
    """Test the UUID is only checked once the device is known to be genuine."""
    cert = make_tls_cert(str(OTHER_UUID), pki.tls_key)
    reply = _reply(pki, peer_cert_der=der(cert), sign_over=b"other data")
    result = _verify(pki, reply, peer_cert_der=der(cert))
    assert result.status is DeviceAuthStatus.SIGNATURE_INVALID


def test_uuid_cn_not_a_uuid(pki: TestPKI) -> None:
    """Test a TLS certificate whose common name is not a UUID."""
    cert = make_tls_cert("not-a-uuid", pki.tls_key)
    result = _tls_reply(pki, der(cert))
    assert result.status is DeviceAuthStatus.UUID_MISMATCH
    assert "'not-a-uuid' is not a UUID" in result.detail


def test_uuid_cn_other_format(pki: TestPKI) -> None:
    """Test the UUID is compared as a UUID, not as a string."""
    cert = make_tls_cert(TEST_UUID.hex.upper(), pki.tls_key)
    result = _tls_reply(pki, der(cert))
    assert result.status is DeviceAuthStatus.VERIFIED


def test_uuid_not_checked_when_none(pki: TestPKI) -> None:
    """Test the UUID is not checked without an expected UUID."""
    cert = make_tls_cert("anything", pki.tls_key)
    result = _verify(
        pki,
        _reply(pki, peer_cert_der=der(cert)),
        peer_cert_der=der(cert),
        expected_uuid=None,
    )
    assert result.status is DeviceAuthStatus.VERIFIED
    assert not result.uuid_checked
    assert result.tls_cert_cn == "anything"


def test_too_many_intermediates(pki: TestPKI) -> None:
    """Test a reply with more intermediates than accepted."""
    result = _verify(pki, _reply(pki, intermediates=(pki.ica,) * 9))
    assert result.status is DeviceAuthStatus.MALFORMED_REPLY


class FakeAuthSocket:
    """A TLS socket of a fake device, for authenticate."""

    def __init__(
        self,
        peer_cert_der: bytes | None,
        responder: Callable[[bytes], list[bytes | BaseException]] | None = None,
    ) -> None:
        self.peer_cert_der = peer_cert_der
        self.responder = responder
        self.sent: list[CastMessage] = []
        self.reads: list[bytes | BaseException] = []
        self.timeouts: list[float | None] = []

    def getpeercert(self, binary_form: bool = False) -> bytes | None:
        """Return the TLS certificate."""
        assert binary_form
        return self.peer_cert_der

    def sendall(self, data: bytes) -> None:
        """Record a message, and queue the response."""
        (length,) = unpack(">I", data[:4])
        assert len(data) == 4 + length
        message = CastMessage()
        message.ParseFromString(data[4:])
        self.sent.append(message)
        if self.responder:
            self.reads.extend(self.responder(message.payload_binary))

    def recv(self, bufsize: int) -> bytes:
        """Return queued data."""
        if not self.reads:
            raise TimeoutError("timed out")
        item = self.reads.pop(0)
        if isinstance(item, BaseException):
            raise item
        chunk, rest = item[:bufsize], item[bufsize:]
        if rest:
            self.reads.insert(0, rest)
        return chunk

    def settimeout(self, timeout: float | None) -> None:
        """Record the timeout."""
        self.timeouts.append(timeout)


def _genuine(pki: TestPKI) -> Callable[[bytes], list[bytes | BaseException]]:
    """Return a responder answering the challenge like a genuine device."""

    def respond(payload: bytes) -> list[bytes | BaseException]:
        challenge = DeviceAuthMessage()
        challenge.ParseFromString(payload)
        return [frame(_reply(pki, nonce=challenge.challenge.sender_nonce))]

    return respond


def _authenticate(pki: TestPKI, sock: FakeAuthSocket) -> DeviceAuthResult:
    return authenticate(
        sock,  # type: ignore[arg-type]
        expected_uuid=TEST_UUID,
        timeout=1,
        trust_roots=[pki.root],
        now=NOW,
    )


def test_authenticate_genuine(pki: TestPKI) -> None:
    """Test authenticating a genuine device."""
    sock = FakeAuthSocket(pki.tls_der, _genuine(pki))
    result = _authenticate(pki, sock)
    assert result.status is DeviceAuthStatus.VERIFIED
    assert sock.timeouts
    assert all(timeout is not None and timeout <= 1 for timeout in sock.timeouts)


def test_authenticate_sends_only_challenge(pki: TestPKI) -> None:
    """Test only the challenge is sent, with a fresh nonce each time."""
    nonces = []
    for _ in range(2):
        sock = FakeAuthSocket(pki.tls_der, _genuine(pki))
        _authenticate(pki, sock)
        assert len(sock.sent) == 1
        message = sock.sent[0]
        assert message.namespace == NS_DEVICE_AUTH
        challenge = DeviceAuthMessage()
        challenge.ParseFromString(message.payload_binary)
        assert challenge.HasField("challenge")
        assert len(challenge.challenge.sender_nonce) == NONCE_LENGTH
        nonces.append(challenge.challenge.sender_nonce)
    assert nonces[0] != nonces[1]


def test_authenticate_timeout(pki: TestPKI) -> None:
    """Test a device which does not reply."""
    sock = FakeAuthSocket(pki.tls_der, lambda _: [TimeoutError("timed out")])
    assert _authenticate(pki, sock).status is DeviceAuthStatus.NO_REPLY


def test_authenticate_eof(pki: TestPKI) -> None:
    """Test a device closing the connection."""
    sock = FakeAuthSocket(pki.tls_der, lambda _: [b""])
    assert _authenticate(pki, sock).status is DeviceAuthStatus.CONNECTION_CLOSED


def test_authenticate_eof_mid_reply(pki: TestPKI) -> None:
    """Test a device closing the connection in the middle of the reply."""

    def respond(payload: bytes) -> list[bytes | BaseException]:
        return [_genuine(pki)(payload)[0][:20], b""]  # type: ignore[index]

    sock = FakeAuthSocket(pki.tls_der, respond)
    assert _authenticate(pki, sock).status is DeviceAuthStatus.CONNECTION_CLOSED


def test_authenticate_message_before_reply(pki: TestPKI) -> None:
    """Test a device sending another message before the reply."""
    status = CastMessage(
        protocol_version=CastMessage.CASTV2_1_0,
        source_id="receiver-0",
        destination_id="sender-0",
        namespace="urn:x-cast:com.google.cast.receiver",
        payload_type=CastMessage.STRING,
        payload_utf8='{"type": "RECEIVER_STATUS"}',
    )

    def respond(payload: bytes) -> list[bytes | BaseException]:
        return [frame(status), *_genuine(pki)(payload)]

    sock = FakeAuthSocket(pki.tls_der, respond)
    assert _authenticate(pki, sock).status is DeviceAuthStatus.UNEXPECTED_MESSAGE


@pytest.mark.parametrize("length", [0, 1024 * 1024])
def test_authenticate_bad_frame_length(pki: TestPKI, length: int) -> None:
    """Test a frame which is empty or too large."""
    sock = FakeAuthSocket(pki.tls_der, lambda _: [pack(">I", length) + b"x" * 100])
    assert _authenticate(pki, sock).status is DeviceAuthStatus.MALFORMED_REPLY


def test_authenticate_garbageframe(pki: TestPKI) -> None:
    """Test a frame which can't be parsed."""
    sock = FakeAuthSocket(pki.tls_der, lambda _: [pack(">I", 3) + b"\x0a\xff\xff"])
    assert _authenticate(pki, sock).status is DeviceAuthStatus.MALFORMED_REPLY


def test_authenticate_no_peer_cert_sends_nothing(pki: TestPKI) -> None:
    """Test nothing is sent to a device without a TLS certificate."""
    sock = FakeAuthSocket(None, _genuine(pki))
    assert _authenticate(pki, sock).status is DeviceAuthStatus.TLS_CERT_MALFORMED
    assert sock.sent == []


def test_authenticate_network_error_propagates(pki: TestPKI) -> None:
    """Test network errors are raised."""
    sock = FakeAuthSocket(pki.tls_der, lambda _: [ConnectionResetError("reset")])
    with pytest.raises(OSError):
        _authenticate(pki, sock)


def test_authenticate_reply_split_across_reads(pki: TestPKI) -> None:
    """Test a reply received in many small pieces."""

    def respond(payload: bytes) -> list[bytes | BaseException]:
        data = _genuine(pki)(payload)[0]
        assert isinstance(data, bytes)
        return [data[i : i + 7] for i in range(0, len(data), 7)]

    sock = FakeAuthSocket(pki.tls_der, respond)
    assert _authenticate(pki, sock).status is DeviceAuthStatus.VERIFIED


# verify_group_leader

GROUP_PORT = 32149


def _verify_group(
    pki: TestPKI, server: EurekaServer, **kwargs: Any
) -> DeviceAuthResult:
    options: dict[str, Any] = {"timeout": 2, "https_port": server.port}
    options.update(kwargs)
    return verify_group_leader(
        "127.0.0.1", GROUP_PORT, TEST_UUID, der(pki.leaf), **options
    )


def test_group_attested(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test a device which leads the group on the port."""
    server = eureka_factory(body=eureka_info([group_entry(GROUP_PORT)]))
    result = _verify_group(pki, server)
    assert result.status is DeviceAuthStatus.VERIFIED
    assert server.requests == [b"GET /setup/eureka_info?params=multizone HTTP/1.1"]


def test_group_attested_among_others(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test the group is found among other groups, its UUID in another format."""
    other = group_entry(GROUP_PORT, uuid=str(OTHER_UUID), cast_port=32150)
    entry = group_entry(GROUP_PORT, uuid=TEST_UUID.hex.upper())
    server = eureka_factory(body=eureka_info([other, entry]))
    assert _verify_group(pki, server).status is DeviceAuthStatus.VERIFIED


def test_group_wrong_port(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test a device which leads the group on another port."""
    server = eureka_factory(
        body=eureka_info([group_entry(GROUP_PORT, cast_port=32150)])
    )
    result = _verify_group(pki, server)
    assert result.status is DeviceAuthStatus.GROUP_PORT_MISMATCH
    assert result.failure_class is DeviceAuthFailureClass.WRONG_IDENTITY
    assert "32150" in result.detail


def test_group_port_of_led_entry(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test only the port of an entry the device leads counts."""
    led = group_entry(32150)
    member = group_entry(GROUP_PORT, elected_leader="[::1]:10001")
    server = eureka_factory(body=eureka_info([member, led]))
    result = _verify_group(pki, server)
    assert result.status is DeviceAuthStatus.GROUP_PORT_MISMATCH


def test_group_attestation_overall_deadline(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test fetching eureka_info is bounded by the timeout, not each step."""
    server = eureka_factory(body=eureka_info([group_entry(GROUP_PORT)]), mode="slow")
    start = time.monotonic()
    result = _verify_group(pki, server, timeout=0.6)
    elapsed = time.monotonic() - start
    assert result.status is DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE
    assert elapsed < 0.75


def test_group_member_not_leader(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test a member of the group which doesn't lead it."""
    entry = group_entry(
        GROUP_PORT, elected_leader="[::ffff:c0a8:a1]:10001", cast_port=None
    )
    server = eureka_factory(body=eureka_info([entry]))
    result = _verify_group(pki, server)
    assert result.status is DeviceAuthStatus.GROUP_NOT_LED
    assert "[::ffff:c0a8:a1]:10001" in result.detail


def test_group_missing(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test a device which is not in the group."""
    server = eureka_factory(
        body=eureka_info([group_entry(GROUP_PORT, uuid=str(OTHER_UUID))])
    )
    assert _verify_group(pki, server).status is DeviceAuthStatus.GROUP_NOT_LED


def test_group_leader_field_without_port(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test newer firmware, reportedly with leader instead of elected_leader."""
    entry = group_entry(GROUP_PORT, elected_leader=None, leader="self", cast_port=None)
    server = eureka_factory(body=eureka_info([entry]))
    result = _verify_group(pki, server)
    assert result.status is DeviceAuthStatus.VERIFIED
    assert "port is not reported" in result.detail


def test_group_dynamic(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test a dynamic group, which has no port."""
    entry = group_entry(GROUP_PORT, cast_port=None)
    server = eureka_factory(body=eureka_info(dynamic_groups=[entry]))
    assert _verify_group(pki, server).status is DeviceAuthStatus.VERIFIED


def test_group_leader_cert_mismatch(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test port 8443 presenting another certificate with the same subject."""
    key = rsa_key()
    leaf = pki.make_leaf(public_key=key.public_key())
    assert leaf.subject == pki.leaf.subject
    server = eureka_factory(
        cert=leaf, key=key, body=eureka_info([group_entry(GROUP_PORT)])
    )
    result = _verify_group(pki, server)
    assert result.status is DeviceAuthStatus.GROUP_LEADER_CERT_MISMATCH
    assert result.failure_class is DeviceAuthFailureClass.NOT_GENUINE
    # Nothing is requested from another device
    server.wait_idle()
    assert server.requests == []


def test_group_no_device_cert(eureka_factory: Callable[..., EurekaServer]) -> None:
    """Test attestation needs the authenticated device certificate."""
    server = eureka_factory(body=eureka_info([group_entry(GROUP_PORT)]))
    result = verify_group_leader(
        "127.0.0.1", GROUP_PORT, TEST_UUID, None, https_port=server.port
    )
    assert result.status is DeviceAuthStatus.GROUP_LEADER_CERT_MISMATCH
    # Nothing is contacted
    server.wait_idle()
    assert server.handlers == []


@pytest.mark.parametrize(
    ("kwargs", "timeout"),
    [
        ({"mode": "close"}, 2),
        ({"mode": "silent"}, 0.3),
        ({"body": b"<html>not json</html>"}, 2),
        ({"body": {"name": "no multizone"}}, 2),
        ({"status": 403}, 2),
    ],
)
def test_group_attestation_unavailable(
    pki: TestPKI,
    eureka_factory: Callable[..., EurekaServer],
    kwargs: dict[str, Any],
    timeout: float,
) -> None:
    """Test failures to fetch eureka_info."""
    server = eureka_factory(**kwargs)
    result = _verify_group(pki, server, timeout=timeout)
    assert result.status is DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE
    assert result.failure_class is DeviceAuthFailureClass.TRANSIENT


def test_group_attestation_port_closed(pki: TestPKI) -> None:
    """Test port 8443 refusing connections."""
    with refused_port() as port:
        result = verify_group_leader(
            "127.0.0.1", GROUP_PORT, TEST_UUID, der(pki.leaf), https_port=port
        )
    assert result.status is DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE


def test_failure_classes() -> None:
    """Test the class of every status, as specified."""
    expected = {
        DeviceAuthStatus.VERIFIED: None,
        DeviceAuthStatus.DISABLED: None,
        DeviceAuthStatus.UUID_MISMATCH: DeviceAuthFailureClass.WRONG_IDENTITY,
        DeviceAuthStatus.GROUP_NOT_LED: DeviceAuthFailureClass.WRONG_IDENTITY,
        DeviceAuthStatus.GROUP_PORT_MISMATCH: DeviceAuthFailureClass.WRONG_IDENTITY,
        DeviceAuthStatus.GROUP_ENDPOINT: DeviceAuthFailureClass.WRONG_IDENTITY,
        DeviceAuthStatus.CHAIN_UNTRUSTED: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.SIGNATURE_INVALID: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.NONCE_MISSING: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.NONCE_MISMATCH: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.UNSUPPORTED_ALGORITHM: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.CERT_INVALID: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.AUTH_ERROR_REPLY: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.UNEXPECTED_MESSAGE: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.MALFORMED_REPLY: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.GROUP_LEADER_CERT_MISMATCH: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.TLS_CERT_MALFORMED: DeviceAuthFailureClass.NOT_GENUINE,
        DeviceAuthStatus.TLS_CERT_INVALID: DeviceAuthFailureClass.CLOCK,
        DeviceAuthStatus.CERT_EXPIRED: DeviceAuthFailureClass.CLOCK,
        DeviceAuthStatus.NO_REPLY: DeviceAuthFailureClass.TRANSIENT,
        DeviceAuthStatus.CONNECTION_CLOSED: DeviceAuthFailureClass.TRANSIENT,
        DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE: DeviceAuthFailureClass.TRANSIENT,
    }
    assert set(expected) == set(DeviceAuthStatus)
    for status, failure_class in expected.items():
        assert DeviceAuthResult(status).failure_class is failure_class, status


def test_device_cert_der_not_in_repr(pki: TestPKI) -> None:
    """Test the device certificate is kept, but not shown in the repr."""
    result = _verify(pki, _reply(pki))
    assert result.device_cert_der == der(pki.leaf)
    assert "device_cert_der" not in repr(result)


# Only a genuine signature can lead to a failure blamed on the clock


def _forged(pki: TestPKI, **kwargs: Any) -> CastMessage:
    """Return a reply with a signature over something else."""
    return _reply(pki, sign_over=b"something else", **kwargs)


@pytest.mark.parametrize(
    ("not_before", "not_after"),
    [
        (NOW - timedelta(days=2), NOW - timedelta(seconds=1)),
        (NOW + timedelta(seconds=1), NOW + timedelta(days=2)),
        (NOW - timedelta(hours=1), NOW + timedelta(days=365)),
    ],
    ids=["expired", "not_yet_valid", "too_long"],
)
def test_forged_signature_bad_tls_cert(
    pki: TestPKI, not_before: datetime, not_after: datetime
) -> None:
    """Test a relay with a TLS certificate invalid now is not blamed on the clock."""
    cert = make_tls_cert(
        str(TEST_UUID), pki.tls_key, not_before=not_before, not_after=not_after
    )
    reply = _forged(pki, peer_cert_der=der(cert))
    result = _verify(pki, reply, peer_cert_der=der(cert))
    assert result.status is DeviceAuthStatus.SIGNATURE_INVALID
    assert result.failure_class is DeviceAuthFailureClass.NOT_GENUINE
    # With a genuine signature, the clock is blamed
    genuine = _verify(
        pki, _reply(pki, peer_cert_der=der(cert)), peer_cert_der=der(cert)
    )
    assert genuine.status is DeviceAuthStatus.TLS_CERT_INVALID
    assert genuine.failure_class is DeviceAuthFailureClass.CLOCK


@pytest.mark.parametrize(
    "dates",
    [
        {"not_after": NOW - timedelta(days=1)},
        {"not_before": NOW + timedelta(days=1)},
    ],
    ids=["expired", "not_yet_valid"],
)
@pytest.mark.parametrize("which", ["leaf", "intermediate"])
def test_forged_signature_expired_cert(
    pki: TestPKI, dates: dict[str, datetime], which: str
) -> None:
    """Test a replayed expired device certificate is not blamed on the clock."""
    if which == "leaf":
        kwargs: dict[str, Any] = {"leaf": pki.make_leaf(**dates)}
    else:
        kwargs = {"intermediates": (_ica(pki, **dates),)}
    result = _verify(pki, _forged(pki, **kwargs))
    assert result.status is DeviceAuthStatus.SIGNATURE_INVALID
    genuine = _verify(pki, _reply(pki, **kwargs))
    assert genuine.status is DeviceAuthStatus.CERT_EXPIRED
    assert genuine.failure_class is DeviceAuthFailureClass.CLOCK


def test_small_rsa_intermediate(pki: TestPKI) -> None:
    """Test an intermediate with a 1024 bit key."""
    key = rsa_key(1024)
    ica = make_cert(
        "Test ICA",
        pki.root,
        pki.root_key,
        key.public_key(),
        ca=True,
        path_length=0,
        ku=key_usage(key_cert_sign=True),
    )
    leaf = make_cert(
        "TEST FA8FCA000000",
        ica,
        key,
        pki.leaf_key.public_key(),
        ca=False,
        ku=LEAF_KEY_USAGE,
    )
    result = _verify(pki, _reply(pki, leaf=leaf, intermediates=(ica,)))
    assert result.status is DeviceAuthStatus.CERT_INVALID
    assert "intermediate certificate" in result.detail
    assert "1024" in result.detail


def test_unexpected_error_fails_closed(pki: TestPKI) -> None:
    """Test an unexpected error while verifying is a failure."""
    with patch(
        "pychromecast.device_auth._check_path", side_effect=RuntimeError("boom")
    ):
        result = _verify(pki, _reply(pki))
    assert result.status is DeviceAuthStatus.MALFORMED_REPLY
    assert "boom" in result.detail


# A real chain: the device certificate leaked with the shanocast receiver


def test_real_chain_accepted_by_bundled_roots() -> None:
    """Test a real SHA-1 signed device chain chains up to the bundled roots."""
    leaf = x509.load_pem_x509_certificate(SHANOCAST_DEVICE_CERT_PEM.encode())
    ica = x509.load_pem_x509_certificate(SHANOCAST_ICA_PEM.encode())
    path = _find_path(leaf, [ica], default_trust_roots())
    assert path is not None
    assert [_common_name(cert.subject) for cert in path] == [
        "WDFT3 FA8FCA895D59",
        "Eureka Gen1 ICA",
        "Eureka Root CA",
    ]
    assert _find_path(leaf, [ica], ()) is None


def test_real_chain_is_not_enough(pki: TestPKI) -> None:
    """Test a reply with a real chain but no matching signature is rejected.

    The chain passes with the bundled roots, which are used by default, the
    signature then fails: the chain alone proves nothing.
    """
    leaf = x509.load_pem_x509_certificate(SHANOCAST_DEVICE_CERT_PEM.encode())
    ica = x509.load_pem_x509_certificate(SHANOCAST_ICA_PEM.encode())
    # Signed with another key, the shanocast key is not known
    reply = _reply(pki, leaf=leaf, intermediates=(ica,))
    now = datetime(2025, 6, 1, tzinfo=UTC)
    tls_cert = make_tls_cert(
        str(TEST_UUID),
        pki.tls_key,
        not_before=now - timedelta(hours=1),
        not_after=now + timedelta(days=2),
    )
    reply = _reply(pki, leaf=leaf, intermediates=(ica,), peer_cert_der=der(tls_cert))
    result = _verify(pki, reply, peer_cert_der=der(tls_cert), trust_roots=None, now=now)
    assert result.status is DeviceAuthStatus.SIGNATURE_INVALID
    untrusted = _verify(
        pki, reply, peer_cert_der=der(tls_cert), trust_roots=[pki.root], now=now
    )
    assert untrusted.status is DeviceAuthStatus.CHAIN_UNTRUSTED


# Bounds against denial of service


def _cross_signed_intermediates(count: int) -> tuple[Any, list[x509.Certificate]]:
    """Return a leaf and intermediates all sharing one name and key."""
    key = rsa_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Loop ICA")])
    intermediates = []
    for _ in range(count):
        intermediates.append(
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(NOW - timedelta(days=1))
            .not_valid_after(NOW + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .sign(key, hashes.SHA256())
        )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "leaf")]))
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - timedelta(days=1))
        .not_valid_after(NOW + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return leaf, intermediates


def test_signature_check_budget(pki: TestPKI) -> None:
    """Test path building checks a bounded number of signatures."""
    # Without a bound, all 5! orders of the intermediates would be tried
    leaf, intermediates = _cross_signed_intermediates(5)
    with patch(
        "pychromecast.device_auth._signed_by",
        wraps=device_auth._signed_by,  # pylint: disable=protected-access
    ) as signed_by:
        path = _find_path(leaf, intermediates, [pki.root])
    assert path is None
    assert MAX_SIGNATURE_CHECKS == 64
    assert signed_by.call_count == 64


def test_intermediate_used_once(pki: TestPKI) -> None:
    """Test a self-signed intermediate is not used again to extend the path."""
    leaf, intermediates = _cross_signed_intermediates(1)
    with patch(
        "pychromecast.device_auth._signed_by",
        wraps=device_auth._signed_by,  # pylint: disable=protected-access
    ) as signed_by:
        path = _find_path(leaf, intermediates, [pki.root])
    assert path is None
    # The leaf by the intermediate, nothing more
    assert signed_by.call_count == 1


class DripSocket:
    """A socket of a device trickling its reply, one byte at a time."""

    def __init__(self, peer_cert_der: bytes, interval: float) -> None:
        self._sock, self._peer = socket.socketpair()
        self.peer_cert_der = peer_cert_der
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._drip, args=(interval,))
        self._thread.start()

    def _drip(self, interval: float) -> None:
        # The start of a 1000 byte message, which would take minutes
        data = pack(">I", 1000) + bytes(1000)
        for index in range(len(data)):
            if self._stop.wait(interval):
                return
            self._peer.send(data[index : index + 1])

    def getpeercert(self, binary_form: bool = False) -> bytes:
        """Return the TLS certificate."""
        assert binary_form
        return self.peer_cert_der

    def sendall(self, data: bytes) -> None:
        """Send data."""
        self._sock.sendall(data)

    def recv(self, bufsize: int) -> bytes:
        """Receive data."""
        return self._sock.recv(bufsize)

    def settimeout(self, timeout: float | None) -> None:
        """Set the timeout."""
        self._sock.settimeout(timeout)

    def close(self) -> None:
        """Stop dripping and close the sockets."""
        self._stop.set()
        self._thread.join()
        self._sock.close()
        self._peer.close()


def test_authenticate_reply_deadline(pki: TestPKI) -> None:
    """Test a trickled reply times out after the timeout, not per read."""
    sock = DripSocket(pki.tls_der, 0.45)
    try:
        start = time.monotonic()
        result = authenticate(
            sock,  # type: ignore[arg-type]
            expected_uuid=TEST_UUID,
            timeout=1,
            trust_roots=[pki.root],
            now=NOW,
        )
        elapsed = time.monotonic() - start
    finally:
        sock.close()
    assert result.status is DeviceAuthStatus.NO_REPLY
    assert 0.9 <= elapsed < 1.2


def test_group_eureka_info_size_limit(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test a too large eureka_info is not used."""
    body = eureka_info([group_entry(GROUP_PORT)])
    body["padding"] = "x" * MAX_EUREKA_INFO_SIZE
    server = eureka_factory(body=body)
    result = _verify_group(pki, server)
    assert result.status is DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE
    assert "too large" in result.detail


def test_group_unexpected_error_fails_closed(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test an unexpected error while checking a group is a failure."""
    server = eureka_factory(body=eureka_info([group_entry(GROUP_PORT)]))
    with patch(
        "pychromecast.device_auth._check_group_leadership",
        side_effect=RuntimeError("boom"),
    ):
        result = _verify_group(pki, server)
    assert result.status is DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE
    assert "boom" in result.detail


# verify_not_group_endpoint


def _verify_endpoint(
    pki: TestPKI, server: EurekaServer, port: int = GROUP_PORT
) -> DeviceAuthResult:
    return verify_not_group_endpoint(
        "127.0.0.1", port, der(pki.leaf), timeout=2, https_port=server.port
    )


def test_endpoint_is_group_port(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test the port of a group the device leads is refused as the device."""
    server = eureka_factory(body=eureka_info([group_entry(GROUP_PORT)]))
    result = _verify_endpoint(pki, server)
    assert result.status is DeviceAuthStatus.GROUP_ENDPOINT
    assert result.failure_class is DeviceAuthFailureClass.WRONG_IDENTITY
    assert str(TEST_UUID) in result.detail


@pytest.mark.parametrize(
    "body",
    [
        eureka_info([group_entry(32150)]),
        eureka_info([group_entry(GROUP_PORT, elected_leader="[::1]:10001")]),
        eureka_info(dynamic_groups=[group_entry(None)]),
        eureka_info(),
        {"name": "no multizone"},
    ],
    ids=["other_port", "member", "dynamic", "no_groups", "no_multizone"],
)
def test_endpoint_not_group_port(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer], body: Any
) -> None:
    """Test a port which is not the port of a group the device leads."""
    server = eureka_factory(body=body)
    assert _verify_endpoint(pki, server).status is DeviceAuthStatus.VERIFIED
    assert len(server.requests) == 1


def test_endpoint_check_fails_closed(pki: TestPKI) -> None:
    """Test the device's groups not being available is a failure."""
    with refused_port() as port:
        result = verify_not_group_endpoint(
            "127.0.0.1", GROUP_PORT, der(pki.leaf), https_port=port
        )
    assert result.status is DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE


def test_endpoint_cert_mismatch(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test another device's eureka_info is not used."""
    key = rsa_key()
    server = eureka_factory(
        cert=pki.make_leaf(public_key=key.public_key()), key=key, body=eureka_info()
    )
    result = _verify_endpoint(pki, server)
    assert result.status is DeviceAuthStatus.GROUP_LEADER_CERT_MISMATCH
    server.wait_idle()
    assert server.requests == []


def test_endpoint_no_device_cert(
    eureka_factory: Callable[..., EurekaServer],
) -> None:
    """Test the check needs the authenticated device certificate."""
    server = eureka_factory()
    result = verify_not_group_endpoint(
        "127.0.0.1", GROUP_PORT, None, https_port=server.port
    )
    assert result.status is DeviceAuthStatus.GROUP_LEADER_CERT_MISMATCH
    server.wait_idle()
    assert server.handlers == []


def test_endpoint_unexpected_error_fails_closed(
    pki: TestPKI, eureka_factory: Callable[..., EurekaServer]
) -> None:
    """Test an unexpected error while checking the endpoint is a failure."""
    server = eureka_factory()
    with patch(
        "pychromecast.device_auth._multizone_groups", side_effect=RuntimeError("boom")
    ):
        result = _verify_endpoint(pki, server)
    assert result.status is DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE


def test_default_attestation_port(pki: TestPKI) -> None:
    """Test eureka_info is fetched from GROUP_ATTESTATION_PORT by default."""
    with (
        refused_port() as port,
        patch("pychromecast.device_auth.GROUP_ATTESTATION_PORT", port),
        patch(
            "pychromecast.device_auth._fetch_eureka_info", side_effect=RuntimeError
        ) as fetch,
    ):
        verify_group_leader("127.0.0.1", GROUP_PORT, TEST_UUID, der(pki.leaf))
        verify_not_group_endpoint("127.0.0.1", GROUP_PORT, der(pki.leaf))
    assert [call.args[1] for call in fetch.call_args_list] == [port, port]
