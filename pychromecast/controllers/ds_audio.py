"""
Controller to interface with the DS Audio-app at https://dsaudio-chromecast.synology.com/dsaudio.html
"""
from collections import namedtuple

from ..config import APP_DS_AUDIO
from . import BaseController

# STREAM_TYPE_UNKNOWN = "UNKNOWN"
# STREAM_TYPE_BUFFERED = "BUFFERED"
# STREAM_TYPE_LIVE = "LIFE"

AUDIO_PLAYER_REPEAT_NONE = "none"
AUDIO_PLAYER_REPEAT_ONE = "one"
AUDIO_PLAYER_REPEAT_ALL = "all"

MEDIA_PLAYER_STATUS_PLAYING = "playing"
MEDIA_PLAYER_STATUS_PAUSED = "pause"
MEDIA_PLAYER_STATE_IDLE = "stopped"
MEDIA_PLAYER_STATE_UNKNOWN = "UNKNOWN"

MESSAGE_DATA = 'data'
MESSAGE_COMMAND = 'command'
MESSAGE_TYPE = "type"

TYPE_IDENTIFY = "identify"
TYPE_CHALLENGE = "challenge"
TYPE_PLAYLIST = "playlist"
TYPE_MEDIA_STATUS = "status"

TYPE_PLAY = "resume"
TYPE_PLAY_INDEX = "play"
TYPE_PAUSE = "pause"
TYPE_STOP = "stop"
TYPE_NEXT = "next"
TYPE_PREV = "prev"
TYPE_REPLAY_CURRENT = "replayCurrent"
TYPE_SEEK = "seek"
TYPE_REPEAT = "set_repeat"
TYPE_SHUFFLE = "set_shuffle"
#TODO TYPE_UPDATE_PLAYLIST = "update_playlist"

DATA_PLAY_INDEX = "playing_index"
DATA_SEEK_POSITION = "position"
DATA_REPEAT_MODE = "mode"
DATA_SHUFFLE_ENABLED = "enabled"
#TODO DATA_UPDATE_PLAYLIST_OFFSET
#TODO DATA_UPDATE_PLAYLIST_LIMIT
#TODO DATA_UPDATE_PLAYLIST_SONGS
#TODO DATA_UPDATE_PLAYLIST_PLAYING_INDEX

# TYPE_GET_STATUS = "GET_STATUS"
# TYPE_PLAY = "PLAY"
# TYPE_PAUSE = "PAUSE"
# TYPE_STOP = "STOP"
# TYPE_LOAD = "LOAD"
# TYPE_SEEK = "SEEK"
# TYPE_EDIT_TRACKS_INFO = "EDIT_TRACKS_INFO"

# METADATA_TYPE_GENERIC = 0
# METADATA_TYPE_TVSHOW = 1
# METADATA_TYPE_MOVIE = 2
# METADATA_TYPE_MUSICTRACK = 3
# METADATA_TYPE_PHOTO = 4

# CMD_SUPPORT_PAUSE = 1
# CMD_SUPPORT_SEEK = 2
# CMD_SUPPORT_STREAM_VOLUME = 4
# CMD_SUPPORT_STREAM_MUTE = 8
# CMD_SUPPORT_SKIP_FORWARD = 16
# CMD_SUPPORT_SKIP_BACKWARD = 32


# MediaImage = namedtuple('MediaImage', 'url height width')

#     def _process_status(self, status):
#         """ Process latest status update. """
#         self.position = status.get('position')  # in seconds
#         self.buffered = status.get('buffered')  # in seconds
#         self.playing_index = status.get('playing_index')  # item in the list of songs in the album
#         self.song = status.get('song')  # song object

