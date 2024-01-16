from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SignatureAlgorithm(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNSPECIFIED: _ClassVar[SignatureAlgorithm]
    RSASSA_PKCS1v15: _ClassVar[SignatureAlgorithm]
    RSASSA_PSS: _ClassVar[SignatureAlgorithm]

class HashAlgorithm(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SHA1: _ClassVar[HashAlgorithm]
    SHA256: _ClassVar[HashAlgorithm]
UNSPECIFIED: SignatureAlgorithm
RSASSA_PKCS1v15: SignatureAlgorithm
RSASSA_PSS: SignatureAlgorithm
SHA1: HashAlgorithm
SHA256: HashAlgorithm

class CastMessage(_message.Message):
    __slots__ = ("protocol_version", "source_id", "destination_id", "namespace", "payload_type", "payload_utf8", "payload_binary")
    class ProtocolVersion(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        CASTV2_1_0: _ClassVar[CastMessage.ProtocolVersion]
    CASTV2_1_0: CastMessage.ProtocolVersion
    class PayloadType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        STRING: _ClassVar[CastMessage.PayloadType]
        BINARY: _ClassVar[CastMessage.PayloadType]
    STRING: CastMessage.PayloadType
    BINARY: CastMessage.PayloadType
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    SOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    DESTINATION_ID_FIELD_NUMBER: _ClassVar[int]
    NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_UTF8_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_BINARY_FIELD_NUMBER: _ClassVar[int]
    protocol_version: CastMessage.ProtocolVersion
    source_id: str
    destination_id: str
    namespace: str
    payload_type: CastMessage.PayloadType
    payload_utf8: str
    payload_binary: bytes
    def __init__(self, protocol_version: _Optional[_Union[CastMessage.ProtocolVersion, str]] = ..., source_id: _Optional[str] = ..., destination_id: _Optional[str] = ..., namespace: _Optional[str] = ..., payload_type: _Optional[_Union[CastMessage.PayloadType, str]] = ..., payload_utf8: _Optional[str] = ..., payload_binary: _Optional[bytes] = ...) -> None: ...

class AuthChallenge(_message.Message):
    __slots__ = ("signature_algorithm", "sender_nonce", "hash_algorithm")
    SIGNATURE_ALGORITHM_FIELD_NUMBER: _ClassVar[int]
    SENDER_NONCE_FIELD_NUMBER: _ClassVar[int]
    HASH_ALGORITHM_FIELD_NUMBER: _ClassVar[int]
    signature_algorithm: SignatureAlgorithm
    sender_nonce: bytes
    hash_algorithm: HashAlgorithm
    def __init__(self, signature_algorithm: _Optional[_Union[SignatureAlgorithm, str]] = ..., sender_nonce: _Optional[bytes] = ..., hash_algorithm: _Optional[_Union[HashAlgorithm, str]] = ...) -> None: ...

class AuthResponse(_message.Message):
    __slots__ = ("signature", "client_auth_certificate", "intermediate_certificate", "signature_algorithm", "sender_nonce", "hash_algorithm", "crl")
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    CLIENT_AUTH_CERTIFICATE_FIELD_NUMBER: _ClassVar[int]
    INTERMEDIATE_CERTIFICATE_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_ALGORITHM_FIELD_NUMBER: _ClassVar[int]
    SENDER_NONCE_FIELD_NUMBER: _ClassVar[int]
    HASH_ALGORITHM_FIELD_NUMBER: _ClassVar[int]
    CRL_FIELD_NUMBER: _ClassVar[int]
    signature: bytes
    client_auth_certificate: bytes
    intermediate_certificate: _containers.RepeatedScalarFieldContainer[bytes]
    signature_algorithm: SignatureAlgorithm
    sender_nonce: bytes
    hash_algorithm: HashAlgorithm
    crl: bytes
    def __init__(self, signature: _Optional[bytes] = ..., client_auth_certificate: _Optional[bytes] = ..., intermediate_certificate: _Optional[_Iterable[bytes]] = ..., signature_algorithm: _Optional[_Union[SignatureAlgorithm, str]] = ..., sender_nonce: _Optional[bytes] = ..., hash_algorithm: _Optional[_Union[HashAlgorithm, str]] = ..., crl: _Optional[bytes] = ...) -> None: ...

class AuthError(_message.Message):
    __slots__ = ("error_type",)
    class ErrorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        INTERNAL_ERROR: _ClassVar[AuthError.ErrorType]
        NO_TLS: _ClassVar[AuthError.ErrorType]
        SIGNATURE_ALGORITHM_UNAVAILABLE: _ClassVar[AuthError.ErrorType]
    INTERNAL_ERROR: AuthError.ErrorType
    NO_TLS: AuthError.ErrorType
    SIGNATURE_ALGORITHM_UNAVAILABLE: AuthError.ErrorType
    ERROR_TYPE_FIELD_NUMBER: _ClassVar[int]
    error_type: AuthError.ErrorType
    def __init__(self, error_type: _Optional[_Union[AuthError.ErrorType, str]] = ...) -> None: ...

class DeviceAuthMessage(_message.Message):
    __slots__ = ("challenge", "response", "error")
    CHALLENGE_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    challenge: AuthChallenge
    response: AuthResponse
    error: AuthError
    def __init__(self, challenge: _Optional[_Union[AuthChallenge, _Mapping]] = ..., response: _Optional[_Union[AuthResponse, _Mapping]] = ..., error: _Optional[_Union[AuthError, _Mapping]] = ...) -> None: ...
