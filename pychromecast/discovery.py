"""Discovers Chromecasts on the network using mDNS/zeroconf."""
import logging
import socket
from threading import Event
from uuid import UUID

import zeroconf

DISCOVER_TIMEOUT = 5

_LOGGER = logging.getLogger(__name__)


class CastListener:
    """Zeroconf Cast Services collection."""

    def __init__(self, add_callback=None, remove_callback=None, update_callback=None):
        self.services = {}
        self.add_callback = add_callback
        self.remove_callback = remove_callback
        self.update_callback = update_callback

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
        service = None
        service_removed = False
        uuid = None
        for uuid, services_for_uuid in self.services.items():
            if name in services_for_uuid[0]:
                service = services_for_uuid
                services_for_uuid[0].remove(name)
                if len(services_for_uuid[0]) == 0:
                    self.services.pop(uuid)
                    service_removed = True
                break

        if not service:
            _LOGGER.debug("remove_service unknown %s, %s", typ, name)
            return

        if self.remove_callback and service_removed:
            self.remove_callback(uuid, name, service)
        if self.update_callback and not service_removed:
            self.update_callback(uuid, name)

    def update_service(self, zconf, typ, name):
        """ Update a service in the collection. """
        _LOGGER.debug("update_service %s, %s", typ, name)
        self._add_update_service(zconf, typ, name, self.update_callback)

    def add_service(self, zconf, typ, name):
        """ Add a service to the collection. """
        _LOGGER.debug("add_service %s, %s", typ, name)
        self._add_update_service(zconf, typ, name, self.add_callback)

    def _add_update_service(self, zconf, typ, name, callback):
        """ Add or update a service. """
        service = None
        tries = 0
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
            value = service.properties.get(key.encode("utf-8"))

            if value is None or isinstance(value, str):
                return value
            return value.decode("utf-8")

        model_name = get_value("md")
        uuid = get_value("id")
        friendly_name = get_value("fn")

        if not uuid:
            _LOGGER.debug("add_service failed to get uuid for %s, %s", typ, name)
            return
        uuid = UUID(uuid)

        services_for_uuid = self.services.setdefault(
            uuid, ({name}, uuid, model_name, friendly_name)
        )
        services_for_uuid[0].add(name)
        self.services[uuid] = (
            services_for_uuid[0],
            services_for_uuid[1],
            model_name,
            friendly_name,
        )

        if callback:
            callback(uuid, name)


def start_discovery(listener, zeroconf_instance):
    """
    Start discovering chromecasts on the network.

    This method will start discovering chromecasts on a separate thread. When
    a chromecast is discovered, the callback will be called with the
    discovered chromecast's zeroconf name. This is the dictionary key to find
    the chromecast metadata in listener.services.

    This method returns the zeroconf ServiceBrowser object.

    A CastListener object must be passed, and will contain information for the
    discovered chromecasts. To stop discovery, call the stop_discovery method with
    the ServiceBrowser object.

    A shared zeroconf instance can be passed as zeroconf_instance. If no
    instance is passed, a new instance will be created.
    """
    return zeroconf.ServiceBrowser(
        zeroconf_instance, "_googlecast._tcp.local.", listener,
    )


def stop_discovery(browser):
    """Stop the chromecast discovery thread."""
    try:
        browser.cancel()
    except RuntimeError:
        # Throws if called from service callback when joining the zc browser thread
        pass
    browser.zc.close()


def discover_chromecasts(max_devices=None, timeout=DISCOVER_TIMEOUT):
    """ Discover chromecasts on the network. """
    # pylint: disable=unused-argument
    def callback(uuid, name):
        """Called when zeroconf has discovered a new chromecast."""
        if max_devices is not None and listener.count >= max_devices:
            discover_complete.set()

    discover_complete = Event()
    listener = CastListener(callback)
    zconf = zeroconf.Zeroconf()
    browser = start_discovery(listener, zconf)

    # Wait for the timeout or the maximum number of devices
    discover_complete.wait(timeout)

    return (listener.devices, browser)


def get_info_from_service(service, zconf):
    """ Resolve service_info from service. """
    service_info = None
    try:
        service_info = zconf.get_service_info("_googlecast._tcp.local.", service)
        if service_info:
            _LOGGER.debug(
                "get_info_from_service resolved service %s to service_info %s",
                service,
                service_info,
            )
    except IOError:
        pass
    return service_info


def get_host_from_service_info(service_info):
    """ Get hostname or IP from service_info. """
    host = None
    port = None
    if (
        service_info
        and service_info.port
        and (service_info.server or len(service_info.addresses) > 0)
    ):
        if len(service_info.addresses) > 0:
            host = socket.inet_ntoa(service_info.addresses[0])
        else:
            host = service_info.server.lower()
        port = service_info.port
    return (host, port)
