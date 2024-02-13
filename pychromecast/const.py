"""
Chromecast constants
"""

# Regular chromecast, supports video/audio
CAST_TYPE_CHROMECAST = "cast"
# Cast Audio device, supports only audio
CAST_TYPE_AUDIO = "audio"
# Cast Audio group device, supports only audio
CAST_TYPE_GROUP = "group"

# Default command timeout
REQUEST_TIMEOUT = 10.0

MF_CANTON = "Canton Elektronik GmbH + Co. KG"
MF_GOOGLE = "Google Inc."
MF_JBL = "JBL"
MF_LENOVO = "LENOVO"
MF_LG = "LG"
MF_MARSHALL = "Marshall"
MF_NVIDIA = "NVIDIA"
MF_PHILIPS = "Philips"
MF_PIONEER = "Pioneer"
MF_SONY = "Sony"
MF_SVS = "SVS"
MF_VIZIO = "Vizio"
MF_WNC = "wnc"
MF_XIAOMI = "Xiaomi"

CAST_TYPES = {
    "chromecast audio": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "chromecast": (CAST_TYPE_CHROMECAST, MF_GOOGLE),
    "chromecast hd": (CAST_TYPE_CHROMECAST, MF_GOOGLE),
    "chromecast ultra": (CAST_TYPE_CHROMECAST, MF_GOOGLE),
    "eureka dongle": (CAST_TYPE_CHROMECAST, MF_GOOGLE),
    "google cast group": (CAST_TYPE_GROUP, MF_GOOGLE),
    "google home mini": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "google home": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "google nest hub max": (CAST_TYPE_CHROMECAST, MF_GOOGLE),
    "google nest hub": (CAST_TYPE_CHROMECAST, MF_GOOGLE),
    "google nest mini": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "nest audio": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "nest wifi point": (CAST_TYPE_AUDIO, MF_GOOGLE),
    "bravia 4k vh2": (CAST_TYPE_CHROMECAST, MF_SONY),
    "C4A": (CAST_TYPE_AUDIO, MF_SONY),
    "JBL Link 10": (CAST_TYPE_AUDIO, MF_JBL),
    "JBL Link 20": (CAST_TYPE_AUDIO, MF_JBL),
    "JBL Link 300": (CAST_TYPE_AUDIO, MF_JBL),
    "JBL Link 500": (CAST_TYPE_AUDIO, MF_JBL),
    "lenovocd-24502f": (CAST_TYPE_AUDIO, MF_LENOVO),
    "Lenovo Smart Display 7": (CAST_TYPE_CHROMECAST, MF_LENOVO),
    "LG WK7 ThinQ Speaker": (CAST_TYPE_AUDIO, MF_LG),
    "marshall stanmore ii": (CAST_TYPE_AUDIO, MF_MARSHALL),
    "mitv-mssp2": (CAST_TYPE_CHROMECAST, MF_XIAOMI),
    "Pioneer VSX-831": (CAST_TYPE_AUDIO, MF_PIONEER),
    "Pioneer VSX-1131": (CAST_TYPE_AUDIO, MF_PIONEER),
    "Pioneer VSX-LX305": (CAST_TYPE_AUDIO, MF_PIONEER),
    "shield android tv": (CAST_TYPE_CHROMECAST, MF_NVIDIA),
    "Smart Soundbar 10": (CAST_TYPE_AUDIO, MF_CANTON),
    "Stream TV": (CAST_TYPE_CHROMECAST, MF_WNC),
    "SVS Pro SoundBase": (CAST_TYPE_AUDIO, MF_SVS),
    "TPM191E": (CAST_TYPE_CHROMECAST, MF_PHILIPS),
    "V705-H3": (CAST_TYPE_CHROMECAST, MF_VIZIO),
}


MESSAGE_TYPE = "type"
REQUEST_ID = "requestId"
SESSION_ID = "sessionId"