#         # 'song':{
#         #    'album':'538 Dance Smash Hits 2004, Volume 4: Autumn',
#         #    'type':'file',
#         #    'album_artist':'Various Artists',
#         #    'genre':'House/Euro House/Progressive Trance/Trance',
#         #    'artist':'Marly',
#         #    'composer':'',
#         #    'duration':199.7406,
#         #    'title':'You Never Know',
#         #    'cover_url':'[url_to_cover_image]',
#         #    'song_url':'[url_to_cover_image]',
#         #    'extra':{
#         #       'song_id':'music_4376',
#         #       'ds_id':'1370LSN001554'
#         #    }
#         # },
#         self.repeat_mode = status.get('repeat_mode')  # 'none','one','all',
#         self.shuffle_enabled = status.get('shuffle_enabled')  # true, false
#         self.playing_status = status.get('status')  # "playing";"pause";"stopped";
#         self.seekable = status.get('seekable')  # in seconds

# {
#             status: 'playing',
#             position: 234.34,
#             buffered: 234.34,
#             seekable: 234.34,
#             shuffle_enabled: false,
#             repeat_mode: 'all',
#             playing_index: 5,
#             song: {
#                 duration: 234.34
#                 xxx:""
#             },
#             is_certificate_untrusted: this.is_certificate_untrusted
#         };

class DsAudioMediaStatus(object):
    """ Class to hold the DS Audio media status. """

    # pylint: disable=too-many-instance-attributes,too-many-public-methods
    def __init__(self):

        """ Default media status properties """
        self.current_time = 0
        #self.content_id = None
        #self.content_type = None
        self.duration = None
        #self.stream_type = STREAM_TYPE_UNKNOWN
        #self.idle_reason = None
        #self.media_session_id = None
        #self.playback_rate = 1
        self.player_state = MEDIA_PLAYER_STATE_UNKNOWN
        #self.supported_media_commands = 0
        #self.volume_level = 1
        #self.volume_muted = False
        #self.media_custom_data = {}
        self.media_metadata = {}
        #self.subtitle_tracks = {}

        """ Synology media status additions """
        self.buffered = None
        self.seekable = None
        self.shuffle_enabled = False
        self.repeat_mode = AUDIO_PLAYER_REPEAT_NONE
        self.playing_index= None
        self.is_certificate_untrusted = False

#     @property
#     def metadata_type(self):
#         """ Type of meta data. """
#         return self.media_metadata.get('metadataType')

    @property
    def player_is_playing(self):
        """ Return True if player is PLAYING. """
        return self.player_state == MEDIA_PLAYER_STATE_PLAYING

    @property
    def player_is_paused(self):
        """ Return True if player is PAUSED. """
        return self.player_state == MEDIA_PLAYER_STATE_PAUSED

    @property
    def player_is_idle(self):
        """ Return True if player is IDLE. """
        return self.player_state == MEDIA_PLAYER_STATE_IDLE

#     @property
#     def media_is_generic(self):
#         """ Return True if media status represents generic media. """
#         return self.metadata_type == METADATA_TYPE_GENERIC

#     @property
#     def media_is_tvshow(self):
#         """ Return True if media status represents a tv show. """
#         return self.metadata_type == METADATA_TYPE_TVSHOW

#     @property
#     def media_is_movie(self):
#         """ Return True if media status represents a movie. """
#         return self.metadata_type == METADATA_TYPE_MOVIE

#     @property
#     def media_is_musictrack(self):
#         """ Return True if media status represents a musictrack. """
#         return self.metadata_type == METADATA_TYPE_MUSICTRACK

#     @property
#     def media_is_photo(self):
#         """ Return True if media status represents a photo. """
#         return self.metadata_type == METADATA_TYPE_PHOTO

#     @property
#     def stream_type_is_buffered(self):
#         """ Return True if stream type is BUFFERED. """
#         return self.stream_type == STREAM_TYPE_BUFFERED

#     @property
#     def stream_type_is_live(self):
#         """ Return True if stream type is LIVE. """
#         return self.stream_type == STREAM_TYPE_LIVE

    @property
    def title(self):
        """ Return title of media. """
        return self.media_metadata.get('title')

#     @property
#     def series_title(self):
#         """ Return series title if available. """
#         return self.media_metadata.get('seriesTitle')

#     @property
#     def season(self):
#         """ Return season if available. """
#         return self.media_metadata.get('season')

