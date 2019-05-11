"""
Example on how to use the Spotify Controller.
NOTE: You need to install the spotipy and spotify-token dependencies.

This can be done by running the following:
pip install spotify-token
pip install git+https://github.com/plamere/spotipy.git
"""
import argparse
import http.client as http_client
import logging
import time
import sys

import pychromecast
from pychromecast.controllers.multizone import MultizoneController
from pychromecast.controllers.spotify import SpotifyController
import spotify_token as st
import spotipy

CAST_NAME = "My Chromecast"

parser = argparse.ArgumentParser(
    description="Example on how to use the Spotify Controller.")
parser.add_argument('--show-debug', help='Enable debug log',
                    action='store_true')
parser.add_argument('--cast',
                    help='Name of cast device (default: "%(default)s")',
                    default=CAST_NAME)
parser.add_argument('--user', help='Spotify username', required=True)
parser.add_argument('--password', help='Spotify password', required=True)
parser.add_argument('--track', help='Spotify uri (default: "%(default)s")',
                    default="spotify:track:3Zwu2K0Qa5sT6teCCHPShP")
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
    # Uncomment to enable http.client debug log
    #http_client.HTTPConnection.debuglevel = 1

chromecasts = pychromecast.get_chromecasts()
cast = None
for _cast in chromecasts:
    if _cast.name == args.cast:
        cast = _cast
        break

if not cast:
    print('No chromecast with name "{}" discovered'.format(args.cast))
    print('Discovered casts: {}'.format(chromecasts))
    sys.exit(1)

print('cast {}'.format(cast))

class ConnListener:
    def __init__(self, mz):
        self._mz=mz

    def new_connection_status(self, connection_status):
        """Handle reception of a new ConnectionStatus."""
        if connection_status.status == 'CONNECTED':
            self._mz.update_members()

class MzListener:
    def __init__(self):
        self.got_members=False
    
    def multizone_member_added(self, uuid):
        pass

    def multizone_member_removed(self, uuid):
        pass

    def multizone_status_received(self):
        self.got_members=True

mz = None
mz_listener = None

if cast.cast_type=='group':
    # The spotify API will return the name of the group controller device, not 
    # the group we want to cast to. Setup a MultiZone controller to map devices
    # returned by the Spotify API to members of the group we want to cast to.
    mz = MultizoneController(cast.uuid)
    mz_listener = MzListener()
    mz.register_listener(mz_listener)
    cast.register_handler(mz)

    # Register a connection listener, when connected, we can poll group members
    cast.register_connection_listener(ConnListener(mz))
    
# Wait for connection to the chromecast
cast.wait()

device_id = None

# Create a spotify token
data = st.start_session(args.user, args.password)
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

# Query spotify for active devices
devices_available = client.devices()

# If we're not casting to a group
if mz == None:
    # Try to match active spotify devices with the cast we want to cast to
    # Ideally we would match device['id'] with the cast's UUID because there
    # may be multiple casts with the same name. Currently it's not known how to
    # map between the two so match name instead.
    for device in devices_available['devices']:
        if device['name'] == args.cast:
            device_id = device['id']
            break

    if not device_id:
        print('No device with name "{}" known by Spotify'.format(args.cast))
        print('Known devices: {}'.format(devices_available['devices']))
        sys.exit(1)
else:
    # Wait for group members to update
    while not mz_listener.got_members:
        time.sleep(0.1)

    # Look for a chromecast which:
    # - Is known to spotify (matched by bame)
    # - Is a member of the audio group we want to play to
    for device in devices_available['devices']:
        for _cast in chromecasts:
            if str(_cast.uuid) in mz.members and device['name'] == _cast.name:
                device_id = device['id']
                break

    if not device_id:
      print('Could not find matching member of audio group')
      print('Known devices: {}'.format(devices_available['devices']))
      print('Members of group "{}": {}'.format(args.cast, mz.members))
      sys.exit(1)

# Start playback
client.start_playback(device_id=device_id, uris=[args.track])
