"""
Example on how to use the Yle Areena Controller

"""

import re
import pychromecast
import argparse
from pychromecast.controllers.yleareena import YleAreenaController

import logging
logger = logging.getLogger(__name__)


# Change to the name of your Chromecast
CAST_NAME = "My Chromecast"

parser = argparse.ArgumentParser(
    description="Example on how to use the Yle Areena Controller.")
parser.add_argument('--show-debug', help='Enable debug log',
                    action='store_true')
parser.add_argument('--cast',
                    help='Name of cast device (default: "%(default)s")',
                    default=CAST_NAME)
parser.add_argument('--program', help='Areena Program ID',
                    default="1-50097921")
parser.add_argument('--audio_language', help='audio_language',
                    default="")
parser.add_argument('--text_language', help='text_language',
                    default="off")
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)


def get_entry_id(program_id):
    from requests_html import HTMLSession
    session = HTMLSession()
    response = session.get('https://areena.yle.fi/{}'.format(program_id))
    response.html.render()

    entry_id = None
    for div in response.html.find('div'):
        if div.attrs.get('id', '').startswith('yle-kaltura-player'):
            entry_id = re.sub(r'yle-kaltura-player\d+-\d+-', '', div.attrs['id'])
            break

    return entry_id


chromecasts = pychromecast.get_chromecasts()
cast = next(cc for cc in chromecasts if cc.device.friendly_name == args.cast)
cast.wait()
yt = YleAreenaController()
cast.register_handler(yt)
yt.play_media(entry_id=get_entry_id(args.program), audio_language=args.audio_language, text_language=args.text_language)
