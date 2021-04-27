"""
Example on how to use the Yle Areena Controller

"""
# pylint: disable=invalid-name, import-outside-toplevel

import argparse
import logging
import sys
from time import sleep
import zeroconf

import pychromecast
from pychromecast.controllers.yleareena import YleAreenaController

logger = logging.getLogger(__name__)


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
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument("--program", help="Areena Program ID", default="1-50097921")
parser.add_argument("--audio_language", help="audio_language", default="")
parser.add_argument("--text_language", help="text_language", default="off")
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)


def get_kaltura_id(program_id):
    """
    Dive into the yledl internals and fetch the kaltura player id.
    This can be used with Chromecast
    """
    # yledl is not available in CI, silence import warnings
    from yledl.streamfilters import StreamFilters  # pylint: disable=import-error
    from yledl.http import HttpClient  # pylint: disable=import-error
    from yledl.localization import TranslationChooser  # pylint: disable=import-error
    from yledl.extractors import extractor_factory  # pylint: disable=import-error
    from yledl.titleformatter import TitleFormatter  # pylint: disable=import-error

    title_formatter = TitleFormatter()
    language_chooser = TranslationChooser("fin")
    httpclient = HttpClient(None)
    stream_filters = StreamFilters()

    url = "https://areena.yle.fi/{}".format(program_id)

    extractor = extractor_factory(url, stream_filters, language_chooser, httpclient)
    pid = extractor.program_id_from_url(url)

    info = extractor.program_info_for_pid(pid, url, title_formatter, None)

    return info.media_id.split("-")[-1]


chromecasts, browser = pychromecast.get_listed_chromecasts(
    friendly_names=[args.cast], known_hosts=args.known_host
)
if not chromecasts:
    print('No chromecast with name "{}" discovered'.format(args.cast))
    sys.exit(1)

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()

yt = YleAreenaController()
cast.register_handler(yt)
yt.play_areena_media(
    get_kaltura_id(args.program),
    audio_language=args.audio_language,
    text_language=args.text_language,
)
sleep(10)

# Shut down discovery
browser.stop_discovery()
