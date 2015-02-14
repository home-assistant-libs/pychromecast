#!/usr/bin/env python

from __future__ import print_function
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler


def local_ip():
	try:
		import netifaces
		dev = netifaces.gateways()["default"][netifaces.AF_INET][1]
		return netifaces.ifaddresses(dev)[netifaces.AF_INET][0]["addr"]
	except:
		import socket
		return socket.getfqdn() + ".local"


def resolve_file(filename, tmpdir):
	from os import path
	import magic
	import subprocess

	# According to https://developers.google.com/cast/docs/media
	supportedtypes = [ "audio/aac", "audio/mpeg", "audio/ogg", "audio/wav",
	                   "image/bmp", "image/gif", "image/jpeg", "image/png", "image/webp",
	                   "video/mp4", "video/webm"
	                 ]

	filepath = path.realpath(filename)
	basename = path.basename(filepath)
	filetype = magic.from_file(filepath, mime=True)

	if filetype in supportedtypes:
		return (filepath, filetype, None) # no conversion necessary

	if filetype.startswith("audio/"):
		filepath_out = "{0}.ogg".format(path.join(tmpdir, basename))

		command = [ "ffmpeg",
	                "-i", filepath,
	                #"-preset", "fast",
	                #"-ac", "2",
	                #"-c:v", "libvpx",
	                "-c:a", "libvorbis",
	                "-threads", "auto",
	                #"-movflags", "faststart",
	                filepath_out ]

		ffmpeg = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		return (filepath_out, "audio/ogg", ffmpeg)

	if filetype.startswith("video/"):
		filepath_out = "{0}.webm".format(path.join(tmpdir, basename))

		command = [ "ffmpeg",
	                "-i", filepath,
	                "-preset", "fast",
	                "-ac", "2",
	                "-c:v", "libvpx",
	                "-c:a", "libvorbis",
	                "-threads", "auto",
	                "-movflags", "faststart",
	                filepath_out ]

		ffmpeg = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		return (filepath_out, "video/webm", ffmpeg)


	raise RuntimeError("Unsupported file type: {0}".format(filetype))


class StreamHTTP(BaseHTTPRequestHandler):
	def __init__(self, filepath, filetype, ffmpeg, *args):
		self.filepath = filepath
		self.filetype = filetype
		self.ffmpeg = ffmpeg
		BaseHTTPRequestHandler.__init__(self, *args)

	def do_HEAD(self):
		self.send_response(200)
		self.send_header("Content-type", self.filetype)
		self.end_headers()

	def do_GET(self):
		self.do_HEAD()

		chunksize = 8192

		with open(self.filepath, 'rb') as source:
			while True:
				chunk = source.read(chunksize)

				if chunk:
					self.wfile.write(chunk) # send some bytes
				elif self.ffmpeg and self.ffmpeg.poll() is not None:
					import time
					time.sleep(3)           # wait for more file data
				else:
					break                   # really EOF


def main():
	import argparse
	import shutil
	import tempfile
	import threading

	parser = argparse.ArgumentParser()
	parser.add_argument("filename",       type=str, help="file to cast")
	parser.add_argument("-n", "--host",   type=str, default=local_ip(), help="hostname or IP to serve content")
	parser.add_argument("-p", "--port",   type=int, default=5403, help="port on which to serve content")
	parser.add_argument("-d", "--device", type=str, default=None, help="Name of cast target")

	args = parser.parse_args()


	tmpdir = tempfile.mkdtemp()

	(filepath, filetype, ffmpeg) = resolve_file(args.filename, tmpdir)

	def build_stream(*h_args): # lets us pass arguments the constructor
		StreamHTTP(filepath, filetype, ffmpeg, *h_args)
	httpd = HTTPServer((args.host, args.port), build_stream)
	threading.Thread(target=httpd.serve_forever).start()

	url = "http://{0}:{1}".format(args.host, args.port)
	print("Serving {0} ({1}) at {2}".format(filepath, filetype, url))


	try:
		import pychromecast

		if args.device is not None:
			cast = pychromecast.get_chromecast(strict=True, friendly_name=args.device)
		else:
			cast = pychromecast.get_chromecast(strict=True)

		controller = cast.media_controller

		if controller and controller.is_active and not controller.is_idle:
			print("{0} is busy".format(cast))
			return

		print("Casting to {0}".format(cast))
		cast.play_media(url, filetype)

		try:
			while True:
				pass
		finally:
			controller.stop()
			cast.quit_app()

	finally:
		if ffmpeg is not None:
			ffmpeg.terminate()

		httpd.shutdown()
		shutil.rmtree(tmpdir)


if __name__ == "__main__":
	main()
