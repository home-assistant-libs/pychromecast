"""
Example on how to use the Shaka Controller to play an URL.


"""

# pylint: disable=invalid-name

import argparse
import sys
from time import sleep

import pychromecast
from pychromecast import quick_play

from .common import add_log_arguments, configure_logging

# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")


# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room"

# Change to an audio or video url
# Sample DRM request from https://reference.dashif.org/dash.js/latest/samples/drm/clearkey.html
MEDIA_URL = "https://media.axprod.net/TestVectors/v7-MultiDRM-SingleKey/Manifest_1080p_ClearKey.mpd"

parser = argparse.ArgumentParser(
    description="Example on how to use the Shaka Controller to play an URL with DRM."
)
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
parser.add_argument(
    "--known-host",
    help="Add known host (IP), can be used multiple times",
    action="append",
)
add_log_arguments(parser)
parser.add_argument(
    "--url", help='Media url (default: "%(default)s")', default=MEDIA_URL
)
args = parser.parse_args()

configure_logging(args)

chromecasts, browser = pychromecast.get_listed_chromecasts(
    friendly_names=[args.cast], known_hosts=args.known_host
)
if not chromecasts:
    print(f'No chromecast with name "{args.cast}" discovered')
    sys.exit(1)

cast = list(chromecasts)[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()
print(f'Found chromecast with name "{args.cast}", attempting to play "{args.url}"')

# Take customData from shaka player appData object sent in init message to chromecast
app_name = "shaka"
app_data = {
    "media_id": args.url,
    "media_type": "",
    "stream_type": "LIVE",
    "media_info": {
        "customData": {
            "asset": {
                "name": "Custom DRM Video",
                "shortName": "",
                "iconUri": "",
                "manifestUri": "https://media.axprod.net/TestVectors/v7-MultiDRM-SingleKey/Manifest_1080p_ClearKey.mpd",
                "source": "Custom",
                "focus": False,
                "disabled": False,
                "extraText": [],
                "extraThumbnail": [],
                "certificateUri": None,
                "description": None,
                "isFeatured": False,
                "drm": ["No DRM protection"],
                "features": ["VOD"],
                "licenseServers": {"__type__": "map"},
                "licenseRequestHeaders": {"__type__": "map"},
                "requestFilter": None,
                "responseFilter": None,
                "clearKeys": {"__type__": "map"},
                "extraConfig": {
                    "drm": {
                        "clearKeys": {
                            "nrQFDeRLSAKTLifXUIPiZg": "FmY0xnWCPCNaSpRG-tUuTQ"
                        }
                    }
                },
                "adTagUri": None,
                "imaVideoId": None,
                "imaAssetKey": None,
                "imaContentSrcId": None,
                "imaManifestType": None,
                "mediaTailorUrl": None,
                "mediaTailorAdsParams": None,
                "mimeType": None,
                "mediaPlaylistFullMimeType": None,
                "storedProgress": 1,
                "storedContent": None,
            }
        }
    },
}

quick_play.quick_play(cast, app_name, app_data)

sleep(10)

browser.stop_discovery()
