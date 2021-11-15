"""
Chromecast types
"""
from collections import namedtuple

CastInfo = namedtuple(
    "CastInfo",
    [
        "services",
        "uuid",
        "model_name",
        "friendly_name",
        "host",
        "port",
        "cast_type",
        "manufacturer",
    ],
)
ServiceInfo = namedtuple("ServiceInfo", ["type", "data"])
