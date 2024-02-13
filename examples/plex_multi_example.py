"""
Examples of the Plex controller playing on a Chromecast.

DEMO TYPES:
  * simple: Picks the first item it finds in your libray and plays it.
  * list: Creates a list of items from your library and plays them.
  * playqueue: Creates a playqueue and plays it.
  * playlist: Creates a playlist, plays it, then deletes it.

All demos with the exception of 'simple' can use startItem.
startItem lets you start playback anywhere in the list of items.
turning this option on will pick an item in the middle of the list to start from.

This demo uses features that require the latest Python-PlexAPI
pip install plexapi

"""

# pylint: disable=invalid-name
from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from plexapi.server import PlexServer  # type: ignore[import-untyped]
import zeroconf

import pychromecast
from pychromecast.controllers.plex import PlexController


# Change to the friendly name of your Chromecast.
CAST_NAME = "Office TV"

# Replace with your own Plex URL, including port.
PLEX_URL = "http://192.168.1.3:32400"

# Replace with your Plex token. See link below on how to find it:
# https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/
PLEX_TOKEN = "Y0urT0k3nH3rE"

# Library of items to pick from for tests. Use "episode", "movie", or "track".
PLEX_LIBRARY = "episode"

# The demo type you'd like to run.
# Options are "single", "list", "playqueue", or "playlist"
DEMO_TYPE = "playqueue"

# If demo type is anything other than "single",
# make this True to see a demo of startItem.
START_ITEM = True

parser = argparse.ArgumentParser(
    description="How to play media items, lists, playQueues, "
    "and playlists to a Chromecast device."
)
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s").', default=CAST_NAME
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
parser.add_argument(
    "--url", help='URL of your Plex Server (default: "%(default)s").', default=PLEX_URL
)
parser.add_argument(
    "--library",
    help="The library you'd like to test: episode, movie, or track (default: '%(default)s').",
    default=PLEX_LIBRARY,
)
parser.add_argument("--token", help="Your Plex token.", default=PLEX_TOKEN)
parser.add_argument(
    "--demo",
    help="The demo you'd like to run: single, list, playqueue, or playlist (default: '%(default)s').",
    default=DEMO_TYPE,
)
parser.add_argument(
    "--startitem",
    help="If demo type is anything other than 'single', set to True to see a demo of startItem (default: '%(default)s').",
    default=START_ITEM,
)

args = parser.parse_args()
if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)
startItem = None


def media_info(_cast: pychromecast.Chromecast, _media: Any, items: Any) -> None:
    """Print media info."""
    print(f"Cast Device: {_cast.name}")
    print(f"Media Type: {type(_media)}")
    print(f"Media Items: {items}")


def start_item_info(_media: Any) -> None:
    """Print item info."""
    if args.startitem:
        print(f"Starting From: {_media}")


chromecasts, browser = pychromecast.get_listed_chromecasts(
    friendly_names=[args.cast], known_hosts=args.known_host
)
cast = next((cc for cc in chromecasts if cc.name == args.cast), None)

if not cast:
    print(f"No chromecast with name '{args.cast}' found.")
    foundCasts = ", ".join(
        [cc.name or "<unknown>" for cc in pychromecast.get_chromecasts()[0]]
    )
    print(f"Chromecasts found: {foundCasts}")
    sys.exit(1)

plex_server = PlexServer(args.url, args.token)

# Create a list of 5 items from the selected library.
libraryItems = plex_server.library.search(
    libtype=args.library, sort="addedAt:desc", limit=5
)

if args.demo == "single":
    # Use a single item as media.
    media = libraryItems[0]
    media_info(cast, media, libraryItems[0])
elif args.demo == "list":
    # Use the unaltered list as media.
    media = libraryItems
    # Set starting position to the 2nd item if startItem demo.
    startItem = libraryItems[1] if args.startitem else None
    # Print info
    media_info(cast, libraryItems, libraryItems)
    start_item_info(libraryItems[1])
elif args.demo == "playqueue":
    # Convert list into a playqueue for media.
    media = plex_server.createPlayQueue(libraryItems)
    # Set starting position to the 3rd item if startItem demo.
    startItem = libraryItems[2] if args.startitem else None
    # Print info
    media_info(cast, media, media.items)
    start_item_info(libraryItems[2])
elif args.demo == "playlist":
    # Convert list into a playlist for media.
    media = plex_server.createPlaylist("pychromecast test playlist", libraryItems)
    # Set starting position to the 4th item if startItem demo.
    startItem = libraryItems[3] if args.startitem else None
    # Print info
    media_info(cast, media, media.items())
    start_item_info(libraryItems[2])

plex_c = PlexController()
cast.register_handler(plex_c)
cast.wait()

# Plays the media item, list, playlist, or playqueue.
# If startItem = None it is ignored and playback starts at first item,
# otherwise playback starts at the position of the media item given.
plex_c.block_until_playing(media, startItem=startItem)

if getattr(media, "TYPE", None) == "playlist":
    media.delete()

# Shut down discovery
browser.stop_discovery()
