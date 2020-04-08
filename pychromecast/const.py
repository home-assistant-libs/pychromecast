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
    "google cast group": CAST_TYPE_GROUP,
}

CAST_MANUFACTURERS = {
    "chromecast": MF_GOOGLE,
    "eureka dongle": MF_GOOGLE,
    "chromecast audio": MF_GOOGLE,
    "google home": MF_GOOGLE,
    "google home mini": MF_GOOGLE,
}

