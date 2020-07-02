pychromecast |Build Status|
===========================

.. |Build Status| image:: https://travis-ci.org/balloob/pychromecast.svg?branch=master
   :target: https://travis-ci.org/balloob/pychromecast

Library for Python 3.6+ to communicate with the Google Chromecast. It
currently supports:

-  Auto discovering connected Chromecasts on the network
-  Start the default media receiver and play any online media
-  Control playback of current playing media
-  Implement Google Chromecast api v2
-  Communicate with apps via channels
-  Easily extendable to add support for unsupported namespaces
-  Multi-room setups with Audio cast devices

*Check out* `Home Assistant <https://home-assistant.io>`_ *for a
ready-made solution using PyChromecast for controlling and automating
your Chromecast or Cast-enabled device like Google Home.*

Dependencies
------------

PyChromecast depends on the Python packages requests, protobuf and
zeroconf. Make sure you have these dependencies installed using
``pip install -r requirements.txt``

How to use
----------

.. code:: python

    >> import time
    >> import pychromecast

    >> # List chromecasts on the network, but don't connect
    >> services, browser = pychromecast.discovery.discover_chromecasts()
    >> # Shut down discovery
    >> pychromecast.discovery.stop_discovery(browser)

    >> # Discover and connect to chromecasts named Living Room
    >> chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=["Living Room"])
    >> [cc.device.friendly_name for cc in chromecasts]
    ['Living Room']

    >> cast = chromecasts[0]
    >> # Start worker thread and wait for cast device to be ready
    >> cast.wait()
    >> print(cast.device)
    DeviceStatus(friendly_name='Living Room', model_name='Chromecast', manufacturer='Google Inc.', uuid=UUID('df6944da-f016-4cb8-97d0-3da2ccaa380b'), cast_type='cast')

    >> print(cast.status)
    CastStatus(is_active_input=True, is_stand_by=False, volume_level=1.0, volume_muted=False, app_id='CC1AD845', display_name='Default Media Receiver', namespaces=['urn:x-cast:com.google.cast.player.message', 'urn:x-cast:com.google.cast.media'], session_id='CCA39713-9A4F-34A6-A8BF-5D97BE7ECA5C', transport_id='web-9', status_text='')

    >> mc = cast.media_controller
    >> mc.play_media('http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4', 'video/mp4')
    >> mc.block_until_active()
    >> print(mc.status)
    MediaStatus(current_time=42.458322, content_id='http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4', content_type='video/mp4', duration=596.474195, stream_type='BUFFERED', idle_reason=None, media_session_id=1, playback_rate=1, player_state='PLAYING', supported_media_commands=15, volume_level=1, volume_muted=False)

    >> mc.pause()
    >> time.sleep(5)
    >> mc.play()

    >> # Shut down discovery
    >> pychromecast.discovery.stop_discovery(browser)

Adding support for extra namespaces
-----------------------------------

Each app that runs on the Chromecast supports namespaces. They specify a
JSON-based mini-protocol. This is used to communicate between the
Chromecast and your phone/browser and now Python.

Support for extra namespaces is added by using controllers. To add your own namespace to a current chromecast instance you will first have to define your controller. Example of a minimal controller:

.. code:: python

    from pychromecast.controllers import BaseController

    class MyController(BaseController):
        def __init__(self):
            super(MyController, self).__init__(
                "urn:x-cast:my.super.awesome.namespace")

        def receive_message(self, message, data):
            print("Wow, I received this message: {}".format(data))

            return True  # indicate you handled this message

        def request_beer(self):
            self.send_message({'request': 'beer'})

After you have defined your controller you will have to add an instance to a Chromecast object: `cast.register_handler(MyController())`. When a message is received with your namespace it will be routed to your controller.

For more options see the `BaseController`_. For an example of a fully implemented controller see the `MediaController`_.

.. _BaseController: https://github.com/balloob/pychromecast/blob/master/pychromecast/controllers/__init__.py
.. _MediaController: https://github.com/balloob/pychromecast/blob/master/pychromecast/controllers/media.py

Exploring existing namespaces
-------------------------------
So you've got PyChromecast running and decided it is time to add support to your favorite app. No worries, the following instructions will have you covered in exploring the possibilities.

The following instructions require the use of the `Google Chrome browser`_ and the `Google Cast plugin`_.

 * In Chrome, go to `chrome://net-export/`
 * Select 'Include raw bytes (will include cookies and credentials)'
 * Click 'Start Logging to Disk'
 * Open a new tab, browse to your favorite application on the web that has Chromecast support and start casting.
 * Go back to the tab that is capturing events and click on stop.
 * Open https://netlog-viewer.appspot.com/ and select your event log file.
 * Browse to https://netlog-viewer.appspot.com/#events&q=type:SOCKET, and find the socket that has familiar JSON data. (For me, it's usually the second or third from the top.)
 * Go through the results and collect the JSON that is exchanged.
 * Now write a controller that is able to mimic this behavior :-)

.. _Google Chrome Browser: https://www.google.com/chrome/
.. _Google Cast Plugin: https://chrome.google.com/webstore/detail/google-cast/boadgeojelhgndaghljhdicfkmllpafd

Ignoring CEC Data
-----------------
The Chromecast typically reports whether it is the active input on the device
to which it is connected. This value is stored inside a cast object in the
following property.

.. code:: python

    cast.status.is_active_input

Some Chromecast users have reported CEC incompatibilities with their media
center devices. These incompatibilities may sometimes cause this active input
value to be reported improperly.

This active input value is typically used to determine if the Chromecast
is idle. PyChromecast is capable of ignoring the active input value when
determining if the Chromecast is idle in the instance that the
Chromecast is returning erroneous values. To ignore this CEC detection
data in PyChromecast, append a `Linux style wildcard`_ formatted string
to the IGNORE\_CEC list in PyChromecast like in the example below.

.. code:: python

    pychromecast.IGNORE_CEC.append('*')  # Ignore CEC on all devices
    pychromecast.IGNORE_CEC.append('Living Room')  # Ignore CEC on Chromecasts named Living Room

Thanks
------

I would like to thank `Fred Clift`_ for laying the socket client ground
work. Without him it would not have been possible!

.. _Linux style wildcard: http://tldp.org/LDP/GNU-Linux-Tools-Summary/html/x11655.htm
.. _@am0s: https://github.com/am0s
.. _@rmkraus: https://github.com/rmkraus
.. _@balloob: https://github.com/balloob
.. _Fred Clift: https://github.com/minektur
