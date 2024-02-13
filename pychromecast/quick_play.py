""" Choose a controller and quick play """

from typing import Any

from . import Chromecast
from .controllers import QuickPlayController
from .controllers.bbciplayer import BbcIplayerController
from .controllers.bbcsounds import BbcSoundsController
from .controllers.bubbleupnp import BubbleUPNPController
from .controllers.homeassistant_media import HomeAssistantMediaController
from .controllers.media import DefaultMediaReceiverController
from .controllers.supla import SuplaController
from .controllers.yleareena import YleAreenaController
from .controllers.youtube import YouTubeController
from .controllers.shaka import ShakaController
from .controllers.nrktv import NrkTvController
from .controllers.nrkradio import NrkRadioController


def quick_play(  # pylint:disable=too-many-branches
    cast: Chromecast,
    app_name: str,
    data: dict[str, Any],
    timeout: float = 30.0,
) -> None:
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

    controller: QuickPlayController
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
    elif app_name == "shaka":
        controller = ShakaController()
    elif app_name == "nrktv":
        controller = NrkTvController()
    elif app_name == "nrkradio":
        controller = NrkRadioController()
    else:
        raise NotImplementedError()

    cast.register_handler(controller)

    try:
        controller.quick_play(**data, timeout=timeout)
    finally:
        cast.unregister_handler(controller)
