"""
Example that shows how the socket client can be used without its own worker
thread by not calling Chromecast.start() or Chromecast.wait(), but instead calling
Chromecast.connect() and use asyncio as main loop.
"""
import argparse
import logging
import select
import time
import asyncio

import pychromecast

CAST_NAME = "Living Room"

"""
Check for cast.socket_client.get_socket() and
handle it with cast.socket_client.run_once()
"""

loop = asyncio.get_event_loop()

async def startChromecast():

    cc = None
    socketInLoop = 0
    checkConnectionTask = None

    def ccRunOnce():
        cc.socket_client.run_once()

    async def checkConnection():
        nonlocal socketInLoop
        while True:
            try:
                ccRunOnce()
                if socketInLoop != cc.socket_client.get_socket() and cc.socket_client.is_connected:
                    # update socket after reconnect
                    socketInLoop = cc.socket_client.get_socket()
                    loop.add_reader(socketInLoop, ccRunOnce)
                socketInLoop = cc.socket_client.get_socket()
                loop.add_reader(socketInLoop, ccRunOnce)
            except Exception as e:
                print("ERROR: run_once: " + str(e))
            await asyncio.sleep(2)

    async def connectChromecast():
        nonlocal checkConnectionTask
        cc.connect()
        checkConnectionTask = loop.create_task(checkConnection())

    def castFound(chromecast):
        if chromecast.name == CAST_NAME:
            print("=> Discovered cast " + CAST_NAME)
            nonlocal cc
            cc = chromecast
            loop.create_task(connectChromecast())
            # stop the discovery of pychromecast
            pychromecast.stop_discovery(browser)

    browser = pychromecast.get_chromecasts(blocking=False, tries=1, retry_wait=0.1, timeout=0.1, callback=castFound)

    while True:
        if cc is not None and cc.socket_client.is_connected:
            print("=> Start BigBuckBunny")
            cc.play_media(
                (
                    "http://commondatastorage.googleapis.com/gtv-videos-bucket/"
                    "sample/BigBuckBunny.mp4"
                ),
                "video/mp4",
            )

            await asyncio.sleep(30)
            print("=> Pause")
            cc.media_controller.pause()
            await asyncio.sleep(5)
            print("=> Play")
            cc.media_controller.play()
            await asyncio.sleep(5)
            print("=> Stop")
            cc.media_controller.stop()
            print("=> Quit App")
            cc.quit_app()

            # stop the checkConnectionTask before we close asyncio
            checkConnectionTask.cancel()
            return
        else:
            await asyncio.sleep(1)


parser = argparse.ArgumentParser(
    description="Example on how to use the Media Controller to play an URL."
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)


try:
    asyncio.get_event_loop().run_until_complete(startChromecast())
except KeyboardInterrupt:
    pass
finally:
    loop.close()
