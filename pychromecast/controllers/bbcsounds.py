"""
Controller to interface with BBC Sounds.
"""

# Media ID can be found in the URL
# e.g. https://www.bbc.co.uk/sounds/live:bbc_radio_one

import logging
from typing import Any

from .media import STREAM_TYPE_BUFFERED, STREAM_TYPE_LIVE, BaseMediaPlayer
from ..config import APP_BBCSOUNDS

APP_NAMESPACE = "urn:x-cast:com.google.cast.media"


class BbcSoundsController(BaseMediaPlayer):
    """Controller to interact with BBC Sounds namespace."""

    def __init__(self) -> None:
        super().__init__(APP_BBCSOUNDS)
        self.logger = logging.getLogger(__name__)

    # pylint: disable-next=arguments-differ
    def quick_play(
        self,
        *,
        media_id: str,
        timeout: float,
        is_live: bool = False,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Quick Play helper for BBC Sounds media"""
        stream_type = STREAM_TYPE_LIVE if is_live else STREAM_TYPE_BUFFERED
        metadata_default = {"metadataType": 0, "title": ""}
        if metadata is None:
            metadata = metadata_default
        super().quick_play(
            media_id=media_id,
            media_type=None,
            stream_type=stream_type,
            metadata=metadata,
            timeout=timeout,
            **kwargs,
        )
