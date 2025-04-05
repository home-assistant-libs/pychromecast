from typing import ClassVar as _ClassVar
from typing import Iterable as _Iterable
from typing import Mapping as _Mapping
from typing import Optional as _Optional
from typing import Union as _Union

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers

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
