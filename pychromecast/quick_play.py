""" Choose a controller and quick play """

from .controllers.bbciplayer import BbcIplayerController
from .controllers.bbcsounds import BbcSoundsController
from .controllers.bubbleupnp import BubbleUPNPController
from .controllers.homeassistant_media import HomeAssistantMediaController
from .controllers.media import DefaultMediaReceiverController
from .controllers.supla import SuplaController
from .controllers.yleareena import YleAreenaController
from .controllers.youtube import YouTubeController


def quick_play(cast, app_name, data):
    """
    Given a Chromecast connection, launch the app `app_name` and start playing media
    based on parameters defined in `data`.

    :param cast: Chromecast connection to cast to
    :param app_name: App name "slug" to cast
    :param data: Data to send to the app controller. Must contain "media_id", and other
        values can be passed depending on the controller.
    :type cast: Chromecast
    :type app_name: string
    :type data: dict

    `data` can contain the following keys:
        media_id: string (Required)
            Primary identifier of the media
        media_type: string
            Type of the media identified by `media_id`. e.g. "program" if the media is a
            program name instead of a direct item id.
            When using a regular media controller (e.g. BubbleUPNP) this should be the
            content_type ('audio/mp3')
        enqueue: boolean
            Enqueue the media to the current playlist, if possible.
        index: string
            Play index x of matching media. "random" should also be allowed.
        audio_lang: string
            Audio language (3 characters for YleAreena)
        text_lang: string
            Subtitle language (3 characters for YleAreena)

    Youtube-specific:
        playlist_id: string
            Youtube playlist id

    Supla-specific:
        is_live: boolean
            Whether the media is a livestream

    Media controller (BubbleUPNP)-specific:
        stream_type: string
            "BUFFERED" or "LIVE"
    """

    if app_name == "bbciplayer":
        controller = BbcIplayerController()
    elif app_name == "bbcsounds":
        controller = BbcSoundsController()
    elif app_name == "bubbleupnp":
        controller = BubbleUPNPController()
    elif app_name == "default_media_receiver":
        controller = DefaultMediaReceiverController()
    elif app_name == "homeassistant_media":
        controller = HomeAssistantMediaController()
    elif app_name == "supla":
        controller = SuplaController()
    elif app_name == "yleareena":
        controller = YleAreenaController()
    elif app_name == "youtube":
        controller = YouTubeController()
    else:
        raise NotImplementedError()

    cast.register_handler(controller)

    controller.quick_play(**data)

    cast.unregister_handler(controller)
