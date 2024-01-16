"""Helpers and types related to waiting for a command response."""

from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Protocol

CallbackType = Callable[[bool, dict | None], None]
"""Signature of optional callback functions supported by methods sending messages.

The callback function will be called with a bool indicating if the message was sent
and an optional response dict.
"""


class AcceptsCallbackFunc(Protocol):
    """A function which accepts a callback_function kwarg."""

    def __call__(
        self,
        *,
        callback_function: CallbackType | None = None,
    ):
        ...


class WaitResponse:
    """Wait for a response."""

    msg_sent: bool
    response: dict | None

    def __init__(self, timeout: float) -> None:
        """Initialize."""
        self._event = threading.Event()
        self._timeout = timeout

    def callback(self, msg_sent: bool, response: dict | None) -> None:
        """Called when the request is finished."""
        self.response = response
        self.msg_sent = msg_sent
        self._event.set()

    def wait_response(self) -> bool:
        """Wait for the request to finish."""
        return self._event.wait(self._timeout)


def chain_on_success(
    on_success: AcceptsCallbackFunc, callback_function: CallbackType | None
) -> CallbackType:
    """Helper to chain callbacks."""

    def _callback(msg_sent: bool, response: dict | None) -> None:
        if not msg_sent:
            if callback_function:
                callback_function(msg_sent, response)
            return
        on_success(callback_function=callback_function)

    return _callback
