"""
Example on how to use the Multizone (Audio Group) Controller

"""

import logging
import sys
import time

import pychromecast
from pychromecast.controllers.multizone import MultizoneController
from pychromecast.socket_client import CONNECTION_STATUS_CONNECTED

# Change to the name of your Chromecast
CAST_NAME = "Whole house"

debug = '--show-debug' in sys.argv
if debug:
    logging.basicConfig(level=logging.DEBUG)

class connlistener:
    def __init__(self, mz):
        self._mz=mz

    def new_connection_status(self, connection_status):
        """Handle reception of a new ConnectionStatus."""
        if connection_status.status == 'CONNECTED':
            self._mz.update_members()

class mzlistener:
    def multizone_member_added(self, uuid):
        print("New member: {}".format(uuid))

    def multizone_member_removed(self, uuid):
        print("Removed member: {}".format(uuid))

    def multizone_status_received(self):
        print("Members: {}".format(mz.members))

chromecasts = pychromecast.get_chromecasts(timeout=2)
cast = next(cc for cc in chromecasts if cc.device.friendly_name == CAST_NAME)
mz = MultizoneController(cast.uuid)
mz.register_listener(mzlistener())
cast.register_handler(mz)
cast.register_connection_listener(connlistener(mz))
cast.wait()
while True:
    time.sleep(1)