#     @property
#     def episode(self):
#         """ Return episode if available. """
#         return self.media_metadata.get('episode')

    @property
    def artist(self):
        """ Return artist if available. """
        return self.media_metadata.get('artist')

    @property
    def album_name(self):
        """ Return album name if available. """
        return self.media_metadata.get('album')

    @property
    def album_artist(self):
        """ Return album artist if available. """
        return self.media_metadata.get('album_artist')

    @property
    def track(self):
        """ Return track number if available. """
        #return self.media_metadata.get('track')
        return self.playing_index

#     @property
#     def images(self):
#         """ Return a list of MediaImage objects for this media. """
#         return [
#             MediaImage(item.get('url'), item.get('height'), item.get('width'))
#             for item in self.media_metadata.get('images', [])
#         ]

#     @property
#     def supports_pause(self):
#         """ True if PAUSE is supported. """
#         return bool(self.supported_media_commands & CMD_SUPPORT_PAUSE)

#     @property
#     def supports_seek(self):
#         """ True if SEEK is supported. """
#         return bool(self.supported_media_commands & CMD_SUPPORT_SEEK)

#     @property
#     def supports_stream_volume(self):
#         """ True if STREAM_VOLUME is supported. """
#         return bool(self.supported_media_commands & CMD_SUPPORT_STREAM_VOLUME)

#     @property
#     def supports_stream_mute(self):
#         """ True if STREAM_MUTE is supported. """
#         return bool(self.supported_media_commands & CMD_SUPPORT_STREAM_MUTE)

#     @property
#     def supports_skip_forward(self):
#         """ True if SKIP_FORWARD is supported. """
#         return bool(self.supported_media_commands & CMD_SUPPORT_SKIP_FORWARD)

#     @property
#     def supports_skip_backward(self):
#         """ True if SKIP_BACKWARD is supported. """
#         return bool(self.supported_media_commands & CMD_SUPPORT_SKIP_BACKWARD)

    def update(self, data):
        """ New data will only contain the changed attributes. """

        #print("DsAudio:Received update %s", data)

        # if len(data.get('status', [])) == 0:
        #     return

        status_data = data['data']
        
        song_data = status_data.get('song') or {}

        """ Media properties """
        self.current_time = status_data.get('position')
        #self.content_id = media_data.get('contentId', self.content_id)
        #self.content_type = media_data.get('contentType', self.content_type)
        self.duration = song_data.get('duration')
        #self.stream_type = media_data.get('streamType', self.stream_type)
        #self.idle_reason = status_data.get('idleReason', self.idle_reason)
        #self.media_session_id = status_data.get(
        #    'mediaSessionId', self.media_session_id)
        #self.playback_rate = status_data.get(
        #    'playbackRate', self.playback_rate)
        self.player_state = status_data.get('status')
        #self.supported_media_commands = status_data.get(
        #    'supportedMediaCommands', self.supported_media_commands)
        #self.volume_level = volume_data.get('level', self.volume_level)
        #self.volume_muted = volume_data.get('muted', self.volume_muted)
        #self.media_custom_data = media_data.get(
        #    'customData', self.media_custom_data)
        self.media_metadata = song_data
        #self.subtitle_tracks = media_data.get('tracks', self.subtitle_tracks)

        """ Additional DS Audio properties """
        self.buffered = status_data.get('buffered')
        self.seekable = status_data.get('seekable')
        self.shuffle_enabled = status_data.get('shuffle_enabled')
        self.repeat_mode = status_data.get('repeat_mode')
        self.playing_index = status_data.get('playing_index')
        self.is_certificate_untrusted = status_data.get('is_certificate_untrusted')

    def __repr__(self):
        info = {
            'metadata_type': self.metadata_type,
            'title': self.title,
            'series_title': self.series_title,
            'season': self.season,
            'episode': self.episode,
            'artist': self.artist,
            'album_name': self.album_name,
            'album_artist': self.album_artist,
            'track': self.track,
            #'subtitle_tracks': self.subtitle_tracks,
            #'images': self.images,
            # 'supports_pause': self.supports_pause,
            # 'supports_seek': self.supports_seek,
            # 'supports_stream_volume': self.supports_stream_volume,
            # 'supports_stream_mute': self.supports_stream_mute,
            # 'supports_skip_forward': self.supports_skip_forward,
            # 'supports_skip_backward': self.supports_skip_backward,
        }
        info.update(self.__dict__)
        return '<DsAudioMediaStatus {}>'.format(info)


