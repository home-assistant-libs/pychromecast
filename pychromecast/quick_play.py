""" Choose a controller and quick play """

from .controllers.youtube import YouTubeController
from .controllers.supla import SuplaController


def quick_play(cast, app_name, data):
    """
    CAST_APP_SCHEMA = {
        vol.Required('app_name', default=""): cv.string,
        vol.Required('data'): vol.Schema({
            vol.Required("media_id"): cv.string,
            vol.Optional("media_type"): cv.string,
            vol.Optional("enqueue", default=False): cv.boolean,
            vol.Optional("index"): cv.string,
            vol.Optional("extra1"): cv.string,
            vol.Optional("extra2"): cv.string,
        }),
    }
    """

    if app_name == "youtube":
        controller = YouTubeController()
        kwargs = {
            'video_id': data.pop('media_id'),
            'enqueue': data.pop('enqueue', False),
            'playlist_id': data.pop('extra1', None),
        }
    elif app_name == 'supla':
        controller = SuplaController()
        kwargs = {
            'media_id': data.pop('media_id'),
            'is_live': data.pop('extra2', None),
        }
    else:
        raise NotImplementedError()

    cast.wait()
    cast.register_handler(controller)
    controller.quick_play(**kwargs)

    if data:
        controller.logger.warning('Unused data in quick_play: %s', data)
