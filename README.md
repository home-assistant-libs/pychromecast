pychromecast [![Build Status](https://travis-ci.org/balloob/pychromecast.svg?branch=master)](https://travis-ci.org/balloob/pychromecast)
============

Library for Python 2 and 3 to communicate with the Google Chromecast. It currently supports:
 - Auto discovering connected Chromecasts on the network
 - Start the default media receiver and play any online media
 - Control playback of current playing media
 - Implement Google Chromecast api v2
 - Communicate with apps via channels
 - Easily extendable to add support for unsupported namespaces

*PyChromecast 0.6 introduces some backward incompatible changes due to the migration from DIAL to socket for retrieving the app status.*

Dependencies
------------
PyChromecast depends on the Python packages requests, protobuf and zeroconf. Make sure you have these dependencies installed using `pip install -r requirements.txt`

_Some users running Python 2.7 have [reported](https://github.com/balloob/pychromecast/issues/47#issuecomment-107822162) that they had to upgrade their version of pip using `pip install --upgrade pip` before they were able to install the latest version of the dependencies._

How to use
----------

    >> from __future__ import print_function
    >> import time
    >> import pychromecast

    >> pychromecast.get_chromecasts_as_dict().keys()
    ['Dev', 'Living Room', 'Den', 'Bedroom']

    >> cast = pychromecast.get_chromecast(friendly_name="Living Room")
    >> print(cast.device)
    DeviceStatus(friendly_name='Living Room', model_name='Eureka Dongle', manufacturer='Google Inc.', api_version=(1, 0))

    >> print(cast.status)
    CastStatus(is_active_input=True, is_stand_by=False, volume_level=1.0, volume_muted=False, app_id=u'CC1AD845', display_name=u'Default Media Receiver', namespaces=[u'urn:x-cast:com.google.cast.player.message', u'urn:x-cast:com.google.cast.media'], session_id=u'CCA39713-9A4F-34A6-A8BF-5D97BE7ECA5C', transport_id=u'web-9', status_text='')

    >> mc = cast.media_controller
    >> print(mc.status)
    MediaStatus(current_time=42.458322, content_id=u'http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4', content_type=u'video/mp4', duration=596.474195, stream_type=u'BUFFERED', idle_reason=None, media_session_id=1, playback_rate=1, player_state=u'PLAYING', supported_media_commands=15, volume_level=1, volume_muted=False)

    >> mc.pause()
    >> time.sleep(5)
    >> mc.play()
    >> from pychromecast.controllers.youtube import YouTubeController
    >> yt = YouTubeController()
    >> cast.register_handler(yt)
    >> yt.play_video("L0MK7qz13bU")

Adding support for extra namespaces
-----------------------------------
Each app that runs on the Chromecast supports namespaces. They specify a JSON-based mini-protocol. This is used to communicate between the Chromecast and your phone/browser and now Python.

Support for extra namespaces is added by using controllers. To add your own namespace to a current chromecast instance you will first have to define your controller. Example of a minimal controller:

    from pychromecast.controllers import BaseController

    class MyController(BaseController):
        def __init__(self):
            super(MediaController, self).__init__(
                "urn:x-cast:my.super.awesome.namespace")

        def receive_message(self, message, data):
            print("Wow, I received this message: {}".format(data))

            return True # indicate you handled this message

        def request_beer(self):
            self.send_message({'request': 'beer'})

After you have defined your controller you will have to add an instance to a Chromecast object: `cast.register_handler(MyController())`. When a message is received with your namespace it will be routed to your controller.

For more options see the [BaseController](https://github.com/balloob/pychromecast/blob/master/pychromecast/controllers/__init__.py). For an example of a fully implemented controller see the [MediaController](https://github.com/balloob/pychromecast/blob/master/pychromecast/controllers/media.py).

Exploring existing namespaces
-------------------------------
So you've got PyChromecast running and decided it is time to add support to your favorite app. No worries, the following instructions will have you covered in exploring the possibilities.

The following instructions require the use of the [Google Chrome browser](https://www.google.com/chrome/) and the [Google Cast plugin](https://chrome.google.com/webstore/detail/google-cast/boadgeojelhgndaghljhdicfkmllpafd).

 * In Chrome, go to `chrome://net-internals/#capture`
 * Enable the checkbox 'Include the actual bytes sent/received.'
 * Open a new tab, browse to your favorite application on the web that has Chromecast support and start casting.
 * Go back to the tab that is capturing events and click on stop.
 * From the dropdown click on events. This will show you a table with events that happened while you were recording.
 * In the filter box enter the text `Tr@n$p0rt`. This should give one SOCKET connection as result: the connection with your Chromecast.
 * Go through the results and collect the JSON that is exchanged.
 * Now write a controller that is able to mimic this behavior :-)

Ignoring CEC Data
-----------------
The Chromecast typically reports whether it is the active input on the device
to which it is connected. This value is stored inside a cast object in the
following property.

    cast.status.is_active_input

Some Chromecast users have reported CEC incompatibilities with their media
center devices. These incompatibilities may sometimes cause this active input
value to be reported improperly.

This active input value is typically used to determine if the Chromecast is
idle. PyChromecast is capable of ignoring the active input value when
determining if the Chromecast is idle in the instance that the Chromecast is
returning erroneous values. To ignore this CEC detection data in PyChromecast,
append a [Linux style wildcard](http://tldp.org/LDP/GNU-Linux-Tools-Summary/html/x11655.htm)
formatted string to the IGNORE_CEC list in PyChromecast like in the example
below.

    pychromecast.IGNORE_CEC.append('*')  # Ignore CEC on all devices
    pychromecast.IGNORE_CEC.append('Living Room')  # Ignore CEC on Chromecasts named Living Room

Thanks
------
I would like to thank [Fred Clift](https://github.com/minektur) for laying the socket client ground work. Without him it would not have been possible!