class DsAudioController(BaseController):
    """ Controller to interact with Synology audio namespace. """

    def __init__(self):
        super(DsAudioController, self).__init__(
            "urn:x-cast:com.synology.dsaudio", APP_DS_AUDIO)

        self.media_session_id = 0
        self.status = DsAudioMediaStatus()

        self._status_listeners = []

    def channel_connected(self):
        """ Called when media channel is connected. Will update status. """
        
        msg = {
            MESSAGE_COMMAND: TYPE_IDENTIFY,
            MESSAGE_DATA: {"auth_key": "Doesn't matter'"}
            }

        self.logger.debug("DsAudio:Sending identify init message %s", msg)
        
        self.send_message(msg) #TODO use CONSTS

        self.update_status()

    def channel_disconnected(self):
        """ Called when a media channel is disconnected. Will erase status. """
        self.status = DsAudioMediaStatus()
        self._fire_status_changed()

    def receive_message(self, message, data):
        """ Called when a media message is received. """

        self.logger.debug("DsAudio:Received message %s", message)
        

        if data[MESSAGE_TYPE] == TYPE_PLAYLIST:
            self._process_playlist(data)

            return True

        elif data[MESSAGE_TYPE] == TYPE_MEDIA_STATUS:
            self._process_media_status(data)

            return True

        elif data[MESSAGE_TYPE] == TYPE_CHALLENGE:
            self._handle_challenge(data)

            return True

        else:
            return False

    def register_status_listener(self, listener):
        """ Register a listener for new media statusses. A new status will
            call listener.new_media_status(status) """
        self._status_listeners.append(listener)

    def update_status(self, blocking=False):
        """ Send message to update the status. """
        self.send_message({MESSAGE_TYPE: TYPE_GET_STATUS},
                          wait_for_response=blocking)

    def _send_command(self, command):
        """ Send a command to the Chromecast on media channel. """
        if self.status is None or self.status.media_session_id is None:
            return

        command['mediaSessionId'] = self.status.media_session_id

        self.send_message(command, inc_session_id=True)

    # @property
    # def is_playing(self):
    #     """ Deprecated as of June 8, 2015. Use self.status.player_is_playing.
    #         Returns if the Chromecast is playing. """
    #     return self.status is not None and self.status.player_is_playing

    # @property
    # def is_paused(self):
    #     """ Deprecated as of June 8, 2015. Use self.status.player_is_paused.
    #         Returns if the Chromecast is paused. """
    #     return self.status is not None and self.status.player_is_paused

    # @property
    # def is_idle(self):
    #     """ Deprecated as of June 8, 2015. Use self.status.player_is_idle.
    #         Returns if the Chromecast is idle on a media supported app. """
    #     return self.status is not None and self.status.player_is_idle

    # @property
    # def title(self):
    #     """ Deprecated as of June 8, 2015. Use self.status.title.
    #         Return title of the current playing item. """
    #     return None if not self.status else self.status.title

    # @property
    # def thumbnail(self):
    #     """ Deprecated as of June 8, 2015. Use self.status.images.
    #         Return thumbnail url of current playing item. """
    #     if not self.status:
    #         return None

    #     images = self.status.images

    #     return images[0].url if images and len(images) > 0 else None


    def play(self):
        """ Send play command. """
        self.send_message({MESSAGE_COMMAND: TYPE_PLAY})

    def play_index(self, song_index):
        """ Play a specific song in the playlist """
        msg = {
            MESSAGE_COMMAND: TYPE_PLAY_INDEX,
            MESSAGE_DATA: {
                DATA_PLAY_INDEX: song_index
            }
        }
        self.send_message(msg)

    def pause(self):
        """ Send pause command. """
        self.send_message({MESSAGE_COMMAND: TYPE_PAUSE})

    def stop(self):
        """ Send stop command. """
        self.send_message({MESSAGE_COMMAND: TYPE_STOP})

    def next(self):
        """ Send pause command. """
        self.send_message({MESSAGE_COMMAND: TYPE_NEXT})

    def prev(self):
        """ Send play command. """
        self.send_message({MESSAGE_COMMAND: TYPE_PREV})

    def replayCurrent(self):
        """ Replay current song """
        self.send_message({MESSAGE_COMMAND: TYPE_REPLAY_CURRENT})

    def seek(self, position):
        """ Seek to a specific position """
        msg = {
            MESSAGE_COMMAND: TYPE_SEEK,
            MESSAGE_DATA: {
                DATA_SEEK_POSITION: position
            }
        }
        self.send_message(msg)

    def repeat(self, repeatMode):
        """ Set the repeat mode """
        msg = {
            MESSAGE_COMMAND: TYPE_REPEAT,
            MESSAGE_DATA: {
                DATA_REPEAT_MODE: repeatMode
            }
        }
        self.send_message(msg)

    def shuffle(self, enableShuffle):
        """ Enable or disable shuffle """
        msg = {
            MESSAGE_COMMAND: TYPE_SHUFFLE,
            MESSAGE_DATA: {
                DATA_SHUFFLE_ENABLED: enableShuffle
            }
        }
        self.send_message(msg)


    # def play(self):
    #     """ Send the PLAY command. """
    #     self._send_command({MESSAGE_TYPE: TYPE_PLAY})

    # def pause(self):
    #     """ Send the PAUSE command. """
    #     self._send_command({MESSAGE_TYPE: TYPE_PAUSE})

    # def stop(self):
    #     """ Send the STOP command. """
    #     self._send_command({MESSAGE_TYPE: TYPE_STOP})

    # def rewind(self):
    #     """ Starts playing the media from the beginning. """
    #     self.seek(0)

    # def skip(self):
    #     """ Skips rest of the media. Values less then -5 behaved flaky. """
    #     self.seek(int(self.status.duration)-5)

    # def seek(self, position):
    #     """ Seek the media to a specific location. """
    #     self._send_command({MESSAGE_TYPE: TYPE_SEEK,
    #                         "currentTime": position,
    #                         "resumeState": "PLAYBACK_START"})

    # def enable_subtitle(self, track_id):
    #     """ Enable specific text track. """
    #     self._send_command({
    #         MESSAGE_TYPE: TYPE_EDIT_TRACKS_INFO,
    #         "activeTrackIds": [track_id]
    #     })

    # def disable_subtitle(self):
    #     """ Disable subtitle. """
    #     self._send_command({
    #         MESSAGE_TYPE: TYPE_EDIT_TRACKS_INFO,
    #         "activeTrackIds": []
    #     })

    def _handle_challenge(self, data):
        """ Processes the challenge message and sends a new identify message as response """
        #TODO python style
        challenge = data.get('data')['seed']
        msg = {
            "command": "identify",
            "data": {
                "auth_key": challenge
            }
        }
        self.send_message(msg)

    def _process_playlist(self, data):
        # data: {
        #         offset: offset,
        #         songs: playlist.slice(offset, limit)
        #     }
        self.logger.debug("DsAudio:Received playlist %s", data)

    def _process_media_status(self, data):
        """ Processes a status message. """
        self.status.update(data)

        self.logger.debug("DsAudio:Received status %s", data)
        self._fire_status_changed()

    def _fire_status_changed(self):
        """ Tells listeners of a changed status. """
        for listener in self._status_listeners:
            try:
                listener.new_media_status(self.status)
            except Exception:  # pylint: disable=broad-except
                pass

    # # pylint: disable=too-many-arguments
    # def play_media(self, url, content_type, title=None, thumb=None,
    #                current_time=0, autoplay=True,
    #                stream_type=STREAM_TYPE_BUFFERED,
    #                metadata=None):
    #     """
    #     Plays media on the Chromecast. Start default media receiver if not
    #     already started.

    #     Parameters:
    #     url: str - url of the media.
    #     content_type: str - mime type. Example: 'video/mp4'.
    #     title: str - title of the media.
    #     thumb: str - thumbnail image url.
    #     current_time: float - seconds from the beginning of the media
    #         to start playback.
    #     autoplay: bool - whether the media will automatically play.
    #     stream_type: str - describes the type of media artifact as one of the
    #         following: "NONE", "BUFFERED", "LIVE".
    #     metadata: dict - media metadata object, one of the following:
    #         GenericMediaMetadata, MovieMediaMetadata, TvShowMediaMetadata,
    #         MusicTrackMediaMetadata, PhotoMediaMetadata.

    #     Docs:
    #     https://developers.google.com/cast/docs/reference/messages#MediaData
    #     """

    #     self._socket_client.receiver_controller.launch_app(APP_MEDIA_RECEIVER)

    #     msg = {
    #         'media': {
    #             'contentId': url,
    #             'streamType': stream_type,
    #             'contentType': content_type,
    #             'metadata': metadata or {}
    #         },
    #         MESSAGE_TYPE: TYPE_LOAD,
    #         'currentTime': current_time,
    #         'autoplay': autoplay,
    #         'customData': {}
    #     }

    #     if title:
    #         msg['media']['metadata']['title'] = title

    #     if thumb:
    #         msg['media']['metadata']['thumb'] = thumb

    #         if 'images' not in msg['media']['metadata']:
    #             msg['media']['metadata']['images'] = []

    #         msg['media']['metadata']['images'].append({'url': thumb})

    #     self.send_message(msg, inc_session_id=True)

    def tear_down(self):
        """ Called when controller is destroyed. """
        super(MediaController, self).tear_down()

        self._status_listeners[:] = []


