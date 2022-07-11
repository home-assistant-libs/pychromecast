"""
Example on how to use the DRTV Controller for the Danish Broadcasting Corporation, dr.dk
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
from time import sleep

import zeroconf
import pychromecast
from pychromecast import quick_play

# Change to the name of your Chromecast
CAST_NAME = "Stuen"

# Media ID can be found in the URLs, e.g. "https://www.dr.dk/drtv/episode/fantus-og-maskinerne_-gravemaskine_278087"
MEDIA_ID = "278087"
IS_LIVE = False

parser = argparse.ArgumentParser(
    description="Example on how to use the BBC iPlayer Controller to play an media stream."
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
parser.add_argument(
    "--media_id", help='MediaID (default: "%(default)s")', default=MEDIA_ID
)
parser.add_argument(
    "--no-autoplay",
    help="Disable autoplay",
    action="store_false",
    default=True,
)
parser.add_argument(
    "--dr_tokens",
    help='DR session tokens, from local storage in a browser: localStorage[\'session.tokens\']; token expiry does not seem to matter. If not given automatic retrieval of an anonymous token will be attempted.',
    default=None,
)
parser.add_argument(
    "--is_live",
    help="Show 'live' and no current/end timestamps on UI",
    action="store_true",
    default=IS_LIVE,
)
parser.add_argument(
    "--chainplay_countdown", help='seconds to countdown before the next media in the chain (typically next episode) is played. -1 to disable (default: %(default)s)', default=10
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)

chromecasts, browser = pychromecast.get_listed_chromecasts(
    friendly_names=[args.cast], known_hosts=args.known_host
)
if not chromecasts:
    print(f'No chromecast with name "{args.cast}" discovered')
    sys.exit(1)

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()
print(f'Found chromecast with name "{args.cast}", attempting to play "{args.media_id}"')

if not args.dr_tokens:
    print("Trying to automatically retrieve a token from the webplayer. Requires Selenium with Chrome support.")
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.headless = True

    driver = webdriver.Chrome(options=options)
    try:
        url = 'http://dr.dk/tv/'
        driver.get(url)

        for _ in range(20):
            script_get_token = """return localStorage['session.tokens']"""
            result = driver.execute_script(script_get_token)
            if result:
                args.dr_tokens = result
                break
            sleep(1)

        if not args.dr_tokens:
            raise Exception("Failed in retrieving DR token automatically")
    finally:
        driver.quit()

app_name = "drtv"
app_data = {
    "media_id": args.media_id,
    "is_live": args.is_live,
    "dr_tokens": args.dr_tokens,
    "autoplay": args.no_autoplay,
    "chainplay_countdown": args.chainplay_countdown,
}
quick_play.quick_play(cast, app_name, app_data)

sleep(10)

browser.stop_discovery()
