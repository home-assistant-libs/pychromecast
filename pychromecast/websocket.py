"""
Implements the WEBSOCKET protocol to communicate with the Chromecast.
"""
# pylint: disable=invalid-name

import threading
import datetime as dt
import json
import logging

import requests

from twisted.internet import reactor

from autobahn.twisted.websocket import (WebSocketClientProtocol,
                                        WebSocketClientFactory,
                                        connectWS)

from . import error

_DEBUG = False

RAMP_ENABLED = ['HBO_App',
                '18a8aeaa-8e3d-4c24-b05d-da68394a3476_1',
                'aa35235e-a960-4402-a87e-807ae8b2ac79',
                '06ee44ee-e7e3-4249-83b6-f5d0b6f07f34',
                'YouTube',
                'GoogleMusic',
                '06ee44ee-e7e3-4249-83b6-f5d0b6f07f34_1',
                'edaded98-5119-4c8a-afc1-de722da03562',
                '1812335e-441c-4e1e-a61a-312ca1ead90e',
                'Hulu_Plus',
                'Post_TV_App',
                'PlayMovies',
                'Songza_App',
                'Revision3_App']

PROTOCOL_RAMP = "ramp"
PROTOCOL_COMMAND = "cm"

COMMAND_ATTR_TYPE = "type"
COMMAND_TYPE_PING = "ping"
COMMAND_TYPE_PONG = "pong"

RAMP_ATTR_TYPE = "type"
RAMP_ATTR_CMD_ID = "cmd_id"
RAMP_ATTR_TITLE = "title"
RAMP_ATTR_SRC = "src"
RAMP_ATTR_AUTOPLAY = "autoplay"
RAMP_ATTR_STATUS = "status"
RAMP_ATTR_CONTENT_INFO = "content_info"
RAMP_ATTR_TIME_PROGRESS = "time_progress"
RAMP_ATTR_VOLUME = "volume"
RAMP_ATTR_POSITION = "position"

RAMP_STATUS_ATTR_ERROR = "error"
RAMP_STATUS_ATTR_CONTENT_ID = "content_id"
RAMP_STATUS_ATTR_TITLE = "title"
RAMP_STATUS_ATTR_CURRENT_TIME = "current_time"
RAMP_STATUS_ATTR_DURATION = "duration"
RAMP_STATUS_ATTR_IMAGE_URL = "image_url"
RAMP_STATUS_ATTR_VOLUME = "volume"
RAMP_STATUS_ATTR_MUTED = "muted"
RAMP_STATUS_ATTR_STATE = "state"
RAMP_STATUS_CONTENT_INFO_ATTR_ALBUM_TITLE = "album_title"
RAMP_STATUS_CONTENT_INFO_ATTR_ARTIST = "artist"
RAMP_STATUS_ERROR_ATTR_CODE = "code"
RAMP_STATUS_ERROR_ATTR_DOMAIN = "domain"
RAMP_STATUS_ERROR_ATTR_EVENT_SEQUENCE = "event_sequence"

RAMP_TYPE_PLAY = "PLAY"
RAMP_TYPE_STOP = "STOP"
RAMP_TYPE_LOAD = "LOAD"
RAMP_TYPE_STATUS = "STATUS"
RAMP_TYPE_RESPONSE = "RESPONSE"
RAMP_TYPE_VOLUME = "VOLUME"
RAMP_TYPE_INFO = "INFO"

RAMP_STATE_UNKNOWN = 0
RAMP_STATE_PLAYING = 2
RAMP_STATE_STOPPED = 1

RAMP_VALUE_TRUE = "true"
RAMP_VALUE_FALSE = "false"


def create_websocket_client(app_status):
    """
    Creates and returns a RAMP client based on the supplied app status.
    Will return None if RAMP client is not supported.
    Will raise ValueError if unable to retrieve the websocket url.
    """

    # Check if current app has no service url or no protocols.
    if not app_status.service_url or not app_status.service_protocols:
        return None

    req = requests.post(app_status.service_url,
                        data=bytearray("{}"),
                        headers={"Content-Type": "application/json"})

    if req.status_code != 200:
        raise error.ConnectionError(
            "Could not retrieve websocket url ({}).".format(req.status_code))

    conn_data = json.loads(req.text)

    client = ChromecastWebSocketClient(conn_data['URL'],
                                       app_status.service_protocols)

    # The client is based on Twisted. Make sure twisted is running.
    # If it is running wake Twisted up so it acknowledges our new client.
    if reactor.running:  # pylint: disable=no-member
        reactor.wakeUp()  # pylint: disable=no-member

    else:
        bgthread = threading.Thread(
            target=lambda: reactor.run(installSignalHandlers=False))
        
        bgthread.setDaemon(True)
        bgthread.start()

    return client


