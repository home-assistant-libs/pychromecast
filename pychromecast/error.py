"""
Errors to be used by PyChromecast.
"""


TYPE_LOAD_FAILED = "LOAD_FAILED"
TYPE_LOAD_CANCELLED = "LOAD_CANCELLED"


# pylint: disable=super-init-not-called
class PyChromecastError(Exception):
    """ Base error for PyChromecast. """
    pass


class NoChromecastFoundError(PyChromecastError):
    """
    When a command has to auto-discover a Chromecast and cannot find one.
    """
    pass


class MultipleChromecastsFoundError(PyChromecastError):
    """
    When getting a singular chromecast results in getting multiple chromecasts.
    """
    pass


class ChromecastConnectionError(PyChromecastError):
    """ When a connection error occurs within PyChromecast. """
    pass


class LaunchError(PyChromecastError):
    """ When an app fails to launch. """
    pass


class PyChromecastStopped(PyChromecastError):
    """ Raised when a command is invoked while the Chromecast's socket_client
    is stopped.

    """
    pass


class NotConnected(PyChromecastError):
    """
    Raised when a command is invoked while not connected to a Chromecast.
    """
    pass


class UnsupportedNamespace(PyChromecastError):
    """
    Raised when trying to send a message with a namespace that is not
    supported by the current running app.
    """
    pass


class ControllerNotRegistered(PyChromecastError):
    """
    Raised when trying to interact with a controller while it is
    not registered with a ChromeCast object.
    """
    pass


class MediaLoadError(PyChromecastError):
    """
    Raised when a media load fails on the receiver side i.e. the Chromecast.

    :param media: Either the title or the url of the media that failed to load.
    :type media: str
    :param error: The parsed error message.
    :type error: :class:`controllers.media.MediaError`.

    :ivar media: Either the title or the url of the media that failed to load.
    :vartype media: str
    :ivar request_id: ID of the request that generated this error.
    :vartype request_id: int
    :ivar reason: None; Load Error messages do not have a 'reason' attribute.
    :vartype reason: None
    :ivar custom_data: App specific dict of data defined by the receiver app,
         if any, otherwise None.
    :vartype custom_data: dict or None
    :ivar load_failed: True if the load error type is TYPE_LOAD_FAILED, which
        indicates a number of possibilities, such as network issue or
        unsupported media.
    :vartype load_failed: bool
    :ivar load_cancelled: True if the load error type is TYPE_LOAD_CANCELLED,
        which means the load request was replaced by another.
    :vartype load_cancelled: bool
    """

    def __init__(self, media, error):
        self.media = media

        self.request_id = error.request_id
        self.reason = error.reason
        self.custom_data = error.custom_data

        self.load_failed = False
        self.load_cancelled = False

        if error.type == TYPE_LOAD_FAILED:
            self.load_failed = True
        elif error.type == TYPE_LOAD_CANCELLED:
            self.load_cancelled = True

    def __str__(self):
        return ("There was an error loading the media: '%s' on the Chromecast."
                % self.media)
