#!/usr/bin/env python

# Copyright 2015 Benn Snyder <benn.snyder@gmail.com>
# Released under MIT license

from __future__ import print_function
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import os


def get_localhost():
	try:
		import netifaces
		dev = netifaces.gateways()["default"][netifaces.AF_INET][1]
		return netifaces.ifaddresses(dev)[netifaces.AF_INET][0]["addr"]
	except ImportError:
		import socket
		return "{0}.local".format(socket.getfqdn())

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
	for (root, dirs, files) in os.walk(dirpath, followlinks=True):
		dirs.sort()
		yield (root, dirs, files)
		num_sep_this = root.count(os.path.sep)
		if num_sep + max_depth <= num_sep_this:
			del dirs[:]

def resolve_path(name, max_depth):
	filepath = os.path.abspath(name)
	if os.path.isfile(filepath):
		filetype = get_filetype(os.path.realpath(filepath))
		yield (filepath, filetype)
	elif os.path.isdir(filepath) and max_depth > 0:
		for (root, subdirs, subfiles) in walk_depth(filepath, max_depth - 1):
			for subfile in sorted(subfiles):
				subfilepath = os.path.join(root, subfile)
				subfiletype = get_filetype(os.path.realpath(subfilepath))
				yield (subfilepath, subfiletype)

def resolve_name(name, max_depth, args):
	import contextlib
	import re
	import urllib2
	import urlparse
	import uuid

	# According to https://developers.google.com/cast/docs/media
	supportedtypes = [ "audio/aac", "audio/mpeg", "audio/ogg", "audio/wav",
	                   "image/bmp", "image/gif", "image/jpeg", "image/png", "image/webp",
	                   "video/mp4", "video/webm"
	                 ]

	parsed = urlparse.urlparse(name)
	if parsed.netloc == "":
		# local file(s)
		found_any = False
		for (filepath, filetype) in resolve_path(name, max_depth):
			found_any = True
			if filetype in supportedtypes:
				handle = str(uuid.uuid4())
				url = "http://{0}:{1}/{2}".format(args.host, args.port, handle)
				yield (url, filetype, handle, filepath)
		if found_any:
			return
	else:
		# remote file
		with contextlib.closing(urllib2.urlopen(parsed.geturl())) as source:
			filetype = source.info()["content-type"]
			url = source.geturl()
			if filetype in supportedtypes:
				yield (url, filetype, None, None)
				return

	# youtube link or ID
	youtube_re = re.compile(r"(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})")
	youtube_match = youtube_re.match(name)
	youtube_id = name if len(name) == 11 else (youtube_match.group(6) if youtube_match else None)
	if youtube_id is not None:
		try:
			# make sure video with youtube_id exists
			with contextlib.closing(urllib2.urlopen("https://youtube.com/oembed?url=https://youtube.com/watch?v={0}".format(youtube_id))) as exists:
				if exists.getcode() == 200:
					yield (youtube_id, "youtube", None, None)
					return
		except urllib2.HTTPError as error:
			print("Failed to verify YouTube video exists: {0}".format(error))

	print("Unable to resolve {0}".format(name))


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
	import pychromecast
	#import pychromecast.controllers.youtube
	import signal
	import threading
	import time

	if args.device is not None:
		cast = pychromecast.get_chromecast(strict=True, friendly_name=args.device)
	else:
		cast = pychromecast.get_chromecast(strict=True)

	controller = cast.media_controller
	#yt_controller = pychromecast.controllers.youtube.YouTubeController()
	#cast.register_handler(yt_controller)

	media = [] # list of (url, filetype)
	files = {} # dict of handle : (filepath, filetype)
	max_depth = args.recursive or 0

	for name in args.names:
		for (url, filetype, handle, filepath) in resolve_name(name, max_depth, args):
			media += [(url, filetype)]
			if filepath is not None and handle is not None:
				files[handle] = (filepath, filetype)

	httpd = None
	if len(files) > 0:
		def build_stream(*h_args):
			StreamHTTP(files, *h_args)
		httpd = HTTPServer((args.host, args.port), build_stream)
		threading.Thread(target=httpd.serve_forever).start()

	# Treat SIGTERM like Ctrl-C
	def handle_signal(signum, frame):
		if (signum == signal.SIGTERM):
			raise KeyboardInterrupt("Caught SIGTERM; shutting down")
	signal.signal(signal.SIGTERM, handle_signal)

	try:
		for (url, filetype) in media:
			print("Casting {0} ({1}) to {2}".format(url, filetype, cast))

			if filetype == "youtube":
				print("Skipping YouTube video")
				# YouTube decides to auto-play extra videos after the first one.
				# Disabled until we find a workaround for this dumbass behavior.
				#yt_controller.play_video(url)
				#time.sleep(8) # wait for youtube to start playing
				#while yt_controller.screen_id is not None:
				#	time.sleep(1)
			else:
				controller.play_media(url, filetype)
				while not controller.status.player_is_idle:
					time.sleep(1)

			time.sleep(args.wait)

	finally:
		cast.quit_app()
		if httpd is not None:
			httpd.shutdown()


if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser(version="0.5")
	parser.add_argument("names",             type=str,                     nargs="*",                      help="files, directories, and/or URLs to cast")
	parser.add_argument("-r", "--recursive", type=int, const=float("inf"), nargs="?", metavar="MAX_DEPTH", help="recurse directories to find files")
	parser.add_argument("-w", "--wait",      type=int, default=1,                                          help="seconds to wait between each file")
	parser.add_argument("-n", "--host",      type=str, default=get_localhost(),                            help="hostname or IP to serve content")
	parser.add_argument("-p", "--port",      type=int, default=5403,                                       help="port on which to serve content")
	parser.add_argument("-d", "--device",    type=str, default=None,                                       help="name of cast target")
	parser.add_argument("-l", "--list",      action="store_true",                                          help="list available devices and exit")
	args = parser.parse_args()

	if args.list:
		import pychromecast
		for device in pychromecast.get_chromecasts():
			print(device)
	else:
		if len(args.names) == 0:
			parser.error("must specify one or more names to cast")
		cast(args)
