"""Tests for pychromecast.protocol."""

import json

import pytest

from pychromecast.protocol import build_message, frame_message, parse_frames

FIRST = frame_message(build_message("sender-0", "receiver-0", "urn:x-cast:a", {}))
SECOND = frame_message(build_message("sender-0", "receiver-0", "urn:x-cast:b", {}))


def test_build_message() -> None:
    """Test that a message has a JSON payload."""
    msg = build_message("sender-0", "receiver-0", "urn:x-cast:test", {"type": "ä"})
    assert (msg.source_id, msg.destination_id, msg.namespace) == (
        "sender-0",
        "receiver-0",
        "urn:x-cast:test",
    )
    assert json.loads(msg.payload_utf8) == {"type": "ä"}


@pytest.mark.parametrize(
    ("received", "namespaces", "rest"),
    [
        (b"", [], b""),
        (FIRST[:3], [], FIRST[:3]),
        (FIRST[:-1], [], FIRST[:-1]),
        (FIRST, ["urn:x-cast:a"], b""),
        (FIRST + SECOND[:5], ["urn:x-cast:a"], SECOND[:5]),
        (FIRST + SECOND, ["urn:x-cast:a", "urn:x-cast:b"], b""),
    ],
)
def test_parse_frames(received: bytes, namespaces: list[str], rest: bytes) -> None:
    """Test that complete messages are parsed and a partial one is kept."""
    messages, remaining = parse_frames(received)
    assert [msg.namespace for msg in messages] == namespaces
    assert remaining == rest
