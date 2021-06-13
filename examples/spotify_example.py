"""
Example on how to use the Spotify Controller.
NOTE: You need to install the spotipy and spotify-token dependencies.

This can be done by running the following:
pip install spotify-token
pip install git+https://github.com/plamere/spotipy.git
"""
# pylint: disable=invalid-name

import argparse
import logging
import time
import sys
import requests

import zeroconf
import spotify_token as st  # pylint: disable=import-error
import spotipy  # pylint: disable=import-error

import pychromecast
from pychromecast.controllers.spotify import SpotifyController

CAST_NAME = "My Chromecast"

parser = argparse.ArgumentParser(
    description="Example on how to use the Spotify Controller."
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
parser.add_argument("--sp-key", help="Spotify cookie", required=True)
parser.add_argument("--sp-dc", help="Spotify cookie", required=True)
parser.add_argument(
    "--uri",
    help='Spotify uri(s) (default: "%(default)s")',
    default=["spotify:track:3Zwu2K0Qa5sT6teCCHPShP"],
    nargs="+",
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
    # Uncomment to enable http.client debug log
    # http_client.HTTPConnection.debuglevel = 1
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)

chromecasts, browser = pychromecast.get_listed_chromecasts(
    friendly_names=[args.cast], known_hosts=args.known_host
)
cast = list(chromecasts)[0]

if not cast:
    print('No chromecast with name "{}" discovered'.format(args.cast))
    print("Discovered casts: {}".format(chromecasts))
    sys.exit(1)

print("cast {}".format(cast))


# Wait for connection to the chromecast
cast.wait()

spotify_device_id = None

# Create a spotify token
data = st.start_session(args.sp_dc, args.sp_key)
access_token = data[0]
expires = data[1] - int(time.time())

# Create a spotify client
client = spotipy.Spotify(auth=access_token)
if args.show_debug:
    spotipy.trace = True
    spotipy.trace_out = True

# Launch the spotify app on the cast we want to cast to
sp = SpotifyController(access_token, expires)
cast.register_handler(sp)
sp.launch_app()

if not sp.is_launched and not sp.credential_error:
    print("Failed to launch spotify controller due to timeout")
    sys.exit(1)
if not sp.is_launched and sp.credential_error:
    print("Failed to launch spotify controller due to credential error")
    sys.exit(1)

# The chromecast device does not show up as part of the public API get devices
# call until it starts playing. The only way to do so is to transfer playback
# by call this endpoint that's not part of their public API.
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": "Bearer " + access_token,
}
transferResponse = requests.post(
    "https://guc-spclient.spotify.com/connect-state/v1/connect/transfer/from/noop/to/"
    + sp.device,
    headers=headers,
)

if transferResponse.status_code is not 200:
    print("Failed to transfer playback to chromecast device")
    sys.exit(1)

# Start playback
if args.uri[0].find("track") > 0:
    client.start_playback(uris=args.uri)
else:
    client.start_playback(context_uri=args.uri[0])

# Shut down discovery
browser.stop_discovery()
