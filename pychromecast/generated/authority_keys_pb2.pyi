from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AuthorityKeys(_message.Message):
    __slots__ = ("keys",)
    class Key(_message.Message):
        __slots__ = ("fingerprint", "public_key")
        FINGERPRINT_FIELD_NUMBER: _ClassVar[int]
        PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
        fingerprint: bytes
        public_key: bytes
        def __init__(self, fingerprint: _Optional[bytes] = ..., public_key: _Optional[bytes] = ...) -> None: ...
    KEYS_FIELD_NUMBER: _ClassVar[int]
    keys: _containers.RepeatedCompositeFieldContainer[AuthorityKeys.Key]
    def __init__(self, keys: _Optional[_Iterable[_Union[AuthorityKeys.Key, _Mapping]]] = ...) -> None: ...