# pylint: disable=too-many-public-methods
class ChromecastWebSocketClient(WebSocketClientFactory):
    """ A Client to remote control a Chromecast via the RAMP protocol. """

    def __init__(self, url, supported_protocols):
        WebSocketClientFactory.__init__(self, url)

        self.logger = logging.getLogger(__name__)

        self.handlers = {PROTOCOL_COMMAND: CommandSubprotocol(self)}

        _known_prot = KNOWN_PROTOCOLS

        # Instantiate supported subprotocols.
        for protocol in supported_protocols:
            handler = _known_prot.get(protocol)

            if handler:
                self.handlers[protocol] = handler(self)
            else:
                self.logger.warning(
                    "Unsupported protocol: {}".format(protocol))

        self.client = None
        self.connection = connectWS(self)

    def buildProtocol(self, addr):
        """ Build a new Websocket protocol. """
        proto = ChromecastWebSocketProtocol()
        proto.factory = self  # pylint: disable=attribute-defined-outside-init
        return proto

    def onClientConnected(self, client):
        """ Called when the client gets connected. """
        self.client = client

        for handler in self.handlers.values():
            handler.factory = self

    def onClientDisconnected(self):
        """ Called when the client gets disconnected. """
        self.client.factory = None
        self.client = None

        for handler in self.handlers.values():
            handler.factory = None

    def sendChromecastMessage(self, protocol, data):
        """ Sends a message to the Chromecast. """
        if not self.client:
            raise error.ConnectionError(
                "WebsocketClient is not connected anymore.")

        if _DEBUG:
            self.logger.info("Sending {}".format(data))

        self.client.sendMessage(json.dumps([protocol, data]).encode("utf8"))
        reactor.wakeUp()  # pylint: disable=no-member

    def exit(self):
        """ Quit the client. """
        self.connection.disconnect()

        # Remove circle references
        for handler in self.handlers.values():
            handler.factory = None


# pylint: disable=attribute-defined-outside-init, no-init
class ChromecastWebSocketProtocol(WebSocketClientProtocol):
    """ Implements the RAMP-protocol. """

    def onOpen(self):
        """ When the connection is opened. """
        self.factory.onClientConnected(self)

    def onClose(self, wasClean, code, reason):
        """ When the connection is closed. """
        self.factory.onClientDisconnected()

    def onMessage(self, payload, isBinary):
        """ When a new message is received. """
        # We do not speak binary
        if isBinary:
            return

        try:
            protocol, data = json.loads(payload.decode('utf8'))
        except ValueError:
            # If error while parsing JSON
            logging.getLogger(__name__).exception(
                "Error parsing incoming message: {}".format(
                    payload.decode("utf8")))

            return

        if _DEBUG:
            logging.getLogger(__name__).info("Receiving {}".format(data))

        handler = self.factory.handlers.get(protocol)

        if handler:
            handler.receiveMessage(data)
        else:
            logging.getLogger(__name__).warning(
                "Unknown protocol received: {}, {}".format(protocol, data))


class BaseSubprotocol(object):
    """ Abstract implementation for a subprotocol. """

    def __init__(self, protocol, factory):
        self.protocol = protocol
        self.factory = factory
        self.logger = logging.getLogger(__name__)

    def sendMessage(self, data):
        """ Default handler for sending messages as subprotocol. """
        if self.is_active:
            self.factory.sendChromecastMessage(self.protocol, data)
        else:
            raise error.ConnectionError("Not connected.")

    def receiveMessage(self, data):
        """ Default handler for receiving messages as subprotocol. """
        self.logger.warning(
            "Unhandled {} message: {}".format(self.protocol, data))

    @property
    def is_active(self):
        """ Returns if this subprotocol is active. """
        return self.factory and self.factory.client


class CommandSubprotocol(BaseSubprotocol):
    """ Implements the Command subprotocol. """

    def __init__(self, factory):
        BaseSubprotocol.__init__(self, PROTOCOL_COMMAND, factory)

    def receiveMessage(self, data):
        """ Handles an incoming COMMAND message. """

        if data[COMMAND_ATTR_TYPE] == COMMAND_TYPE_PING:
            self.sendMessage({COMMAND_ATTR_TYPE: COMMAND_TYPE_PONG})
        else:
            BaseSubprotocol.receiveMessage(self, data)


