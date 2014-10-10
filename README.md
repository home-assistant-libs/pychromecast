pychromecast
============

**Python 3 support is currently broken. Use version 0.5.1.1 on PyPy for Python 3 support.**

Library for Python 2 and 3 to communicate with the Google Chromecast. It currently supports:
 - Auto discovering connected Chromecasts on the network
 - Start the default media receiver and play any online media
 - Control playback of current playing media
 - Implement Google Chromecast api v2
 - Communicate with apps via channels
 - Easily extendable to add support for unsupported namespaces

Dependencies
------------

PyChromecast depends on the Python packages requests and protobuf. Make sure you have these dependencies installed using `pip install -r requirements.txt`

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

    >> print(cast.app)
    CastStatus(is_active_input=True, is_stand_by=False, volume_level=1.0, volume_muted=False, app_id=u'CC1AD845', display_name=u'Default Media Receiver', namespaces=[u'urn:x-cast:com.google.cast.player.message', u'urn:x-cast:com.google.cast.media'], session_id=u'CCA39713-9A4F-34A6-A8BF-5D97BE7ECA5C', transport_id=u'web-9', status_text='')

    >> mc = cast.media_controller
    >> print(mc.status)
    MediaStatus(current_time=42.458322, content_id=u'http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4', content_type=u'video/mp4', duration=596.474195, stream_type=u'BUFFERED', idle_reason=None, media_session_id=1, playback_rate=1, player_state=u'PLAYING', supported_media_commands=15, volume_level=1, volume_muted=False)

    >> mc.pause()
    >> time.sleep(5)
    >> mc.play()

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

Thanks
------

I would like to thank [Fred Clift](https://github.com/minektur) for laying the socket client ground work. Without him it would not have been possible!
