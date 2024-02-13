"""Common helpers and utilities shared by examples."""

import argparse
import logging

import zeroconf


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
    logging.basicConfig(format=fmt, datefmt=datefmt, level=logging.INFO)

    if args.show_debug:
        logging.getLogger("pychromecast.dial").setLevel(logging.INFO)
        logging.getLogger("pychromecast.discovery").setLevel(logging.INFO)
    if args.show_discovery_debug:
        logging.getLogger("pychromecast.dial").setLevel(logging.DEBUG)
        logging.getLogger("pychromecast.discovery").setLevel(logging.DEBUG)
    if args.show_zeroconf_debug:
        print("Zeroconf version: " + zeroconf.__version__)
        logging.getLogger("zeroconf").setLevel(logging.DEBUG)
