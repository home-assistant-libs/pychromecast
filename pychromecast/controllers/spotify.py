import logging
import os
import requests

from pychromecast.controllers import BaseController
from ..config import APP_SPOTIFY

logging.basicConfig(level=logging.DEBUG)

APP_NAMESPACE = "urn:x-cast:com.spotify.chromecast.secure.v1"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36"

TYPE_STATUS = "setCredentials"


class SpotifyController(BaseController):
    def __init__(self, username, password, friendly_name):
        super(SpotifyController, self).__init__(
              APP_NAMESPACE, APP_SPOTIFY)

        self.logger = logging.getLogger(__name__)
        self.username = username
        self.password = password
        self.session_started = False
        self.token = None
        self.expiration_date = None

    def receive_message(self, message, data):
        self.logger.debug("Cast message: {}".format(data))
        
        return True

    def _get_csrf(self, session, cookies):
        headers = {'user-agent': USER_AGENT}

        response = session.get("https://accounts.spotify.com/login",
                               headers=headers, cookies=cookies)
        response.raise_for_status()

        return response.cookies['csrf_token']

    def _login(self, session, cookies, username, password, csrf_token):
        headers = {'user-agent': USER_AGENT}

        data = {"remember": False, "username": username, "password": password,
                "csrf_token": csrf_token}

        response = session.post("https://accounts.spotify.com/api/login",
                                data=data, cookies=cookies, headers=headers)

        response.raise_for_status()

    def _get_access_token(self, session, cookies):
        headers = {'user-agent': USER_AGENT}

        response = session.get("https://open.spotify.com/browse",
                               headers=headers, cookies=cookies)
        response.raise_for_status()

        self.token = response.cookies['wp_access_token']

        expiration = response.cookies['wp_expiration']
        self.expiration_date = int(expiration)//1000

        # return response.cookies['wp_access_token']

    def start_session(self):
        # arbitrary value and can be static
        cookies = {"__bon": "MHwwfC01ODc4MjExMzJ8LTI0Njg4NDg3NTQ0fDF8MXwxfDE="}

        if self.username is None:
            username = os.getenv("SPOTIFY_USERNAME")

        if self.password is None:
            password = os.getenv("SPOTIFY_PASS")

        if self.username is None or self.password is None:
            raise("No username or password")

        session = requests.Session()
        token = self. _get_csrf(session, cookies)

        self._login(session, cookies, self.username, self.password, token)
        self._get_access_token(session, cookies)

        self.session_started = True

        return self.token

    def launch_app(self):

        def callback():
            self.send_message({"type": TYPE_STATUS, "credentials": self.token})

        self.start_session()
        self.launch(callback_function=callback)
