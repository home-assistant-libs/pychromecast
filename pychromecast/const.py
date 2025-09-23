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

MF_BOSE = "Bose"
MF_CANTON = "Canton Elektronik GmbH + Co. KG"
MF_GOOGLE = "Google Inc."
MF_HARMAN = "HARMAN International Industries"
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

# Map model names to cast types and manufacturers
# Note: The keys should be in lowercase to ensure case-insensitive matching
# when checking against device names.
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
    "bravia 4k vh21": (CAST_TYPE_CHROMECAST, MF_SONY),
    "bose smart ultra soundbar": (CAST_TYPE_AUDIO, MF_BOSE),
    "c4a": (CAST_TYPE_AUDIO, MF_SONY),
    "jbl link 10": (CAST_TYPE_AUDIO, MF_JBL),
    "jbl link 20": (CAST_TYPE_AUDIO, MF_JBL),
    "jbl link 300": (CAST_TYPE_AUDIO, MF_JBL),
    "jbl link 500": (CAST_TYPE_AUDIO, MF_JBL),
    "jbl link portable": (CAST_TYPE_AUDIO, MF_HARMAN),
    "lenovocd-24502f": (CAST_TYPE_AUDIO, MF_LENOVO),
    "lenovo smart display 7": (CAST_TYPE_CHROMECAST, MF_LENOVO),
    "lenovo smart display 10": (CAST_TYPE_CHROMECAST, MF_LENOVO),
    "lg wk7 thinq speaker": (CAST_TYPE_AUDIO, MF_LG),
    "marshall stanmore ii": (CAST_TYPE_AUDIO, MF_MARSHALL),
    "mitv-mssp2": (CAST_TYPE_CHROMECAST, MF_XIAOMI),
    "pioneer vsx-831": (CAST_TYPE_AUDIO, MF_PIONEER),
    "pioneer vsx-1131": (CAST_TYPE_AUDIO, MF_PIONEER),
    "pioneer vsx-lx305": (CAST_TYPE_AUDIO, MF_PIONEER),
    "shield android tv": (CAST_TYPE_CHROMECAST, MF_NVIDIA),
    "smart soundbar 10": (CAST_TYPE_AUDIO, MF_CANTON),
    "stream tv": (CAST_TYPE_CHROMECAST, MF_WNC),
    "svs pro soundbase": (CAST_TYPE_AUDIO, MF_SVS),
    "tpm191e": (CAST_TYPE_CHROMECAST, MF_PHILIPS),
    "v705-h3": (CAST_TYPE_CHROMECAST, MF_VIZIO),
    "d24f-j09": (CAST_TYPE_CHROMECAST, MF_VIZIO),
}


MESSAGE_TYPE = "type"
REQUEST_ID = "requestId"
SESSION_ID = "sessionId"

PLATFORM_DESTINATION_ID = "receiver-0"
