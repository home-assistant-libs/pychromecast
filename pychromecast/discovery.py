"""Discovers Chromecasts on the network using mDNS/zeroconf."""
import logging
import socket
from uuid import UUID

import zeroconf

DISCOVER_TIMEOUT = 5

_LOGGER = logging.getLogger(__name__)


class CastListener(object):
    """Zeroconf Cast Services collection."""

    def __init__(self, add_callback=None, remove_callback=None):
        self.services = {}
        self.add_callback = add_callback
        self.remove_callback = remove_callback

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
        _LOGGER.debug("remove_service %s, %s", typ, name)
        service = self.services.pop(name, None)

        if not service:
            _LOGGER.debug("remove_service unknown %s, %s", typ, name)
            return

        if self.remove_callback:
            self.remove_callback(name, service)

    def add_service(self, zconf, typ, name):
        """ Add a service to the collection. """
        service = None
        tries = 0
        _LOGGER.debug("add_service %s, %s", typ, name)
        while service is None and tries < 4:
            try:
                service = zconf.get_service_info(typ, name)
            except IOError:
                # If the zeroconf fails to receive the necessary data we abort
                # adding the service
                break
            tries += 1

        if not service:
            _LOGGER.debug("add_service failed to add %s, %s", typ, name)
            return

        def get_value(key):
            """Retrieve value and decode to UTF-8."""
            value = service.properties.get(key.encode('utf-8'))

            if value is None or isinstance(value, str):
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

        if self.add_callback:
            self.add_callback(name)


def start_discovery(add_callback=None, remove_callback=None):
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
    listener = CastListener(add_callback, remove_callback)
    service_browser = False
    try:
        service_browser = zeroconf.ServiceBrowser(zeroconf.Zeroconf(),
                                                  "_googlecast._tcp.local.",
                                                  listener)
    except (zeroconf.BadTypeInNameException,
            NotImplementedError,
            OSError,
            socket.error,
            zeroconf.NonUniqueNameException):
        pass

    return listener, service_browser


def stop_discovery(browser):
    """Stop the chromecast discovery thread."""
    browser.zc.close()


def discover_chromecasts(max_devices=None, timeout=DISCOVER_TIMEOUT):
    """ Discover chromecasts on the network. """
    from threading import Event
    browser = False
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
    except Exception:  # pylint: disable=broad-except
        raise
    finally:
        if browser is not False:
            stop_discovery(browser)


def get_info_from_service(service, zconf):
    """ Resolve service_info from service. """
    service_info = None
    try:
        service_info = zconf.get_service_info('_googlecast._tcp.local.',
                                              service)
        if service_info:
            _LOGGER.debug(
                "get_info_from_service resolved service %s to service_info %s",
                service, service_info)
    except IOError:
        pass
    return service_info


def get_host_from_service_info(service_info):
    """ Get hostname or IP from service_info. """
    host = None
    port = None
    if (service_info and service_info.port and
            (service_info.server or service_info.address)):
        if service_info.address:
            host = socket.inet_ntoa(service_info.address)
        else:
            host = service_info.server.lower()
        port = service_info.port
    return (host, port)
