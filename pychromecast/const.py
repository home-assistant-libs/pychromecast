"""
Chromecast constants
"""
# Regular chromecast, supports video/audio
CAST_TYPE_CHROMECAST = "cast"
# Cast Audio device, supports only audio
CAST_TYPE_AUDIO = "audio"
# Cast Audio group device, supports only audio
CAST_TYPE_GROUP = "group"

MF_GOOGLE = "Google Inc."

CAST_TYPES = {
    "chromecast": CAST_TYPE_CHROMECAST,
    "eureka dongle": CAST_TYPE_CHROMECAST,
    "chromecast audio": CAST_TYPE_AUDIO,
    "google home": CAST_TYPE_AUDIO,
    "google home mini": CAST_TYPE_AUDIO,
    "google nest mini": CAST_TYPE_AUDIO,
    "nest audio": CAST_TYPE_AUDIO,
    "google cast group": CAST_TYPE_GROUP,
}

# Known models not manufactured by Google
CAST_MANUFACTURERS = {}

SERVICE_TYPE_HOST = "host"
SERVICE_TYPE_MDNS = "mdns"

MESSAGE_TYPE = "type"
REQUEST_ID = "requestId"
SESSION_ID = "sessionId"
