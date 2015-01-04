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
        self.services.pop(name)

    def add_service(self, zconf, typ, name):
        service = zconf.get_service_info(typ, name)

        self.services[name] = (service.server, service.port)


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
