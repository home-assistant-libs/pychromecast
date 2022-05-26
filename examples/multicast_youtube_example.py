"""
Example on how to use YouTubeController to cast the same video to multiple Chromecast or Chromecast enabled devices.

"""

import pychromecast
from pychromecast.controllers.youtube import YouTubeController

print()
print('------- Searching for local chromecast devices... ')
services, browser = pychromecast.discovery.discover_chromecasts()
# Shut down discovery
pychromecast.discovery.stop_discovery(browser)

j = 0
print()
print('The following devices were found. Please review and select the devices you where you will cast.')
print()
for s in services:
    print("   " + str(j) + ": ", s.friendly_name)
    j = j + 1

print()
casts = input('Enter the id of the target devices separated by spaces, e.g. 0 1 2: ')
cast_names = []
for c in casts.split(' '):
    cast_names.append(services[int(c)].friendly_name)

print()
print('------- Devices selected.')
print()
print('Find the YouTube ID of the video you want to cast.')
print('  The video ID can be found after the "v=" in the address bar of your browser.')
print('  For example, if the video url is "https://www.youtube.com/watch?v=ABCd1234z", the viedo ID is ABCd1234z')
youtube_id = input('Enter the YouTube video ID: ')

print()
print('------- Thank you. Attempting to cast to each of the devices...')

chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=cast_names)

print()
for c in chromecasts:
    # Start worker thread and wait for cast device to be ready
    c.wait()
    print('------- Casting to ' + c.cast_info.friendly_name)
    yt = YouTubeController()
    c.register_handler(yt)
    yt.play_video(youtube_id)

print()
print('------- All done! Enjoy your show!')

# Shut down discovery
pychromecast.discovery.stop_discovery(browser)