#!/usr/bin/env python

# Copyright 2015 Benn Snyder <benn.snyder@gmail.com>
# Released under MIT license

from __future__ import print_function
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import collections
import os


def get_localhost():
	try:
		import netifaces
		dev = netifaces.gateways()["default"][netifaces.AF_INET][1]
		return netifaces.ifaddresses(dev)[netifaces.AF_INET][0]["addr"]
	except ImportError:
		import socket
		return socket.getfqdn() + ".local"

def get_filetype(filepath):
	try:
		import magic
		return magic.from_file(filepath, mime=True)
	except (ImportError, UnicodeDecodeError):
		ext_to_mime = { ".aac" : "audio/aac", ".mp3" : "audio/mpeg", ".ogg" : "audio/ogg", ".wav" : "audio/wav",
		                ".bmp" : "image/bmp", ".gif" : "image/gif", ".jpg" : "image/jpeg", ".jpeg" : "image/jpeg", ".png" : "image/png", ".webp" : "image/webp",
		                ".mp4" : "video/mp4", ".webm" : "video/webm",
		              }
		(root, ext) = os.path.splitext(filepath)
		return ext_to_mime.get(ext.lower(), None)

def walk_depth(dirpath, max_depth=1):
	dirpath = dirpath.rstrip(os.path.sep)
	assert os.path.isdir(dirpath)
	num_sep = dirpath.count(os.path.sep)
	for root, dirs, files in os.walk(dirpath, followlinks=True):
		dirs.sort()
		yield root, dirs, files
		num_sep_this = root.count(os.path.sep)
		if num_sep + max_depth <= num_sep_this:
			del dirs[:]

def resolve_path(name, max_depth):
	import uuid

	files = collections.OrderedDict()

	def add_file(filepath):
		filetype = get_filetype(os.path.realpath(filepath))
		files[str(uuid.uuid4())] = (filepath, filetype)

	filepath = os.path.abspath(name)
	if os.path.isfile(filepath):
		add_file(filepath)
	elif os.path.isdir(filepath) and max_depth > 0:
		for (root, subdirs, subfiles) in walk_depth(filepath, max_depth - 1):
			for subfile in sorted(subfiles):
				add_file(os.path.join(root, subfile))

	return files


class StreamHTTP(BaseHTTPRequestHandler):
	def __init__(self, files, *args):
		self.files = files
		BaseHTTPRequestHandler.__init__(self, *args)

	def do_HEAD(self):
		(filepath, filetype) = self.files[self.path[1:]]
		self.send_response(200)
		self.send_header("Content-type", filetype)
		self.end_headers()
		return (filepath, filetype)

	def do_GET(self):
		(filepath, filetype) = self.do_HEAD()

		chunksize = 8192
		with open(filepath, 'rb') as source:
			chunk = source.read(chunksize)
			while chunk:
				self.wfile.write(chunk)
				chunk = source.read(chunksize)


def cast(args):
	import contextlib
	import pychromecast
	import threading
	import time
	import urllib2
	import urlparse

	if args.device is not None:
		cast = pychromecast.get_chromecast(strict=True, friendly_name=args.device)
	else:
		cast = pychromecast.get_chromecast(strict=True)

	controller = cast.media_controller

	if controller.is_active and not controller.is_idle:
		print("{0} is busy".format(cast))
		return


	# According to https://developers.google.com/cast/docs/media
	supportedtypes = [ "audio/aac", "audio/mpeg", "audio/ogg", "audio/wav",
	                   "image/bmp", "image/gif", "image/jpeg", "image/png", "image/webp",
	                   "video/mp4", "video/webm"
	                 ]

	media = [] # list of (url, filetype) tuples
	files = collections.OrderedDict()
	max_depth = args.recursive or 0

	for name in args.names:
		parsed = urlparse.urlparse(name)

		if parsed.netloc != "":
			# remote file
			with contextlib.closing(urllib2.urlopen(parsed.geturl())) as source:
				filetype = source.info()["Content-type"]
				url = source.geturl()
				if filetype in supportedtypes:
					media += [(url, filetype)]
		else:
			# local file
			files.update(resolve_path(name, max_depth))

			for (handle, (filepath, filetype)) in files.items():
				url = "http://{0}:{1}/{2}".format(args.host, args.port, handle)
				if filetype in supportedtypes:
					media += [(url, filetype)]

	httpd = None
	if len(files) > 0:
		def build_stream(*h_args):
			StreamHTTP(files, *h_args)
		httpd = HTTPServer((args.host, args.port), build_stream)
		threading.Thread(target=httpd.serve_forever).start()

	try:
		for (url, filetype) in media:
			print("Casting {0} ({1}) to {2}".format(url, filetype, cast))
			cast.play_media(url, filetype)

			while not controller.is_idle:
				pass

			time.sleep(args.wait)

	finally:
		cast.quit_app()
		if httpd is not None:
			httpd.shutdown()


if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser(version="0.3")
	parser.add_argument("names",             type=str,                     nargs="+",                      help="files, directories, and/or URLs to cast")
	parser.add_argument("-r", "--recursive", type=int, const=float("inf"), nargs="?", metavar="MAX_DEPTH", help="recurse directories to find files")
	parser.add_argument("-w", "--wait",      type=int, default=1,                                          help="seconds to wait between each file")
	parser.add_argument("-n", "--host",      type=str, default=get_localhost(),                            help="hostname or IP to serve content")
	parser.add_argument("-p", "--port",      type=int, default=5403,                                       help="port on which to serve content")
	parser.add_argument("-d", "--device",    type=str, default=None,                                       help="name of cast target")
	args = parser.parse_args()

	cast(args)
