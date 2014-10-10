"""
Provides controllers to handle specific namespaces in Chromecast communication.
"""
import logging

from ..error import NotConnected


class BaseController(object):
    """ ABC for namespace controllers. """

    def __init__(self, namespace, target_platform=False):
        self.namespace = namespace
        self.target_platform = target_platform

        self._socket_client = None
        self._message_func = None

        self.logger = logging.getLogger(__name__)

    def registered(self, socket_client):
        """ Called when a controller is registered. """
        self._socket_client = socket_client

        if self.target_platform:
            self._message_func = self._socket_client.send_platform_message
        else:
            self._message_func = self._socket_client.send_app_message

    def channel_connected(self):
        """ Called when a channel has been openend that supports the
            namespace of this controller. """
        pass

    def send_message(self, data, inc_session_id=False,
                     wait_for_response=False):
        """
        Send a message on this namespace to the Chromecast.

        Will raise a NotConnected exception if not connected.
        """
        if self._socket_client is None:
            raise NotConnected()

        self._message_func(
            self.namespace, data, inc_session_id, wait_for_response)

    # pylint: disable=unused-argument,no-self-use
    def receive_message(self, message, data):
        """
        Called when a message is received that matches the namespace.
        Returns boolean indicating if message was handled.
        """
        return False

    def tear_down(self):
        """ Called when we are shutting down. """
        self._socket_client = None
