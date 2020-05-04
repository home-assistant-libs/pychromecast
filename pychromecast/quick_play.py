""" Choose a controller and quick play """

from .controllers.youtube import YouTubeController
from .controllers.supla import SuplaController


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
            media_type: string,
                Type of the media identified by `media_id`. e.g. "program" if the media is a
                program name instead of a direct item id.
            enqueue: boolean,
                Enqueue the media to the current playlist, if possible.
            index: string,
                Play index x of matching media. "random" should also be allowed.
            extra1: string,
            extra2: string,
                Extra lines for controller-specific values.

    """

    if app_name == "youtube":
        controller = YouTubeController()
        kwargs = {
            "video_id": data.pop("media_id"),
            "enqueue": data.pop("enqueue", False),
            "playlist_id": data.pop("extra1", None),
        }
    elif app_name == "supla":
        controller = SuplaController()
        kwargs = {
            "media_id": data.pop("media_id"),
            "is_live": data.pop("extra2", None),
        }
    else:
        raise NotImplementedError()

    cast.register_handler(controller)
    controller.quick_play(**kwargs)

    if data:
        controller.logger.warning("Unused data in quick_play: %s", data)
