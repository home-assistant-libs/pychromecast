pychromecast
============

Allows to remote control the Chromecast from Python 2 and 3. It currently supports:
 - Auto discovering connected Chromecasts on the network
 - Read Chromecast device status
 - Read application status
 - Read the status of the current content being played*
 - Control content: play, pause, change volume, mute or skip*

*: only supported by apps that support the RAMP-protocol.

Dependencies
------------

PyChromecast depends on the Python packages requests and ws4py. Make sure you have these dependencies installed using `pip install -r requirements.txt`

How to use
----------

    >> import time
    >> import pychromecast

    >> cast = pychromecast.get_single_chromecast(friendly_name="Living Room")
    >> print cast.device
    DeviceStatus(friendly_name='Living Room', model_name='Eureka Dongle', manufacturer='Google Inc.', api_version=(1, 0))

    >> print cast.app
    AppStatus(app_id='YouTube', description='YouTube TV', state='running', options={'allowStop': 'true'}, service_url='http://192.168.1.9:8008/connection/YouTube', service_protocols=['ramp'])

    >> time.sleep(1)  # sleep 1s so RAMP connection has time to init

    >> ramp = cast.get_protocol(pychromecast.PROTOCOL_RAMP)
    >> ramp
    RampSubprotocol(Epic sax guy 10 hours, 810.4/36001, playing)

    >> ramp.pause()

Websocket protocol
------------------

Most apps can be communicated with using a websocket. For their own apps Google uses the RAMP protocol to control the media and give information on current running feedback.

At this point in time the RAMP protocol is the only protocol that is implemented. Except for Netflix all major applications on the Chromecast speak the RAMP protocol (ie YouTube, Google Music, HBO, HULU).

Known issues
------------

Since Google has opened up the Chromecast SDK not all apps seem to be reachable using the DIAL-api. Therefore not all apps are exposed via the app attribute.

