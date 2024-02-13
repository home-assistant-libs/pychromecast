"""
Errors to be used by PyChromecast.
"""


class PyChromecastError(Exception):
    """Base error for PyChromecast."""


class ChromecastConnectionError(PyChromecastError):
    """When a connection error occurs within PyChromecast."""


class PyChromecastStopped(PyChromecastError):
    """Raised when a command is invoked while the Chromecast's socket_client
    is stopped.

    """


class NotConnected(PyChromecastError):
    """
    Raised when a command is invoked while not connected to a Chromecast.
    """


class UnsupportedNamespace(PyChromecastError):
    """
    Raised when trying to send a message with a namespace that is not
    supported by the current running app.
    """


class ControllerNotRegistered(PyChromecastError):
    """
    Raised when trying to interact with a controller while it is
    not registered with a ChromeCast object.
    """


class RequestFailed(PyChromecastError):
    """Raised when a request failed to complete."""

    MSG = "Failed to execute {request}."

    def __init__(self, request: str) -> None:
        super().__init__(self.MSG.format(request=request))


class RequestTimeout(PyChromecastError):
    """Raised when a request timed out."""

    MSG = "Execution of {request} timed out after {timeout} s."

    def __init__(self, request: str, timeout: float) -> None:
        super().__init__(self.MSG.format(request=request, timeout=timeout))


class ZeroConfInstanceRequired(PyChromecastError):
    """Raised when a zeroconf instance is required."""
