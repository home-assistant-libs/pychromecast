from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EVENT_TYPE_UNKNOWN: _ClassVar[EventType]
    CAST_SOCKET_CREATED: _ClassVar[EventType]
    READY_STATE_CHANGED: _ClassVar[EventType]
    CONNECTION_STATE_CHANGED: _ClassVar[EventType]
    READ_STATE_CHANGED: _ClassVar[EventType]
    WRITE_STATE_CHANGED: _ClassVar[EventType]
    ERROR_STATE_CHANGED: _ClassVar[EventType]
    CONNECT_FAILED: _ClassVar[EventType]
    TCP_SOCKET_CONNECT: _ClassVar[EventType]
    TCP_SOCKET_SET_KEEP_ALIVE: _ClassVar[EventType]
    SSL_CERT_WHITELISTED: _ClassVar[EventType]
    SSL_SOCKET_CONNECT: _ClassVar[EventType]
    SSL_INFO_OBTAINED: _ClassVar[EventType]
    DER_ENCODED_CERT_OBTAIN: _ClassVar[EventType]
    RECEIVED_CHALLENGE_REPLY: _ClassVar[EventType]
    AUTH_CHALLENGE_REPLY: _ClassVar[EventType]
    CONNECT_TIMED_OUT: _ClassVar[EventType]
    SEND_MESSAGE_FAILED: _ClassVar[EventType]
    MESSAGE_ENQUEUED: _ClassVar[EventType]
    SOCKET_WRITE: _ClassVar[EventType]
    MESSAGE_WRITTEN: _ClassVar[EventType]
    SOCKET_READ: _ClassVar[EventType]
    MESSAGE_READ: _ClassVar[EventType]
    SOCKET_CLOSED: _ClassVar[EventType]
    SSL_CERT_EXCESSIVE_LIFETIME: _ClassVar[EventType]
    CHANNEL_POLICY_ENFORCED: _ClassVar[EventType]
    TCP_SOCKET_CONNECT_COMPLETE: _ClassVar[EventType]
    SSL_SOCKET_CONNECT_COMPLETE: _ClassVar[EventType]
    SSL_SOCKET_CONNECT_FAILED: _ClassVar[EventType]
    SEND_AUTH_CHALLENGE_FAILED: _ClassVar[EventType]
    AUTH_CHALLENGE_REPLY_INVALID: _ClassVar[EventType]
    PING_WRITE_ERROR: _ClassVar[EventType]

