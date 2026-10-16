"""Common helpers and utilities shared by examples."""

import argparse
import logging

import zeroconf

from pychromecast.discovery import ZEROCONF_IP_VERSIONS
from pychromecast.models import IpVersion


def add_network_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments to control networking to the parser."""
    parser.add_argument(
        "--ip-version",
        help="Only use this IP version for discovery and connections (default: any)",
        type=int,
        choices=(4, 6),
        default=None,
    )


def create_zeroconf(args: argparse.Namespace) -> zeroconf.Zeroconf:
    """Create a zeroconf instance according to command line arguments."""
    return zeroconf.Zeroconf(
        ip_version=ZEROCONF_IP_VERSIONS.get(args.ip_version, zeroconf.IPVersion.All)
    )


def get_ip_version(args: argparse.Namespace) -> IpVersion | None:
    """Get the IP version to connect to cast devices over."""
    ip_version: IpVersion | None = args.ip_version
    return ip_version


def add_log_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments to control logging to the parser."""
    parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
    parser.add_argument(
        "--show-discovery-debug", help="Enable discovery debug log", action="store_true"
    )
    parser.add_argument(
        "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
    )


def configure_logging(args: argparse.Namespace) -> None:
    """Configure logging according to command line arguments."""
    fmt = "%(asctime)s %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    default_log_level = logging.DEBUG if args.show_debug else logging.INFO
    logging.basicConfig(format=fmt, datefmt=datefmt, level=default_log_level)

    if args.show_debug:
        logging.getLogger("pychromecast.dial").setLevel(logging.INFO)
        logging.getLogger("pychromecast.discovery").setLevel(logging.INFO)
    if args.show_discovery_debug:
        logging.getLogger("pychromecast.dial").setLevel(logging.DEBUG)
        logging.getLogger("pychromecast.discovery").setLevel(logging.DEBUG)
    if args.show_zeroconf_debug:
        print("Zeroconf version: " + zeroconf.__version__)
        logging.getLogger("zeroconf").setLevel(logging.DEBUG)
