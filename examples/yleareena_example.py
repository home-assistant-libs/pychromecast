"""
Example on how to use the Yle Areena Controller

"""
# pylint: disable=invalid-name, import-outside-toplevel, too-many-locals

import argparse
import logging
import sys
from time import sleep
import zeroconf

import pychromecast
from pychromecast import quick_play

logger = logging.getLogger(__name__)


# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")

# Change to the name of your Chromecast
CAST_NAME = "My Chromecast"

parser = argparse.ArgumentParser(
    description="Example on how to use the Yle Areena Controller."
)
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
parser.add_argument(
    "--known-host",
    help="Add known host (IP), can be used multiple times",
    action="append",
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--show-discovery-debug", help="Enable discovery debug log", action="store_true"
)
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument("--program", help="Areena Program ID", default="1-50649659")
parser.add_argument("--audio_language", help="audio_language", default="")
parser.add_argument("--text_language", help="text_language", default="off")
args = parser.parse_args()

if args.show_debug:
    fmt = "%(asctime)s %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(format=fmt, datefmt=datefmt, level=logging.DEBUG)
    logging.getLogger("pychromecast.dial").setLevel(logging.INFO)
    logging.getLogger("pychromecast.discovery").setLevel(logging.INFO)
if args.show_discovery_debug:
    logging.getLogger("pychromecast.dial").setLevel(logging.DEBUG)
    logging.getLogger("pychromecast.discovery").setLevel(logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)


def get_kaltura_id(program_id: str) -> str:
    """
    Dive into the yledl internals and fetch the kaltura player id.
    This can be used with Chromecast
    """
    # yledl is not available in CI, silence import warnings
    from yledl.extractors import extractor_factory  # type: ignore[import-untyped]
    from yledl.ffprobe import NullProbe  # type: ignore[import-untyped]
    from yledl.http import HttpClient  # type: ignore[import-untyped]
    from yledl.io import IOContext  # type: ignore[import-untyped]
    from yledl.localization import TranslationChooser  # type: ignore[import-untyped]
    from yledl.titleformatter import TitleFormatter  # type: ignore[import-untyped]

    title_formatter = TitleFormatter()
    language_chooser = TranslationChooser("fin")
    httpclient = HttpClient(IOContext())

    url = f"https://areena.yle.fi/{program_id}"

    ffprobe = NullProbe()
    extractor = extractor_factory(
        url, language_chooser, httpclient, title_formatter, ffprobe
    )
    pid = extractor.program_id_from_url(url)

    info = extractor.program_info_for_pid(pid, url, title_formatter, ffprobe)

    kaltura_id: str = info.media_id.split("-")[-1]
    return kaltura_id


chromecasts, browser = pychromecast.get_listed_chromecasts(
    friendly_names=[args.cast], known_hosts=args.known_host
)
if not chromecasts:
    print(f'No chromecast with name "{args.cast}" discovered')
    sys.exit(1)

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()

app_name = "yleareena"
app_data = {
    "media_id": get_kaltura_id(args.program),
    "audio_lang": args.audio_language,
    "text_lang": args.text_language,
}
quick_play.quick_play(cast, app_name, app_data)
sleep(10)

# Shut down discovery
browser.stop_discovery()
