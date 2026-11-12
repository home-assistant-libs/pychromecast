"""
Cast device authentication.

A sender authenticates a cast device right after the TLS handshake, before
talking to it. The device's TLS certificate is self-signed and short lived, so
it says nothing about the device. Instead, the sender sends a challenge on the
deviceauth namespace with a fresh random nonce, and the device answers with:

- its device certificate, issued by the device's manufacturer and chaining up
  to one of Google's Cast roots, plus the intermediate certificates;
- the echoed nonce;
- a signature, made with the device certificate's key, over the echoed nonce
  followed by the DER encoding of the device's TLS certificate.

The signature binds the TLS connection to a key only a genuine device has. A
relay presenting its own TLS certificate can't produce it, and a replayed reply
signs another nonce.

These checks are performed, in this order:

- the reply is the first message received, and on the deviceauth namespace;
- the nonce is echoed exactly;
- the signature algorithm is RSASSA-PKCS1-v1_5, with SHA-256 or SHA-1;
- the TLS certificate can be parsed;
- the device certificate chains up to a trusted root. The device certificate
  and the intermediates must have an RSA key of at least 2048 bits. The device
  certificate must allow digital signatures, the intermediates must be CAs
  allowed to sign certificates and their path length constraints must hold;
- the signature verifies with the device certificate's key;
- the TLS certificate is valid now, for at most four more days, and the device
  certificate and the intermediates are valid now. These checks come after the
  signature, so only a genuine device can fail for a reason blamed on the
  clock;
- if an expected UUID is given, the common name of the TLS certificate is that
  UUID. Cast devices put their UUID there, and the signature covers the TLS
  certificate, so a genuine device can't claim another device's UUID.

A cast group is served by its leader, whose TLS certificate names the leader,
not the group. verify_group_leader checks that an authenticated device leads a
group: it fetches the device's eureka_info over HTTPS on port 8443, where the
device presents its device certificate. The certificate must be the one which
just passed device authentication, and the device must list the group as led
by itself, on the port which was connected to. Conversely, as a device presents
its own TLS certificate on the ports of the groups it leads,
verify_not_group_endpoint checks that a port is not one of them.

Neither binds the connection to a port of the device: the TLS certificate and
the signature are the same on every port of a device. A forwarder which
doesn't terminate TLS can relay a connection to another endpoint of the same
genuine device, its port 8009 or another group it leads.

Things deliberately not done:

- the certificate revocation list the device sends is not checked;
- devices are not pinned, there's no trust on first use;
- the validity and constraints of the root certificate are not checked, as in
  the Open Screen implementation;
- unknown critical extensions are not rejected, the Cast specific extensions
  aren't documented and rejecting them could fail genuine devices.
"""

import functools
import hmac
import http.client
import json
import logging
import secrets
import socket
import ssl
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from struct import pack, unpack
from uuid import UUID

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID, SignatureAlgorithmOID
from google.protobuf.message import DecodeError

from .device_auth_roots import CAST_ROOT_CA_PEM, EUREKA_ROOT_CA_PEM

# pylint: disable-next=no-name-in-module
from .generated.cast_channel_pb2 import (
    SHA1,
    SHA256,
    RSASSA_PKCS1v15,
    AuthChallenge,
    AuthError,
    AuthResponse,
    CastMessage,
    DeviceAuthMessage,
)

NS_DEVICE_AUTH = "urn:x-cast:com.google.cast.tp.deviceauth"

# Length of the random nonce sent in the challenge
NONCE_LENGTH = 16
# Seconds to wait for the reply to the challenge
DEVICE_AUTH_TIMEOUT = 10.0
# The longest a TLS certificate may remain valid, as in Open Screen
MAX_TLS_CERT_REMAINING_VALIDITY = timedelta(days=4)
# Largest message accepted, as in Chromium
MAX_MESSAGE_SIZE = 65536
# Most intermediate certificates accepted in a reply
MAX_INTERMEDIATES = 8
# Most certificate signatures checked while building a path
MAX_SIGNATURE_CHECKS = 64
MIN_RSA_KEY_SIZE = 2048
# HTTPS port where cast devices serve eureka_info with their device certificate
GROUP_ATTESTATION_PORT = 8443
GROUP_ATTESTATION_PATH = "/setup/eureka_info?params=multizone"
# Largest eureka_info response accepted
MAX_EUREKA_INFO_SIZE = 1024 * 1024

_LOGGER = logging.getLogger(__name__)

_RSA_SIGNATURE_OIDS = frozenset(
    {
        SignatureAlgorithmOID.RSA_WITH_SHA1,
        SignatureAlgorithmOID.RSA_WITH_SHA256,
        SignatureAlgorithmOID.RSA_WITH_SHA384,
        SignatureAlgorithmOID.RSA_WITH_SHA512,
    }
)

# Hash algorithms accepted for the signature of the reply. SHA-256 is always
# requested, but SHA-1 is accepted like in Chromium: the signed data starts
# with our fresh nonce, so forging it needs a second preimage, not a collision.
_RESPONSE_HASHES: dict[int, Callable[[], hashes.HashAlgorithm]] = {
    SHA1: hashes.SHA1,
    SHA256: hashes.SHA256,
}


