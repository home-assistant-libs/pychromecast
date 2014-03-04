"""
Errors to be used by PyChromecast.
"""


class PyChromecastError(Exception):
    """ Base error for PyChromecast. """
    pass


class ConnectionError(PyChromecastError):
    """ When a connection error occurs within PyChromecast. """
    pass