# pylint: disable=too-many-instance-attributes
class RampSubprotocol(BaseSubprotocol):
    """ Implements the Ramp subprotocol. """

    def __init__(self, factory):
        BaseSubprotocol.__init__(self, PROTOCOL_RAMP, factory)

        self.command_id = 0
        self.commands = {}

        self._update_status({})

    def receiveMessage(self, data):
        """ Handles an incoming Ramp message. """
        message_type = data[RAMP_ATTR_TYPE]

        if message_type == RAMP_TYPE_STATUS:
            self._update_status(data[RAMP_ATTR_STATUS])

        elif message_type == RAMP_TYPE_RESPONSE:
            # Match it with the command that we send
            try:
                cmd_type, cmd_event = \
                    self.commands.pop(data[RAMP_ATTR_CMD_ID])

            except KeyError:
                # If CMD_ID did not exist or we do not recognize command
                return

            # Handle response, currently no response handlers
            if cmd_type in (RAMP_TYPE_PLAY, RAMP_TYPE_VOLUME,
                            RAMP_TYPE_INFO):

                self._update_status(data[RAMP_ATTR_STATUS])

            else:
                self.logger.warning(
                    "Unhandled response for command {}: {}".format(
                        cmd_type, data))

            # Alert code that is waiting for this command to get response
            if cmd_event:
                cmd_event.set()

        else:
            BaseSubprotocol.receiveMessage(self, data)

    def sendMessage(self, data, blocking=False):
        """
        Sends a RAMP message.
        Set blocking=True to wait till the Chromecast sends a response
        to the command.
        """
        if not self.is_active:
            raise error.ConnectionError("Not connected.")

        data[RAMP_ATTR_CMD_ID] = self.command_id

        event = threading.Event() if blocking else None

        # Save type to match later with response
        self.commands[self.command_id] = (data[RAMP_ATTR_TYPE], event)

        self.factory.sendChromecastMessage(PROTOCOL_RAMP, data)

        self.command_id += 1

        if blocking:
            event.wait()

    @property
    def is_playing(self):
        """ Property that represents if content is being played. """
        return self.is_active and self.state == RAMP_STATE_PLAYING

    def play(self):
        """ Send the PLAY-command to the RAMP-target. """
        self.sendMessage({RAMP_ATTR_TYPE: RAMP_TYPE_PLAY})

    def pause(self):
        """ Send the PAUSE-command to the RAMP-target. """
        # The STOP command actually pauses the media
        self.sendMessage({RAMP_ATTR_TYPE: RAMP_TYPE_STOP})

    def playpause(self):
        """ Plays if paused, pauses if playing. """
        if self.state == RAMP_STATE_PLAYING:
            self.pause()
        else:
            self.play()

    def seek(self, seconds):
        """ Seek within the content played at RAMP-target. """
        self.sendMessage({RAMP_ATTR_TYPE: RAMP_TYPE_PLAY,
                          RAMP_ATTR_POSITION: seconds})

    def rewind(self):
        """ Rewinds current media item. """
        self.seek(0)

    def next(self):
        """ Skip to the next content at the RAMP-target. """
        if self.duration != 0:
            self.seek(self.duration-.1)

    def set_volume(self, volume):
        """ Set volume at the RAMP-target. """
        # volume is double between 0 and 1
        self.sendMessage({RAMP_ATTR_TYPE: RAMP_TYPE_VOLUME,
                          RAMP_ATTR_VOLUME: volume})

    def refresh(self):
        """ Refresh data at the RAMP-target. """
        self.sendMessage({RAMP_ATTR_TYPE: RAMP_TYPE_INFO})

    def _update_status(self, status):
        """ Updates the RAMP status. """
        con_inf = status.get(RAMP_ATTR_CONTENT_INFO, {})

        self.state = status.get(RAMP_STATUS_ATTR_STATE, 0)
        self.volume = status.get(RAMP_STATUS_ATTR_VOLUME, 1)
        self.muted = status.get(RAMP_STATUS_ATTR_MUTED, False)
        self.content_id = status.get(RAMP_STATUS_ATTR_CONTENT_ID)
        self.title = status.get(RAMP_STATUS_ATTR_TITLE)
        self.artist = con_inf.get(RAMP_STATUS_CONTENT_INFO_ATTR_ARTIST)
        self.album = con_inf.get(RAMP_STATUS_CONTENT_INFO_ATTR_ALBUM_TITLE)
        self._current_time = status.get(RAMP_STATUS_ATTR_CURRENT_TIME, 0)
        self.duration = status.get(RAMP_STATUS_ATTR_DURATION, 0)
        self.image_url = status.get(RAMP_STATUS_ATTR_IMAGE_URL)
        self.time_progress = status.get(RAMP_ATTR_TIME_PROGRESS, False)

        self.last_updated = dt.datetime.now()

    @property
    def current_time(self):
        """ Returns current time of the content. """

        # If time is progressing we have to calculate the current time based on
        # time the status was retrieved and the then current time.
        if self.time_progress:
            timediff = dt.datetime.now() - self.last_updated

            return min(self._current_time + timediff.seconds, self.duration)

        else:
            return self._current_time

    def __repr__(self):
        if self.state == RAMP_STATE_PLAYING:
            state = "playing"
        elif self.state == RAMP_STATE_STOPPED:
            state = "stopped"
        else:
            state = "unknown state"

        if self.title:
            return "RampSubprotocol({}, {}/{}, {})".format(
                self.title.encode("ascii", "replace"),
                self.current_time, self.duration, state)
        else:
            return "RampSubprotocol({})".format(state)


KNOWN_PROTOCOLS = {
    PROTOCOL_COMMAND: CommandSubprotocol,
    PROTOCOL_RAMP: RampSubprotocol,
}