class DeviceAuthStatus(StrEnum):
    """Outcome of Cast device authentication."""

    # The device is genuine
    VERIFIED = "verified"
    # Device authentication was disabled, nothing was checked
    DISABLED = "disabled"
    # The device did not reply in time
    NO_REPLY = "no_reply"
    # The device closed the connection before replying
    CONNECTION_CLOSED = "connection_closed"
    # The first message from the device was not a device auth message
    UNEXPECTED_MESSAGE = "unexpected_message"
    # The reply could not be parsed
    MALFORMED_REPLY = "malformed_reply"
    # The device replied with an error
    AUTH_ERROR_REPLY = "auth_error_reply"
    # The reply does not echo the nonce
    NONCE_MISSING = "nonce_missing"
    # The reply echoes another nonce
    NONCE_MISMATCH = "nonce_mismatch"
    # The reply uses a signature or hash algorithm which is not accepted
    UNSUPPORTED_ALGORITHM = "unsupported_algorithm"
    # The TLS certificate is missing or can't be parsed
    TLS_CERT_MALFORMED = "tls_cert_malformed"
    # The TLS certificate is not valid now
    TLS_CERT_INVALID = "tls_cert_invalid"
    # The device certificate or an intermediate is not acceptable
    CERT_INVALID = "cert_invalid"
    # The device certificate or an intermediate is not valid now
    CERT_EXPIRED = "cert_expired"
    # The device certificate does not chain up to a trusted root
    CHAIN_UNTRUSTED = "chain_untrusted"
    # The signature in the reply does not verify
    SIGNATURE_INVALID = "signature_invalid"
    # The device is genuine, but the TLS certificate is not for the expected UUID
    UUID_MISMATCH = "uuid_mismatch"
    # The device is genuine, but doesn't lead the expected group
    GROUP_NOT_LED = "group_not_led"
    # The device is genuine and leads the expected group, but on another port
    GROUP_PORT_MISMATCH = "group_port_mismatch"
    # The device certificate on port 8443 is not the authenticated one
    GROUP_LEADER_CERT_MISMATCH = "group_leader_cert_mismatch"
    # The group leadership could not be checked, for example port 8443 is blocked
    GROUP_ATTESTATION_UNAVAILABLE = "group_attestation_unavailable"
    # The device is genuine, but the endpoint is the port of a group it leads
    GROUP_ENDPOINT = "group_endpoint"


class DeviceAuthFailureClass(StrEnum):
    """What a device authentication failure says about the responder."""

    # A genuine device answered, but it is another device or doesn't lead the
    # group. Benign causes: a stale IP address, for example after a DHCP lease
    # moved, or a group leader change. Consumers should apply a grace period
    # before surfacing it.
    WRONG_IDENTITY = "wrong_identity"
    # The responder is not a genuine cast device, or misbehaves
    NOT_GENUINE = "not_genuine"
    # A certificate is not valid now: the system clock is wrong, or a device
    # certificate really expired
    CLOCK = "clock"
    # No usable answer, like a network failure
    TRANSIENT = "transient"


_FAILURE_CLASSES: dict[DeviceAuthStatus, DeviceAuthFailureClass] = {
    DeviceAuthStatus.UUID_MISMATCH: DeviceAuthFailureClass.WRONG_IDENTITY,
    DeviceAuthStatus.GROUP_NOT_LED: DeviceAuthFailureClass.WRONG_IDENTITY,
    DeviceAuthStatus.GROUP_PORT_MISMATCH: DeviceAuthFailureClass.WRONG_IDENTITY,
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
    DeviceAuthStatus.GROUP_ENDPOINT: DeviceAuthFailureClass.WRONG_IDENTITY,
    DeviceAuthStatus.TLS_CERT_INVALID: DeviceAuthFailureClass.CLOCK,
    DeviceAuthStatus.CERT_EXPIRED: DeviceAuthFailureClass.CLOCK,
    DeviceAuthStatus.NO_REPLY: DeviceAuthFailureClass.TRANSIENT,
    DeviceAuthStatus.CONNECTION_CLOSED: DeviceAuthFailureClass.TRANSIENT,
    DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE: DeviceAuthFailureClass.TRANSIENT,
}


@dataclass(frozen=True)
class DeviceAuthResult:
    """Result of Cast device authentication."""

    status: DeviceAuthStatus
    # Human readable explanation, safe to log
    detail: str = ""
    # Subject of the device certificate, RFC 4514
    device_cert_subject: str | None = None
    # Common name of the trusted root the device certificate chains up to
    trust_root: str | None = None
    # Common name of the TLS certificate
    tls_cert_cn: str | None = None
    # True if the TLS certificate was checked against the expected UUID
    uuid_checked: bool = False
    # Hash algorithm of the reply's signature, "sha256" or "sha1"
    hash_algorithm: str | None = None
    # DER encoding of the device certificate, set if the device is genuine
    device_cert_der: bytes | None = field(default=None, repr=False)
    # UUID of the group leader, set when a group was verified through its leader
    leader_uuid: UUID | None = None

    @property
    def verified(self) -> bool:
        """Return True if the device is genuine."""
        return self.status is DeviceAuthStatus.VERIFIED

    @property
    def failure_class(self) -> DeviceAuthFailureClass | None:
        """Return the class of the failure, None if authentication didn't fail."""
        return _FAILURE_CLASSES.get(self.status)

    @property
    def tls_cert_uuid(self) -> UUID | None:
        """Return the common name of the TLS certificate as a UUID, if it is one."""
        if self.tls_cert_cn is None:
            return None
        try:
            return UUID(self.tls_cert_cn)
        except ValueError:
            return None


