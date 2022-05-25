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
    "chromecast audio": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "chromecast": (CAST_TYPE_CHROMECAST, MF_GOOGLE),
    "eureka dongle": (CAST_TYPE_CHROMECAST, MF_GOOGLE),
    "google cast group": (CAST_TYPE_GROUP, MF_GOOGLE),
    "google home mini": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "google home": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "google nest hub": (CAST_TYPE_CHROMECAST, MF_GOOGLE),
    "google nest hub max": (CAST_TYPE_CHROMECAST, MF_GOOGLE),
    "google nest mini": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "lenovocd-24502f": (CAST_TYPE_AUDIO, "LENOVO"),
    "mitv-mssp2": (CAST_TYPE_CHROMECAST, "Xiaomi"),
    "nest audio": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "nest wifi point": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "shield android tv": (CAST_TYPE_CHROMECAST, "NVIDIA"),
}

SERVICE_TYPE_HOST = "host"
SERVICE_TYPE_MDNS = "mdns"

MESSAGE_TYPE = "type"
REQUEST_ID = "requestId"
SESSION_ID = "sessionId"
