import time

from zeroconf import ServiceBrowser, Zeroconf

DISCOVER_TIMEOUT = 5


class CastListener(object):
    def __init__(self):
        self.services = {}

    @property
    def count(self):
        return len(self.services)

    @property
    def devices(self):
        return list(self.services.values())

    def remove_service(self, zconf, typ, name):
        self.services.pop(name, None)

    def add_service(self, zconf, typ, name):
        service = None
        tries = 0
        while service is None and tries < 4:
            service = zconf.get_service_info(typ, name)
            tries += 1

        if service:
            ips = zconf.cache.entries_with_name(service.server.lower())
            host = repr(ips[0]) if ips else service.server

            self.services[name] = (host, service.port)


def discover_chromecasts(max_devices=None, timeout=DISCOVER_TIMEOUT):
    try:
        zconf = Zeroconf()
        listener = CastListener()
        browser = ServiceBrowser(zconf, "_googlecast._tcp.local.", listener)

        t = 0

        if max_devices is None:
            time.sleep(DISCOVER_TIMEOUT)
            return listener.devices

        else:
            while t < DISCOVER_TIMEOUT:
                time.sleep(.1)

                if listener.count >= max_devices:
                    return listener.devices

            return listener.devices
    finally:
        browser.cancel()
        zconf.close()
