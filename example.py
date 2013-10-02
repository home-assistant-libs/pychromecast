import pychromecast
import time

host = "192.168.1.120"

# Start the ChromeCast on the home screen so
# the example makes more sense.
pychromecast.quit_app(host)

# Give it some time
time.sleep(4)

# Example using the class
cast = pychromecast.PyChromecast(host)
print cast.device
print "Home screen:", cast.app

cast.app_id = pychromecast.APP_ID_YOUTUBE
print "YouTube status:", cast.app

cast.start_app()

print "YouTube status after opening:", cast.app

# If we are too fast in giving commands the ChromeCast doesn't listen
time.sleep(6)

# Example using the methods
pychromecast.play_youtube_video(host, "kxopViU98Xo")