class _AuthFailure(Exception):
    """Device authentication failed."""

    def __init__(self, status: DeviceAuthStatus, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail

    def result(self) -> DeviceAuthResult:
        """Return the result for the failure."""
        return DeviceAuthResult(self.status, self.detail)


@functools.cache
def default_trust_roots() -> tuple[x509.Certificate, ...]:
    """Return the bundled roots, the Cast Root CA and the Eureka Root CA."""
    return (
        x509.load_pem_x509_certificate(CAST_ROOT_CA_PEM.encode()),
        x509.load_pem_x509_certificate(EUREKA_ROOT_CA_PEM.encode()),
    )


def build_challenge(nonce: bytes) -> CastMessage:
    """Return the challenge message for a nonce."""
    auth_message = DeviceAuthMessage(
        challenge=AuthChallenge(
            signature_algorithm=RSASSA_PKCS1v15,
            sender_nonce=nonce,
            hash_algorithm=SHA256,
        )
    )
    return CastMessage(
        protocol_version=CastMessage.CASTV2_1_0,
        source_id="sender-0",
        destination_id="receiver-0",
        namespace=NS_DEVICE_AUTH,
        payload_type=CastMessage.BINARY,
        payload_binary=auth_message.SerializeToString(),
    )


def _common_name(name: x509.Name) -> str | None:
    """Return the first common name of a name."""
    for attribute in name.get_attributes_for_oid(NameOID.COMMON_NAME):
        if isinstance(attribute.value, str):
            return attribute.value
    return None


def _subject(cert: x509.Certificate) -> str:
    """Return the subject of a certificate, for logging."""
    try:
        return cert.subject.rfc4514_string()
    except ValueError:
        return "<invalid subject>"


def _parse_cert(der: bytes, status: DeviceAuthStatus, what: str) -> x509.Certificate:
    """Parse a DER certificate, failing with status."""
    try:
        return x509.load_der_x509_certificate(der)
    except ValueError as err:
        raise _AuthFailure(status, f"{what} can't be parsed: {err}") from err


def _parse_response(reply: CastMessage, nonce: bytes) -> AuthResponse:
    """Return the response in a reply, checking the echoed nonce."""
    if reply.namespace != NS_DEVICE_AUTH:
        raise _AuthFailure(
            DeviceAuthStatus.UNEXPECTED_MESSAGE,
            f"expected a device auth reply, got a message on {reply.namespace}",
        )
    if reply.payload_type != CastMessage.BINARY:
        raise _AuthFailure(
            DeviceAuthStatus.MALFORMED_REPLY, "reply does not have a binary payload"
        )
    auth_message = DeviceAuthMessage()
    try:
        auth_message.ParseFromString(reply.payload_binary)
    except DecodeError as err:
        raise _AuthFailure(
            DeviceAuthStatus.MALFORMED_REPLY, f"reply can't be parsed: {err}"
        ) from err
    if auth_message.HasField("error"):
        error_type = auth_message.error.error_type
        try:
            error_name = AuthError.ErrorType.Name(error_type)
        except ValueError:
            error_name = str(error_type)
        raise _AuthFailure(
            DeviceAuthStatus.AUTH_ERROR_REPLY, f"device replied with error {error_name}"
        )
    if not auth_message.HasField("response"):
        raise _AuthFailure(
            DeviceAuthStatus.MALFORMED_REPLY,
            "reply has neither a response nor an error",
        )
    response = auth_message.response
    # Parsing doesn't enforce the required fields
    if not response.IsInitialized():
        raise _AuthFailure(
            DeviceAuthStatus.MALFORMED_REPLY,
            "response lacks the signature or the device certificate",
        )
    if not response.HasField("sender_nonce"):
        raise _AuthFailure(
            DeviceAuthStatus.NONCE_MISSING, "reply does not echo the nonce"
        )
    if not hmac.compare_digest(response.sender_nonce, nonce):
        raise _AuthFailure(
            DeviceAuthStatus.NONCE_MISMATCH, "reply echoes another nonce"
        )
    return response


def _response_hash(response: AuthResponse) -> hashes.HashAlgorithm:
    """Return the hash algorithm of the response's signature."""
    if response.signature_algorithm != RSASSA_PKCS1v15:
        raise _AuthFailure(
            DeviceAuthStatus.UNSUPPORTED_ALGORITHM,
            f"signature algorithm {response.signature_algorithm} is not supported",
        )
    hash_factory = _RESPONSE_HASHES.get(response.hash_algorithm)
    if hash_factory is None:
        raise _AuthFailure(
            DeviceAuthStatus.UNSUPPORTED_ALGORITHM,
            f"hash algorithm {response.hash_algorithm} is not supported",
        )
    return hash_factory()


def _parse_tls_cert(peer_cert_der: bytes | None) -> x509.Certificate:
    """Parse the TLS certificate."""
    status = DeviceAuthStatus.TLS_CERT_MALFORMED
    if peer_cert_der is None:
        raise _AuthFailure(status, "the device did not present a TLS certificate")
    return _parse_cert(peer_cert_der, status, "TLS certificate")


def _check_tls_cert_validity(cert: x509.Certificate, now: datetime) -> None:
    """Check the TLS certificate is valid now, for at most a few more days."""
    status = DeviceAuthStatus.TLS_CERT_INVALID
    if now < cert.not_valid_before_utc:
        raise _AuthFailure(
            status,
            "TLS certificate is not valid before "
            f"{cert.not_valid_before_utc.isoformat()}, check the system clock",
        )
    if cert.not_valid_after_utc < now:
        raise _AuthFailure(
            status,
            f"TLS certificate expired at {cert.not_valid_after_utc.isoformat()}, "
            "check the system clock",
        )
    if cert.not_valid_after_utc > now + MAX_TLS_CERT_REMAINING_VALIDITY:
        raise _AuthFailure(
            status,
            f"TLS certificate is valid until {cert.not_valid_after_utc.isoformat()}, "
            "too far in the future, check the system clock",
        )


def _signed_by(child: x509.Certificate, issuer: x509.Certificate) -> bool:
    """Return True if issuer's key signed child.

    The certificate verification of cryptography rejects SHA-1, which the Cast
    roots and many device certificates use, so the signature is checked here.
    """
    if child.signature_algorithm_oid not in _RSA_SIGNATURE_OIDS:
        return False
    try:
        key = issuer.public_key()
        hash_algorithm = child.signature_hash_algorithm
    except ValueError, UnsupportedAlgorithm:
        return False
    if not isinstance(key, rsa.RSAPublicKey) or hash_algorithm is None:
        return False
    try:
        key.verify(
            child.signature,
            child.tbs_certificate_bytes,
            padding.PKCS1v15(),
            hash_algorithm,
        )
    except InvalidSignature, UnsupportedAlgorithm:
        return False
    return True


def _candidate_paths(
    leaf: x509.Certificate,
    intermediates: Sequence[x509.Certificate],
    roots: Sequence[x509.Certificate],
) -> Iterator[list[x509.Certificate]]:
    """Yield the paths [leaf, intermediates..., root] whose signatures check out.

    The intermediates may be in any order. Each is used at most once in a path.
    All paths share a budget of MAX_SIGNATURE_CHECKS signature checks.
    """
    checks_left = MAX_SIGNATURE_CHECKS

    def signed_by(child: x509.Certificate, issuer: x509.Certificate) -> bool:
        nonlocal checks_left
        if child.issuer != issuer.subject or checks_left <= 0:
            return False
        checks_left -= 1
        return _signed_by(child, issuer)

    def extend(
        cert: x509.Certificate, used: frozenset[int]
    ) -> Iterator[list[x509.Certificate]]:
        for root in roots:
            if signed_by(cert, root):
                yield [root]
        for index, intermediate in enumerate(intermediates):
            if index in used or not signed_by(cert, intermediate):
                continue
            for rest in extend(intermediate, used | {index}):
                yield [intermediate, *rest]

    for rest in extend(leaf, frozenset()):
        yield [leaf, *rest]


def _find_path(
    leaf: x509.Certificate,
    intermediates: Sequence[x509.Certificate],
    roots: Sequence[x509.Certificate],
) -> list[x509.Certificate] | None:
    """Return the first path [leaf, intermediates..., root], or None."""
    return next(_candidate_paths(leaf, intermediates, roots), None)


def _check_rsa_key(cert: x509.Certificate, what: str) -> None:
    """Check the certificate has an RSA key of at least MIN_RSA_KEY_SIZE bits."""
    try:
        key = cert.public_key()
    except ValueError, UnsupportedAlgorithm:
        key = None
    if not isinstance(key, rsa.RSAPublicKey):
        raise _AuthFailure(
            DeviceAuthStatus.CERT_INVALID,
            f"{what} {_subject(cert)} does not have an RSA key",
        )
    if key.key_size < MIN_RSA_KEY_SIZE:
        raise _AuthFailure(
            DeviceAuthStatus.CERT_INVALID,
            f"{what} {_subject(cert)} has a {key.key_size} bit key, "
            f"at least {MIN_RSA_KEY_SIZE} bits are required",
        )


def _check_validity(cert: x509.Certificate, what: str, now: datetime) -> None:
    """Check the certificate is valid now."""
    if now < cert.not_valid_before_utc:
        raise _AuthFailure(
            DeviceAuthStatus.CERT_EXPIRED,
            f"{what} {_subject(cert)} is not valid before "
            f"{cert.not_valid_before_utc.isoformat()}",
        )
    if cert.not_valid_after_utc < now:
        raise _AuthFailure(
            DeviceAuthStatus.CERT_EXPIRED,
            f"{what} {_subject(cert)} expired at "
            f"{cert.not_valid_after_utc.isoformat()}, "
            "a firmware update of the device may fix this",
        )


def _extension[ExtensionT: x509.ExtensionType](
    cert: x509.Certificate, extension_type: type[ExtensionT], what: str
) -> ExtensionT | None:
    """Return an extension of the certificate, or None if it has none."""
    try:
        return cert.extensions.get_extension_for_class(extension_type).value
    except x509.ExtensionNotFound:
        return None
    except ValueError as err:
        raise _AuthFailure(
            DeviceAuthStatus.CERT_INVALID,
            f"{what} {_subject(cert)} has invalid extensions: {err}",
        ) from err


def _check_path(path: Sequence[x509.Certificate]) -> None:
    """Check the keys and constraints of a path [leaf, intermediates..., root].

    The root is trusted as is, its validity and constraints are not checked.
    Validity is checked by _check_path_validity, once the signature verified.
    """
    leaf = path[0]
    _check_rsa_key(leaf, "device certificate")
    key_usage = _extension(leaf, x509.KeyUsage, "device certificate")
    if key_usage is None or not key_usage.digital_signature:
        raise _AuthFailure(
            DeviceAuthStatus.CERT_INVALID,
            f"device certificate {_subject(leaf)} does not allow digital signatures",
        )

    for index in range(1, len(path) - 1):
        intermediate = path[index]
        what = "intermediate certificate"
        _check_rsa_key(intermediate, what)
        constraints = _extension(intermediate, x509.BasicConstraints, what)
        if constraints is None or not constraints.ca:
            raise _AuthFailure(
                DeviceAuthStatus.CERT_INVALID,
                f"{what} {_subject(intermediate)} is not a CA",
            )
        key_usage = _extension(intermediate, x509.KeyUsage, what)
        if key_usage is not None and not key_usage.key_cert_sign:
            raise _AuthFailure(
                DeviceAuthStatus.CERT_INVALID,
                f"{what} {_subject(intermediate)} does not allow signing certificates",
            )
        # The number of intermediates between this one and the leaf
        if constraints.path_length is not None and index - 1 > constraints.path_length:
            raise _AuthFailure(
                DeviceAuthStatus.CERT_INVALID,
                f"{what} {_subject(intermediate)} path length constraint "
                f"{constraints.path_length} is violated",
            )


def _check_path_validity(path: Sequence[x509.Certificate], now: datetime) -> None:
    """Check the leaf and the intermediates of a path are valid now."""
    _check_validity(path[0], "device certificate", now)
    for intermediate in path[1:-1]:
        _check_validity(intermediate, "intermediate certificate", now)


def _verify_chain(
    response: AuthResponse,
    roots: Sequence[x509.Certificate],
) -> tuple[list[list[x509.Certificate]], dict[int, _AuthFailure]]:
    """Find the paths from the device certificate to a root which pass constraints.

    Returns the paths [leaf, intermediates..., root] whose keys and constraints
    are acceptable, and the failure of each path which isn't, by index of the
    path among all found. Validity is not checked. Raises the failure of the
    first path found if no path is acceptable.
    """
    if len(response.intermediate_certificate) > MAX_INTERMEDIATES:
        raise _AuthFailure(
            DeviceAuthStatus.MALFORMED_REPLY,
            f"reply has {len(response.intermediate_certificate)} intermediate "
            f"certificates, at most {MAX_INTERMEDIATES} are accepted",
        )
    status = DeviceAuthStatus.CERT_INVALID
    leaf = _parse_cert(response.client_auth_certificate, status, "device certificate")
    intermediates = [
        _parse_cert(der, status, "intermediate certificate")
        for der in response.intermediate_certificate
    ]
    # An expired or unusable intermediate may come before a usable one
    paths = list(_candidate_paths(leaf, intermediates, roots))
    if not paths:
        raise _AuthFailure(
            DeviceAuthStatus.CHAIN_UNTRUSTED,
            f"device certificate {_subject(leaf)} does not chain up to a trusted root",
        )
    usable: list[list[x509.Certificate]] = []
    failures: dict[int, _AuthFailure] = {}
    for index, path in enumerate(paths):
        try:
            _check_path(path)
        except _AuthFailure as failure:
            failures[index] = failure
            continue
        usable.append(path)
    if not usable:
        raise failures[0]
    return usable, failures


def _verify_signature(
    response: AuthResponse,
    leaf: x509.Certificate,
    peer_cert_der: bytes,
    hash_algorithm: hashes.HashAlgorithm,
) -> None:
    """Verify the signature over the echoed nonce and the TLS certificate."""
    key = leaf.public_key()
    assert isinstance(key, rsa.RSAPublicKey)  # Checked by _check_path
    try:
        key.verify(
            response.signature,
            response.sender_nonce + peer_cert_der,
            padding.PKCS1v15(),
            hash_algorithm,
        )
    except InvalidSignature as err:
        raise _AuthFailure(
            DeviceAuthStatus.SIGNATURE_INVALID, "signature of the reply does not verify"
        ) from err


def _first_valid_path(
    paths: list[list[x509.Certificate]],
    failures: dict[int, _AuthFailure],
    now: datetime,
) -> list[x509.Certificate]:
    """Return the first path valid now.

    If none is, raise the failure of the first path found, which may be a
    constraint failure from _verify_chain.
    """
    first_failure: _AuthFailure | None = failures.get(0)
    for path in paths:
        try:
            _check_path_validity(path, now)
        except _AuthFailure as failure:
            if first_failure is None:
                first_failure = failure
            continue
        return path
    assert first_failure is not None
    raise first_failure


def _verify(
    reply: CastMessage,
    nonce: bytes,
    peer_cert_der: bytes | None,
    expected_uuid: UUID | None,
    roots: Sequence[x509.Certificate],
    now: datetime,
) -> DeviceAuthResult:
    """Verify a reply, raise _AuthFailure if it's not acceptable.

    The validity of the certificates is checked after the signature, so only a
    device holding a genuine key can fail for a reason blamed on the clock.
    """
    response = _parse_response(reply, nonce)
    hash_algorithm = _response_hash(response)
    tls_cert = _parse_tls_cert(peer_cert_der)
    assert peer_cert_der is not None  # Checked by _parse_tls_cert
    paths, failures = _verify_chain(response, roots)
    # All paths start with the device certificate, which signed the reply
    leaf = paths[0][0]
    _verify_signature(response, leaf, peer_cert_der, hash_algorithm)
    _check_tls_cert_validity(tls_cert, now)
    path = _first_valid_path(paths, failures, now)

    result = DeviceAuthResult(
        DeviceAuthStatus.VERIFIED,
        "device is genuine",
        device_cert_subject=_subject(leaf),
        trust_root=_common_name(path[-1].subject),
        tls_cert_cn=_common_name(tls_cert.subject),
        hash_algorithm=hash_algorithm.name,
        device_cert_der=response.client_auth_certificate,
    )
    # The identity is checked last, a mismatch means the device is genuine
    if expected_uuid is None:
        return result
    if result.tls_cert_uuid is None:
        return replace(
            result,
            status=DeviceAuthStatus.UUID_MISMATCH,
            detail=(
                f"TLS certificate CN {result.tls_cert_cn!r} is not a UUID, "
                f"expected {expected_uuid}"
            ),
        )
    if result.tls_cert_uuid != expected_uuid:
        return replace(
            result,
            status=DeviceAuthStatus.UUID_MISMATCH,
            detail=(
                f"TLS certificate CN {result.tls_cert_cn!r} does not match "
                f"the expected UUID {expected_uuid}"
            ),
        )
    return replace(result, uuid_checked=True)


def verify_auth_reply(
    reply: CastMessage,
    *,
    nonce: bytes,
    peer_cert_der: bytes | None,
    expected_uuid: UUID | None,
    trust_roots: Sequence[x509.Certificate] | None = None,
    now: datetime | None = None,
) -> DeviceAuthResult:
    """Verify the reply to a challenge.

    :param reply: The first message received after sending the challenge.
    :param nonce: The nonce sent in the challenge.
    :param peer_cert_der: The DER encoded TLS certificate of the device.
    :param expected_uuid: The UUID the TLS certificate must be for, or None to
                          not check it.
    :param trust_roots: The trusted roots, None for the bundled Cast roots.
    :param now: The current time, None to use the system clock.

    Never raises, every failure is reported in the result.
    """
    if trust_roots is None:
        trust_roots = default_trust_roots()
    if now is None:
        now = datetime.now(UTC)
    try:
        return _verify(reply, nonce, peer_cert_der, expected_uuid, trust_roots, now)
    except _AuthFailure as failure:
        return failure.result()
    except Exception as err:  # pylint: disable=broad-exception-caught
        # Fail closed if a malformed reply trips something unexpected
        return DeviceAuthResult(
            DeviceAuthStatus.MALFORMED_REPLY,
            f"unexpected error verifying the reply: {err!r}",
        )


def _recv_exact(sock: ssl.SSLSocket, size: int, deadline: float) -> bytes:
    """Receive exactly size bytes before the deadline."""
    data = b""
    while len(data) < size:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise _AuthFailure(DeviceAuthStatus.NO_REPLY, "timed out waiting for reply")
        sock.settimeout(timeout)
        try:
            chunk = sock.recv(size - len(data))
        except TimeoutError as err:
            raise _AuthFailure(
                DeviceAuthStatus.NO_REPLY, "timed out waiting for reply"
            ) from err
        except ssl.SSLEOFError as err:
            raise _AuthFailure(
                DeviceAuthStatus.CONNECTION_CLOSED,
                "connection closed before the reply was received",
            ) from err
        if not chunk:
            raise _AuthFailure(
                DeviceAuthStatus.CONNECTION_CLOSED,
                "connection closed before the reply was received",
            )
        data += chunk
    return data


def _recv_frame(sock: ssl.SSLSocket, deadline: float) -> CastMessage:
    """Receive one message before the deadline."""
    (length,) = unpack(">I", _recv_exact(sock, 4, deadline))
    if length == 0 or length > MAX_MESSAGE_SIZE:
        raise _AuthFailure(
            DeviceAuthStatus.MALFORMED_REPLY, f"invalid message length {length}"
        )
    message = CastMessage()
    try:
        message.ParseFromString(_recv_exact(sock, length, deadline))
    except DecodeError as err:
        raise _AuthFailure(
            DeviceAuthStatus.MALFORMED_REPLY, f"message can't be parsed: {err}"
        ) from err
    return message


def authenticate(
    sock: ssl.SSLSocket,
    *,
    expected_uuid: UUID | None,
    timeout: float = DEVICE_AUTH_TIMEOUT,
    trust_roots: Sequence[x509.Certificate] | None = None,
    now: datetime | None = None,
) -> DeviceAuthResult:
    """Authenticate the device on a newly connected TLS socket.

    Sends the challenge and waits for exactly one message, which must be the
    reply. Nothing else is sent. The socket's timeout is changed, the caller
    should restore it.

    Returns a result for every authentication outcome, including no reply and
    the connection being closed. Other network errors are raised as OSError.

    Data received after the reply stays buffered in the SSL socket. It is not
    lost, but the socket client only reads it, through pending(), once the
    selector reports more data, for example the device's next message.
    """
    peer_cert_der = sock.getpeercert(binary_form=True)
    if peer_cert_der is None:
        # Don't send anything to a device without a TLS certificate
        return DeviceAuthResult(
            DeviceAuthStatus.TLS_CERT_MALFORMED,
            "the device did not present a TLS certificate",
        )
    nonce = secrets.token_bytes(NONCE_LENGTH)
    challenge = build_challenge(nonce)
    deadline = time.monotonic() + timeout
    sock.sendall(pack(">I", challenge.ByteSize()) + challenge.SerializeToString())
    try:
        reply = _recv_frame(sock, deadline)
    except _AuthFailure as failure:
        return failure.result()
    return verify_auth_reply(
        reply,
        nonce=nonce,
        peer_cert_der=peer_cert_der,
        expected_uuid=expected_uuid,
        trust_roots=trust_roots,
        now=now,
    )


def _host_header(address: str, port: int) -> str:
    """Return the Host header for an IP address, without its IPv6 scope."""
    address = address.partition("%")[0]
    return f"[{address}]:{port}" if ":" in address else f"{address}:{port}"


class _FetchDeadline:
    """An overall deadline for fetching eureka_info.

    When it expires, a timer shuts the watched socket down, which ends any call
    blocked on it, whichever step it is in.
    """

    def __init__(self, timeout: float) -> None:
        self._deadline = time.monotonic() + timeout
        self._lock = threading.Lock()
        self._sockets: list[socket.socket] = []
        self._aborted = False
        self._done = False
        self._timer = threading.Timer(timeout, self._abort)
        self._timer.daemon = True
        self._timer.start()

    def _abort(self) -> None:
        with self._lock:
            if self._done:
                return
            self._aborted = True
            for sock in self._sockets:
                try:
                    # The fd, not the TLS layer, which another thread is using
                    socket.socket.shutdown(sock, socket.SHUT_RDWR)
                except OSError:
                    pass

    def watch(self, sock: socket.socket) -> None:
        """Shut sock down when the deadline expires."""
        with self._lock:
            self._sockets.append(sock)
            aborted = self._aborted
        if aborted:
            self.left()

    def left(self) -> float:
        """Return the time left, raise if the deadline expired."""
        left = self._deadline - time.monotonic()
        if self._aborted or left <= 0:
            raise _AuthFailure(
                DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE,
                "timed out fetching eureka_info",
            )
        return left

    def stop(self) -> None:
        """Stop the timer, the watched sockets are about to be closed."""
        with self._lock:
            self._done = True
        self._timer.cancel()


def _connect_pinned(
    host: str, https_port: int, device_cert_der: bytes, deadline: _FetchDeadline
) -> ssl.SSLSocket:
    """Connect over TLS to a device which must present device_cert_der."""
    unavailable = DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE
    try:
        raw = socket.create_connection((host, https_port), deadline.left())
    except OSError as err:
        deadline.left()
        raise _AuthFailure(
            unavailable, f"can't connect to port {https_port}: {err!r}"
        ) from err
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        tls = context.wrap_socket(raw, do_handshake_on_connect=False)
    except BaseException:
        raw.close()
        raise
    try:
        deadline.watch(tls)
        try:
            tls.settimeout(deadline.left())
            tls.do_handshake()
        except OSError as err:
            deadline.left()
            raise _AuthFailure(
                unavailable, f"TLS handshake on port {https_port} failed: {err!r}"
            ) from err
        # The TLS handshake proved the device holds the certificate's key
        if tls.getpeercert(binary_form=True) != device_cert_der:
            raise _AuthFailure(
                DeviceAuthStatus.GROUP_LEADER_CERT_MISMATCH,
                f"the certificate on port {https_port} is not the device "
                "certificate which passed device authentication",
            )
    except BaseException:
        tls.close()
        raise
    return tls


def _fetch_eureka_info(
    host: str, https_port: int, device_cert_der: bytes, timeout: float
) -> object:
    """Fetch eureka_info from a device presenting the device certificate.

    The whole fetch, from connecting to reading the body, is bounded by timeout.
    """
    unavailable = DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE
    deadline = _FetchDeadline(timeout)
    try:
        tls = _connect_pinned(host, https_port, device_cert_der, deadline)
        # Plain HTTP over the TLS socket which was already set up
        conn = http.client.HTTPConnection(host, https_port, timeout=timeout)
        conn.sock = tls
        try:
            tls.settimeout(deadline.left())
            conn.request(
                "GET",
                GROUP_ATTESTATION_PATH,
                headers={
                    # Devices reject a host name in the Host header
                    "Host": _host_header(tls.getpeername()[0], https_port),
                    "Connection": "close",
                },
            )
            tls.settimeout(deadline.left())
            response = conn.getresponse()
            if response.status != 200:
                raise _AuthFailure(
                    unavailable,
                    f"eureka_info request failed with HTTP status {response.status}",
                )
            # Devices keep the connection open, don't read until EOF
            tls.settimeout(deadline.left())
            body = response.read(MAX_EUREKA_INFO_SIZE + 1)
            deadline.left()
        except (OSError, http.client.HTTPException) as err:
            deadline.left()
            raise _AuthFailure(
                unavailable, f"eureka_info request failed: {err!r}"
            ) from err
        finally:
            deadline.stop()
            conn.close()
    finally:
        deadline.stop()
    if len(body) > MAX_EUREKA_INFO_SIZE:
        raise _AuthFailure(unavailable, "eureka_info response is too large")
    try:
        return json.loads(body)
    except ValueError as err:
        raise _AuthFailure(
            unavailable, f"eureka_info response is not JSON: {err}"
        ) from err


def _multizone_groups(eureka_info: object) -> list[dict] | None:
    """Return the groups and dynamic groups of eureka_info.

    Returns None if eureka_info has no multizone information.
    """
    multizone = eureka_info.get("multizone") if isinstance(eureka_info, dict) else None
    if not isinstance(multizone, dict):
        return None
    entries: list[dict] = []
    for key in ("groups", "dynamic_groups"):
        groups = multizone.get(key)
        if isinstance(groups, list):
            entries.extend(entry for entry in groups if isinstance(entry, dict))
    return entries


def _is_led(entry: dict) -> bool:
    """Return True if a group entry of eureka_info is led by the device."""
    # Some firmware reportedly renames elected_leader to leader
    return "self" in (entry.get("elected_leader"), entry.get("leader"))


def _group_entries(eureka_info: object, group_uuid: UUID) -> list[dict]:
    """Return the entries of eureka_info for a group."""
    groups = _multizone_groups(eureka_info)
    if groups is None:
        raise _AuthFailure(
            DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE,
            "eureka_info has no multizone information",
        )
    entries = []
    for entry in groups:
        if not isinstance(entry.get("uuid"), str):
            continue
        try:
            if UUID(entry["uuid"]) == group_uuid:
                entries.append(entry)
        except ValueError:
            continue
    return entries


def _check_group_leadership(
    eureka_info: object, group_uuid: UUID, port: int
) -> DeviceAuthResult:
    """Check eureka_info lists the group as led by the device, on the port."""
    entries = _group_entries(eureka_info, group_uuid)
    if not entries:
        raise _AuthFailure(
            DeviceAuthStatus.GROUP_NOT_LED,
            f"the device is not a member of group {group_uuid}",
        )
    led = [entry for entry in entries if _is_led(entry)]
    if not led:
        leader = entries[0].get("elected_leader") or entries[0].get("leader")
        raise _AuthFailure(
            DeviceAuthStatus.GROUP_NOT_LED,
            f"the device does not lead group {group_uuid}, the leader is {leader!r}",
        )
    for entry in led:
        cast_port = entry.get("cast_port")
        if cast_port == port:
            return DeviceAuthResult(
                DeviceAuthStatus.VERIFIED,
                f"the device leads group {group_uuid} on port {port}",
            )
        if cast_port is None:
            # Dynamic groups and some firmware don't report the port
            _LOGGER.debug(
                "Group %s is led by the device, its port is not reported and "
                "can't be checked",
                group_uuid,
            )
            return DeviceAuthResult(
                DeviceAuthStatus.VERIFIED,
                f"the device leads group {group_uuid}, its port is not reported",
            )
    raise _AuthFailure(
        DeviceAuthStatus.GROUP_PORT_MISMATCH,
        f"the device leads group {group_uuid} on port {led[0].get('cast_port')}, "
        f"not on port {port}",
    )


def verify_group_leader(
    host: str,
    port: int,
    group_uuid: UUID,
    device_cert_der: bytes | None,
    *,
    timeout: float = DEVICE_AUTH_TIMEOUT,
    https_port: int | None = None,
) -> DeviceAuthResult:
    """Verify an authenticated device leads a group on host:port.

    :param host: The address of the device.
    :param port: The port of the group endpoint.
    :param group_uuid: The UUID of the group.
    :param device_cert_der: The device certificate which passed device
                            authentication on host:port.
    :param timeout: The time allowed to fetch eureka_info, in seconds.
    :param https_port: The port to fetch eureka_info from, None for
                       GROUP_ATTESTATION_PORT.

    Fetches eureka_info from https_port, where the device must present
    device_cert_der. The device must list the group as led by itself, on port
    if it reports the port. Returns a VERIFIED result or a failure, never
    raises.
    """
    if device_cert_der is None:
        # A programming error, only genuine devices have a device certificate
        return DeviceAuthResult(
            DeviceAuthStatus.GROUP_LEADER_CERT_MISMATCH,
            "no authenticated device certificate to compare with",
        )
    try:
        eureka_info = _fetch_eureka_info(
            host, https_port or GROUP_ATTESTATION_PORT, device_cert_der, timeout
        )
        return _check_group_leadership(eureka_info, group_uuid, port)
    except _AuthFailure as failure:
        return failure.result()
    except Exception as err:  # pylint: disable=broad-exception-caught
        return DeviceAuthResult(
            DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE,
            f"unexpected error checking the group leader: {err!r}",
        )


def verify_not_group_endpoint(
    host: str,
    port: int,
    device_cert_der: bytes | None,
    *,
    timeout: float = DEVICE_AUTH_TIMEOUT,
    https_port: int | None = None,
) -> DeviceAuthResult:
    """Verify host:port is not the port of a group the authenticated device leads.

    A device presents its own TLS certificate on the ports of the groups it
    leads, so its UUID matches there too. Fetches eureka_info like
    verify_group_leader, and fails with GROUP_ENDPOINT if the device leads a
    group on port. A device without multizone information leads no group.
    Fails closed if eureka_info can't be fetched. Never raises.
    """
    if device_cert_der is None:
        # A programming error, only genuine devices have a device certificate
        return DeviceAuthResult(
            DeviceAuthStatus.GROUP_LEADER_CERT_MISMATCH,
            "no authenticated device certificate to compare with",
        )
    try:
        eureka_info = _fetch_eureka_info(
            host, https_port or GROUP_ATTESTATION_PORT, device_cert_der, timeout
        )
        for entry in _multizone_groups(eureka_info) or []:
            if _is_led(entry) and entry.get("cast_port") == port:
                return DeviceAuthResult(
                    DeviceAuthStatus.GROUP_ENDPOINT,
                    f"port {port} is the port of group {entry.get('uuid')} "
                    "led by the device, not the device itself",
                )
        return DeviceAuthResult(
            DeviceAuthStatus.VERIFIED,
            f"port {port} is not the port of a group led by the device",
        )
    except _AuthFailure as failure:
        return failure.result()
    except Exception as err:  # pylint: disable=broad-exception-caught
        return DeviceAuthResult(
            DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE,
            f"unexpected error checking the device's groups: {err!r}",
        )
