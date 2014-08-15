"""
Commands that can be sent of Chrome Remote Debugging interface.
Only works if Chromecast device is in developer mode. See
https://developer.chrome.com/devtools/docs/debugger-protocol
"""

import requests
import json
from ws4py.client.threadedclient import WebSocketClient

FORMAT_DEBUG_URL = 'http://{}:9222/json'

#command for FrameID 0, seems to operate on current visible frame
FORMAT_COMMAND = '{{"id":0, "method":"Page.navigate", "params":{{"url":"{}"}}}}'

def crd_open_url(host, url):
    """ Opens URL (developer mode only)

        If your Chromecast device is whitelisted, make 
        embedded browser navigate to url."""
    try:
        # ask Chrome debugger interface for api endpoint
        resp = requests.get(FORMAT_DEBUG_URL.format(host))
    except requests.exceptions.ConnectionError: 
        return False

    payload = json.loads(resp.text)
    wsurl = payload[0]['webSocketDebuggerUrl']

    # format and send api navigate command to the endpoint
    debugcom = FORMAT_COMMAND.format(url)
    ws = WebSocketClient(wsurl)
    ws.connect()
    ws.send(debugcom)
    ws.close()

    return True


