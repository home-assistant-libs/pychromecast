"""
The Cast v2 protocol: TLS connections, messages, their framing and the
connection namespace.
"""

import json
import socket
import ssl
from struct import pack, unpack
import time

from .const import MESSAGE_TYPE

# pylint: disable-next=no-name-in-module
from .generated.cast_channel_pb2 import CastMessage

NS_CONNECTION = "urn:x-cast:com.google.cast.tp.connection"

TYPE_CONNECT = "CONNECT"
TYPE_CLOSE = "CLOSE"

SENDER_ID = "sender-0"

# Largest message accepted by recv_message, as in Chromium
MAX_MESSAGE_SIZE = 65536

# Each message is prefixed with its length, a big-endian 4 byte integer
_LENGTH_SIZE = 4


def get_ssl_context() -> ssl.SSLContext:
    """Return a TLS context for cast devices, whose certificates are self-signed."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def open_connection(
    host: str, port: int, timeout: float, context: ssl.SSLContext | None = None
) -> ssl.SSLSocket:
    """Open a TLS connection to a cast device."""
    if context is None:
        context = get_ssl_context()
    raw_socket = socket.create_connection((host, port), timeout)
    try:
        return context.wrap_socket(raw_socket)
    except BaseException:
        raw_socket.close()
        raise


def connect_message() -> dict:
    """Return the payload which opens a virtual connection to a receiver."""
    return {
        MESSAGE_TYPE: TYPE_CONNECT,
        "origin": {},
        "userAgent": "PyChromecast",
        "senderInfo": {
            "sdkType": 2,
            "version": "15.605.1.3",
            "browserVersion": "44.0.2403.30",
            "platform": 4,
            "systemVersion": "Macintosh; Intel Mac OS X10_10_3",
            "connectionType": 1,
        },
    }


def build_message(
    source_id: str, destination_id: str, namespace: str, data: dict
) -> CastMessage:
    """Return a message with a JSON payload."""
    msg = CastMessage()
    msg.protocol_version = msg.CASTV2_1_0
    msg.source_id = source_id
    msg.destination_id = destination_id
    msg.payload_type = CastMessage.STRING
    msg.namespace = namespace
    msg.payload_utf8 = json.dumps(data, ensure_ascii=False)
    return msg


def frame_message(msg: CastMessage) -> bytes:
    """Return a message as sent on the socket."""
    return pack(">I", msg.ByteSize()) + msg.SerializeToString()


def parse_frames(buffer: bytes) -> tuple[list[CastMessage], bytes]:
    """Parse the complete messages at the start of buffer.

    Returns the messages and the rest of the buffer, a partial message.
    """
    messages = []
    while len(buffer) >= _LENGTH_SIZE:
        (size,) = unpack(">I", buffer[:_LENGTH_SIZE])
        end = _LENGTH_SIZE + size
        if len(buffer) < end:
            break
        msg = CastMessage()
        msg.ParseFromString(buffer[_LENGTH_SIZE:end])
        messages.append(msg)
        buffer = buffer[end:]
    return messages, buffer


def _recv_exact(sock: ssl.SSLSocket, size: int, deadline: float) -> bytes:
    """Receive exactly size bytes before the deadline."""
    data = b""
    while len(data) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for the cast device")
        sock.settimeout(remaining)
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("connection closed by the cast device")
        data += chunk
    return data


def recv_message(sock: ssl.SSLSocket, deadline: float) -> CastMessage:
    """Receive one message on a blocking socket before the deadline.

    Raises TimeoutError, ConnectionError if the connection is closed, ValueError
    if the message is larger than MAX_MESSAGE_SIZE and DecodeError if it can't
    be parsed.
    """
    (size,) = unpack(">I", _recv_exact(sock, _LENGTH_SIZE, deadline))
    if size > MAX_MESSAGE_SIZE:
        raise ValueError(f"message of {size} bytes is too large")
    msg = CastMessage()
    msg.ParseFromString(_recv_exact(sock, size, deadline))
    return msg