#     # message handling

#     def _json_from_message(self, message):
#         """ Parses a PB2 message into JSON format. """
#         return json.loads(message.payload_utf8)

#     def receive_message(self, message, data):
#         print(self._json_from_message(message))
#         message_type = data[MESSAGE_TYPE]
#         if message_type == "challenge":
#             self._handle_challenge(data)
#             return True
#         elif message_type == "status":
#             self._process_status(data)
#             return True

#         else:
#            return False

#     def _handle_challenge(self, data):
#         challenge = data.get('data')['seed']
#         msg = {
#             "command": "identify",
#             "data": {
#                 "auth_key": challenge
#             }
#         }
#         self.send_message(msg)

#     def _process_status(self, status):
#         """ Process latest status update. """
#         self.position = status.get('position')  # in seconds
#         self.buffered = status.get('buffered')  # in seconds
#         self.playing_index = status.get('playing_index')  # item in the list of songs in the album
#         self.song = status.get('song')  # song object

#         # 'song':{
#         #    'album':'538 Dance Smash Hits 2004, Volume 4: Autumn',
#         #    'type':'file',
#         #    'album_artist':'Various Artists',
#         #    'genre':'House/Euro House/Progressive Trance/Trance',
#         #    'artist':'Marly',
#         #    'composer':'',
#         #    'duration':199.7406,
#         #    'title':'You Never Know',
#         #    'cover_url':'[url_to_cover_image]',
#         #    'song_url':'[url_to_cover_image]',
#         #    'extra':{
#         #       'song_id':'music_4376',
#         #       'ds_id':'1370LSN001554'
#         #    }
#         # },
#         self.repeat_mode = status.get('repeat_mode')  # 'none','one','all',
#         self.shuffle_enabled = status.get('shuffle_enabled')  # true, false
#         self.playing_status = status.get('status')  # "playing";"pause";"stopped";
#         self.seekable = status.get('seekable')  # in seconds