class ChannelAuth(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SSL: _ClassVar[ChannelAuth]
    SSL_VERIFIED: _ClassVar[ChannelAuth]

class ReadyState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    READY_STATE_NONE: _ClassVar[ReadyState]
    READY_STATE_CONNECTING: _ClassVar[ReadyState]
    READY_STATE_OPEN: _ClassVar[ReadyState]
    READY_STATE_CLOSING: _ClassVar[ReadyState]
    READY_STATE_CLOSED: _ClassVar[ReadyState]

class ConnectionState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CONN_STATE_UNKNOWN: _ClassVar[ConnectionState]
    CONN_STATE_TCP_CONNECT: _ClassVar[ConnectionState]
    CONN_STATE_TCP_CONNECT_COMPLETE: _ClassVar[ConnectionState]
    CONN_STATE_SSL_CONNECT: _ClassVar[ConnectionState]
    CONN_STATE_SSL_CONNECT_COMPLETE: _ClassVar[ConnectionState]
    CONN_STATE_AUTH_CHALLENGE_SEND: _ClassVar[ConnectionState]
    CONN_STATE_AUTH_CHALLENGE_SEND_COMPLETE: _ClassVar[ConnectionState]
    CONN_STATE_AUTH_CHALLENGE_REPLY_COMPLETE: _ClassVar[ConnectionState]
    CONN_STATE_START_CONNECT: _ClassVar[ConnectionState]
    CONN_STATE_FINISHED: _ClassVar[ConnectionState]
    CONN_STATE_ERROR: _ClassVar[ConnectionState]
    CONN_STATE_TIMEOUT: _ClassVar[ConnectionState]

class ReadState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    READ_STATE_UNKNOWN: _ClassVar[ReadState]
    READ_STATE_READ: _ClassVar[ReadState]
    READ_STATE_READ_COMPLETE: _ClassVar[ReadState]
    READ_STATE_DO_CALLBACK: _ClassVar[ReadState]
    READ_STATE_HANDLE_ERROR: _ClassVar[ReadState]
    READ_STATE_ERROR: _ClassVar[ReadState]

class WriteState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WRITE_STATE_UNKNOWN: _ClassVar[WriteState]
    WRITE_STATE_WRITE: _ClassVar[WriteState]
    WRITE_STATE_WRITE_COMPLETE: _ClassVar[WriteState]
    WRITE_STATE_DO_CALLBACK: _ClassVar[WriteState]
    WRITE_STATE_HANDLE_ERROR: _ClassVar[WriteState]
    WRITE_STATE_ERROR: _ClassVar[WriteState]
    WRITE_STATE_IDLE: _ClassVar[WriteState]

class ErrorState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CHANNEL_ERROR_NONE: _ClassVar[ErrorState]
    CHANNEL_ERROR_CHANNEL_NOT_OPEN: _ClassVar[ErrorState]
    CHANNEL_ERROR_AUTHENTICATION_ERROR: _ClassVar[ErrorState]
    CHANNEL_ERROR_CONNECT_ERROR: _ClassVar[ErrorState]
    CHANNEL_ERROR_SOCKET_ERROR: _ClassVar[ErrorState]
    CHANNEL_ERROR_TRANSPORT_ERROR: _ClassVar[ErrorState]
    CHANNEL_ERROR_INVALID_MESSAGE: _ClassVar[ErrorState]
    CHANNEL_ERROR_INVALID_CHANNEL_ID: _ClassVar[ErrorState]
    CHANNEL_ERROR_CONNECT_TIMEOUT: _ClassVar[ErrorState]
    CHANNEL_ERROR_UNKNOWN: _ClassVar[ErrorState]

class ChallengeReplyErrorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CHALLENGE_REPLY_ERROR_NONE: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_PEER_CERT_EMPTY: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_WRONG_PAYLOAD_TYPE: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_NO_PAYLOAD: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_PAYLOAD_PARSING_FAILED: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_MESSAGE_ERROR: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_NO_RESPONSE: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_FINGERPRINT_NOT_FOUND: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_CERT_PARSING_FAILED: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_CERT_NOT_SIGNED_BY_TRUSTED_CA: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_CANNOT_EXTRACT_PUBLIC_KEY: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_SIGNED_BLOBS_MISMATCH: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_TLS_CERT_VALIDITY_PERIOD_TOO_LONG: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_TLS_CERT_VALID_START_DATE_IN_FUTURE: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_TLS_CERT_EXPIRED: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_CRL_INVALID: _ClassVar[ChallengeReplyErrorType]
    CHALLENGE_REPLY_ERROR_CERT_REVOKED: _ClassVar[ChallengeReplyErrorType]
EVENT_TYPE_UNKNOWN: EventType
CAST_SOCKET_CREATED: EventType
READY_STATE_CHANGED: EventType
CONNECTION_STATE_CHANGED: EventType
READ_STATE_CHANGED: EventType
WRITE_STATE_CHANGED: EventType
ERROR_STATE_CHANGED: EventType
CONNECT_FAILED: EventType
TCP_SOCKET_CONNECT: EventType
TCP_SOCKET_SET_KEEP_ALIVE: EventType
SSL_CERT_WHITELISTED: EventType
SSL_SOCKET_CONNECT: EventType
SSL_INFO_OBTAINED: EventType
DER_ENCODED_CERT_OBTAIN: EventType
RECEIVED_CHALLENGE_REPLY: EventType
AUTH_CHALLENGE_REPLY: EventType
CONNECT_TIMED_OUT: EventType
SEND_MESSAGE_FAILED: EventType
MESSAGE_ENQUEUED: EventType
SOCKET_WRITE: EventType
MESSAGE_WRITTEN: EventType
SOCKET_READ: EventType
MESSAGE_READ: EventType
SOCKET_CLOSED: EventType
SSL_CERT_EXCESSIVE_LIFETIME: EventType
CHANNEL_POLICY_ENFORCED: EventType
TCP_SOCKET_CONNECT_COMPLETE: EventType
SSL_SOCKET_CONNECT_COMPLETE: EventType
SSL_SOCKET_CONNECT_FAILED: EventType
SEND_AUTH_CHALLENGE_FAILED: EventType
AUTH_CHALLENGE_REPLY_INVALID: EventType
PING_WRITE_ERROR: EventType
SSL: ChannelAuth
SSL_VERIFIED: ChannelAuth
READY_STATE_NONE: ReadyState
READY_STATE_CONNECTING: ReadyState
READY_STATE_OPEN: ReadyState
READY_STATE_CLOSING: ReadyState
READY_STATE_CLOSED: ReadyState
CONN_STATE_UNKNOWN: ConnectionState
CONN_STATE_TCP_CONNECT: ConnectionState
CONN_STATE_TCP_CONNECT_COMPLETE: ConnectionState
CONN_STATE_SSL_CONNECT: ConnectionState
CONN_STATE_SSL_CONNECT_COMPLETE: ConnectionState
CONN_STATE_AUTH_CHALLENGE_SEND: ConnectionState
CONN_STATE_AUTH_CHALLENGE_SEND_COMPLETE: ConnectionState
CONN_STATE_AUTH_CHALLENGE_REPLY_COMPLETE: ConnectionState
CONN_STATE_START_CONNECT: ConnectionState
CONN_STATE_FINISHED: ConnectionState
CONN_STATE_ERROR: ConnectionState
CONN_STATE_TIMEOUT: ConnectionState
READ_STATE_UNKNOWN: ReadState
READ_STATE_READ: ReadState
READ_STATE_READ_COMPLETE: ReadState
READ_STATE_DO_CALLBACK: ReadState
READ_STATE_HANDLE_ERROR: ReadState
READ_STATE_ERROR: ReadState
WRITE_STATE_UNKNOWN: WriteState
WRITE_STATE_WRITE: WriteState
WRITE_STATE_WRITE_COMPLETE: WriteState
WRITE_STATE_DO_CALLBACK: WriteState
WRITE_STATE_HANDLE_ERROR: WriteState
WRITE_STATE_ERROR: WriteState
WRITE_STATE_IDLE: WriteState
CHANNEL_ERROR_NONE: ErrorState
CHANNEL_ERROR_CHANNEL_NOT_OPEN: ErrorState
CHANNEL_ERROR_AUTHENTICATION_ERROR: ErrorState
CHANNEL_ERROR_CONNECT_ERROR: ErrorState
CHANNEL_ERROR_SOCKET_ERROR: ErrorState
CHANNEL_ERROR_TRANSPORT_ERROR: ErrorState
CHANNEL_ERROR_INVALID_MESSAGE: ErrorState
CHANNEL_ERROR_INVALID_CHANNEL_ID: ErrorState
CHANNEL_ERROR_CONNECT_TIMEOUT: ErrorState
CHANNEL_ERROR_UNKNOWN: ErrorState
CHALLENGE_REPLY_ERROR_NONE: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_PEER_CERT_EMPTY: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_WRONG_PAYLOAD_TYPE: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_NO_PAYLOAD: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_PAYLOAD_PARSING_FAILED: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_MESSAGE_ERROR: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_NO_RESPONSE: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_FINGERPRINT_NOT_FOUND: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_CERT_PARSING_FAILED: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_CERT_NOT_SIGNED_BY_TRUSTED_CA: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_CANNOT_EXTRACT_PUBLIC_KEY: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_SIGNED_BLOBS_MISMATCH: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_TLS_CERT_VALIDITY_PERIOD_TOO_LONG: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_TLS_CERT_VALID_START_DATE_IN_FUTURE: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_TLS_CERT_EXPIRED: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_CRL_INVALID: ChallengeReplyErrorType
CHALLENGE_REPLY_ERROR_CERT_REVOKED: ChallengeReplyErrorType

class SocketEvent(_message.Message):
    __slots__ = ("type", "timestamp_micros", "details", "net_return_value", "message_namespace", "ready_state", "connection_state", "read_state", "write_state", "error_state", "challenge_reply_error_type", "nss_error_code")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_MICROS_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    NET_RETURN_VALUE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    READY_STATE_FIELD_NUMBER: _ClassVar[int]
    CONNECTION_STATE_FIELD_NUMBER: _ClassVar[int]
    READ_STATE_FIELD_NUMBER: _ClassVar[int]
    WRITE_STATE_FIELD_NUMBER: _ClassVar[int]
    ERROR_STATE_FIELD_NUMBER: _ClassVar[int]
    CHALLENGE_REPLY_ERROR_TYPE_FIELD_NUMBER: _ClassVar[int]
    NSS_ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    type: EventType
    timestamp_micros: int
    details: str
    net_return_value: int
    message_namespace: str
    ready_state: ReadyState
    connection_state: ConnectionState
    read_state: ReadState
    write_state: WriteState
    error_state: ErrorState
    challenge_reply_error_type: ChallengeReplyErrorType
    nss_error_code: int
    def __init__(self, type: _Optional[_Union[EventType, str]] = ..., timestamp_micros: _Optional[int] = ..., details: _Optional[str] = ..., net_return_value: _Optional[int] = ..., message_namespace: _Optional[str] = ..., ready_state: _Optional[_Union[ReadyState, str]] = ..., connection_state: _Optional[_Union[ConnectionState, str]] = ..., read_state: _Optional[_Union[ReadState, str]] = ..., write_state: _Optional[_Union[WriteState, str]] = ..., error_state: _Optional[_Union[ErrorState, str]] = ..., challenge_reply_error_type: _Optional[_Union[ChallengeReplyErrorType, str]] = ..., nss_error_code: _Optional[int] = ...) -> None: ...

class AggregatedSocketEvent(_message.Message):
    __slots__ = ("id", "endpoint_id", "channel_auth_type", "socket_event", "bytes_read", "bytes_written")
    ID_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_ID_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_AUTH_TYPE_FIELD_NUMBER: _ClassVar[int]
    SOCKET_EVENT_FIELD_NUMBER: _ClassVar[int]
    BYTES_READ_FIELD_NUMBER: _ClassVar[int]
    BYTES_WRITTEN_FIELD_NUMBER: _ClassVar[int]
    id: int
    endpoint_id: int
    channel_auth_type: ChannelAuth
    socket_event: _containers.RepeatedCompositeFieldContainer[SocketEvent]
    bytes_read: int
    bytes_written: int
    def __init__(self, id: _Optional[int] = ..., endpoint_id: _Optional[int] = ..., channel_auth_type: _Optional[_Union[ChannelAuth, str]] = ..., socket_event: _Optional[_Iterable[_Union[SocketEvent, _Mapping]]] = ..., bytes_read: _Optional[int] = ..., bytes_written: _Optional[int] = ...) -> None: ...

class Log(_message.Message):
    __slots__ = ("aggregated_socket_event", "num_evicted_aggregated_socket_events", "num_evicted_socket_events")
    AGGREGATED_SOCKET_EVENT_FIELD_NUMBER: _ClassVar[int]
    NUM_EVICTED_AGGREGATED_SOCKET_EVENTS_FIELD_NUMBER: _ClassVar[int]
    NUM_EVICTED_SOCKET_EVENTS_FIELD_NUMBER: _ClassVar[int]
    aggregated_socket_event: _containers.RepeatedCompositeFieldContainer[AggregatedSocketEvent]
    num_evicted_aggregated_socket_events: int
    num_evicted_socket_events: int
    def __init__(self, aggregated_socket_event: _Optional[_Iterable[_Union[AggregatedSocketEvent, _Mapping]]] = ..., num_evicted_aggregated_socket_events: _Optional[int] = ..., num_evicted_socket_events: _Optional[int] = ...) -> None: ...
