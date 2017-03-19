"""Discovers Chromecasts on the network using mDNS/zeroconf."""
from uuid import UUID
import socket
try:
    from http.client import HTTPResponse
    from io import BytesIO as ClassIO
    from urllib.parse import urlparse
except ImportError:
    from httplib import HTTPResponse
    from StringIO import StringIO as ClassIO
    from urlparse import urlparse

import six
from zeroconf import ServiceBrowser, Zeroconf

DISCOVER_TIMEOUT = 5
SSDP_ADDR = '239.255.255.250'
SSDP_PORT = 1900
SSDP_ST = 'urn:dial-multiscreen-org:service:dial:1'


class CastListener(object):
    """Zeroconf Cast Services collection."""
    def __init__(self, callback=None):
        self.services = {}
        self.callback = callback

    @property
    def count(self):
        """Number of discovered cast services."""
        return len(self.services)

    @property
    def devices(self):
        """List of tuples (ip, host) for each discovered device."""
        return list(self.services.values())

    # pylint: disable=unused-argument
    def remove_service(self, zconf, typ, name):
        """ Remove a service from the collection. """
        self.services.pop(name, None)

    def add_service(self, zconf, typ, name):
        """ Add a service to the collection. """
        service = None
        tries = 0
        while service is None and tries < 4:
            try:
                service = zconf.get_service_info(typ, name)
            except IOError:
                # If the zerconf fails to receive the necesarry data we abort
                # adding the service
                break
            tries += 1

        if not service:
            return

        def get_value(key):
            """Retrieve value and decode for Python 2/3."""
            value = service.properties.get(key.encode('utf-8'))

            if value is None or isinstance(value, six.text_type):
                return value
            return value.decode('utf-8')

        ips = zconf.cache.entries_with_name(service.server.lower())
        host = repr(ips[0]) if ips else service.server

        model_name = get_value('md')
        uuid = get_value('id')
        friendly_name = get_value('fn')

        if uuid:
            uuid = UUID(uuid)

        self.services[name] = (host, service.port, uuid, model_name,
                               friendly_name)

        if self.callback:
            self.callback((host, service.port, uuid, model_name,
                               friendly_name))


class FakeSocket(ClassIO):
    def makefile(self, *args, **kw):
        return self


def ssdp_discover(device_list, stop_event, callback=None, max_devices=None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    # TODO: configurable poll interval
    sock.settimeout(0.5)
    ssdp_message = "\r\n".join([
        'M-SEARCH * HTTP/1.1',
        'HOST: {IP}:{PORT}',
        'MAN: "ssdp:discover"',
        'ST: {ST}',
        'MX: 1',
        '', '']).format(IP=SSDP_ADDR, PORT=SSDP_PORT, ST=SSDP_ST)
    sock.sendto(six.b(ssdp_message), (SSDP_ADDR, SSDP_PORT))
    while not stop_event.is_set():
        try:
            ssdp_response = HTTPResponse(FakeSocket(sock.recv(1024)))
            ssdp_response.begin()
            host = urlparse(ssdp_response.getheader("location")).netloc.split(":")[0]
            device_list.append(host)
            if callback:
                callback(host)
            if len(device_list) >= max_devices:
                break
        except socket.timeout:
            continue


def start_discovery(callback=None, ssdp=False):
    """
    Start discovering chromecasts on the network.

    This method will start discovering chromecasts on a separate thread. When
    a chromecast is discovered, the callback will be called with the
    discovered chromecast's zeroconf name. This is the dictionary key to find
    the chromecast metadata in listener.services.

    This method returns the CastListener object and the zeroconf ServiceBrowser
    object. The CastListener object will contain information for the discovered
    chromecasts. To stop discovery, call the stop_discovery method with the
    ServiceBrowser object.
    """
    from threading import Event, Thread
    if ssdp:
        stop_discover = Event()
        device_list = []
        th = Thread(target=ssdp_discover, args=(device_list, stop_discover, callback))
        th.start()
        return device_list, stop_discover
    else:
        listener = CastListener(callback)
        return listener, \
            ServiceBrowser(Zeroconf(), "_googlecast._tcp.local.", listener)


def stop_discovery(browser):
    """Stop the chromecast discovery thread."""
    browser.zc.close()


def discover_chromecasts(max_devices=None, timeout=DISCOVER_TIMEOUT, ssdp=False):
    """ Discover chromecasts on the network. """
    from threading import Event, Thread
    if ssdp:
        stop_discover = Event()
        device_list = []
        th = Thread(target=ssdp_discover, args=(device_list, stop_discover),
                    kwargs={"max_devices": max_devices})
        th.start()
        th.join(DISCOVER_TIMEOUT)
        stop_discover.set()
        th.join()
        return device_list
    try:
        # pylint: disable=unused-argument
        def callback(name):
            """Called when zeroconf has discovered a new chromecast."""
            if max_devices is not None and listener.count >= max_devices:
                discover_complete.set()

        discover_complete = Event()
        listener, browser = start_discovery(callback)

        # Wait for the timeout or the maximum number of devices
        discover_complete.wait(timeout)

        return listener.devices
    finally:
        stop_discovery(browser)
