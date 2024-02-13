"""
Controller to monitor audio group members.
"""

from __future__ import annotations

import abc
import logging
from typing import TYPE_CHECKING, TypedDict
from uuid import UUID

from . import BaseController
from .media import MediaController, MediaStatusListener, MediaStatus
from .receiver import CastStatus, CastStatusListener
from ..const import MESSAGE_TYPE

# pylint: disable-next=no-name-in-module
from ..generated.cast_channel_pb2 import CastMessage
from ..socket_client import (
    CONNECTION_STATUS_CONNECTED,
    CONNECTION_STATUS_DISCONNECTED,
    CONNECTION_STATUS_LOST,
    ConnectionStatus,
    ConnectionStatusListener,
)

if TYPE_CHECKING:
    from .. import Chromecast

_LOGGER = logging.getLogger(__name__)

MULTIZONE_NAMESPACE = "urn:x-cast:com.google.cast.multizone"
TYPE_CASTING_GROUPS = "CASTING_GROUPS"
TYPE_DEVICE_ADDED = "DEVICE_ADDED"
TYPE_DEVICE_UPDATED = "DEVICE_UPDATED"
TYPE_DEVICE_REMOVED = "DEVICE_REMOVED"
TYPE_GET_CASTING_GROUPS = "GET_CASTING_GROUPS"
TYPE_GET_STATUS = "GET_STATUS"
TYPE_MULTIZONE_STATUS = "MULTIZONE_STATUS"
TYPE_SESSION_UPDATED = "PLAYBACK_SESSION_UPDATED"


class GroupInfo(TypedDict):
    """Chromecast connection and listener for a group."""

    chromecast: Chromecast
    listener: Listener


class GroupMemberInfo(TypedDict):
    """Group memberships and listener for a group."""

    group_memberships: set[str]
    listeners: list[MultiZoneManagerListener]


class MultiZoneControllerListener(abc.ABC):
    """Listener for receiving audio group events."""

    @abc.abstractmethod
    def multizone_member_added(self, group_uuid: str) -> None:
        """The cast has been added to group identified by group_uuid."""

    @abc.abstractmethod
    def multizone_member_removed(self, group_uuid: str) -> None:
        """The cast has been removed from group identified by group_uuid."""

    @abc.abstractmethod
    def multizone_status_received(self) -> None:
        """Multizone status has been updated."""


class MultiZoneManagerListener(abc.ABC):
    """Listener for receiving audio group events for a cast device."""

    @abc.abstractmethod
    def added_to_multizone(self, group_uuid: str) -> None:
        """The cast has been added to group identified by group_uuid."""

    @abc.abstractmethod
    def removed_from_multizone(self, group_uuid: str) -> None:
        """The cast has been removed from group identified by group_uuid."""

    @abc.abstractmethod
    def multizone_new_media_status(
        self, group_uuid: str, media_status: MediaStatus
    ) -> None:
        """The group identified by group_uuid, of which the cast is a member, has new media status."""

    @abc.abstractmethod
    def multizone_new_cast_status(
        self, group_uuid: str, cast_status: CastStatus
    ) -> None:
        """The group identified by group_uuid, of which the cast is a member, has new status."""


class Listener(
    CastStatusListener,
    ConnectionStatusListener,
    MediaStatusListener,
    MultiZoneControllerListener,
):
    """Callback handler."""

    def __init__(
        self, group_cast: Chromecast, casts: dict[str, GroupMemberInfo]
    ) -> None:
        """Initialize the listener."""
        self._casts = casts
        group_cast.register_status_listener(self)
        group_cast.media_controller.register_status_listener(self)
        group_cast.register_connection_listener(self)
        self._mz = MultizoneController(group_cast.uuid)
        self._mz.register_listener(self)
        self._group_uuid = str(group_cast.uuid)
        group_cast.register_handler(self._mz)

    def new_cast_status(self, status: CastStatus) -> None:
        """Handle reception of a new CastStatus."""
        casts = self._casts
        group_members = self._mz.members
        for member_uuid in group_members:
            if member_uuid not in casts:
                continue
            for listener in list(casts[member_uuid]["listeners"]):
                listener.multizone_new_cast_status(self._group_uuid, status)

    def new_media_status(self, status: MediaStatus) -> None:
        """Handle reception of a new MediaStatus."""
        casts = self._casts
        group_members = self._mz.members
        for member_uuid in group_members:
            if member_uuid not in casts:
                continue
            for listener in list(casts[member_uuid]["listeners"]):
                listener.multizone_new_media_status(self._group_uuid, status)

    def load_media_failed(self, queue_item_id: int, error_code: int) -> None:
        """Called when load media failed."""

    def new_connection_status(self, status: ConnectionStatus) -> None:
        """Handle reception of a new ConnectionStatus."""
        if status.status == CONNECTION_STATUS_CONNECTED:
            self._mz.update_members()
        if status.status in (
            CONNECTION_STATUS_DISCONNECTED,
            CONNECTION_STATUS_LOST,
        ):
            self._mz.reset_members()

    def multizone_member_added(self, group_uuid: str) -> None:
        """Handle added audio group member."""
        casts = self._casts
        if group_uuid not in casts:
            casts[group_uuid] = {"listeners": [], "group_memberships": set()}
        casts[group_uuid]["group_memberships"].add(self._group_uuid)
        for listener in list(casts[group_uuid]["listeners"]):
            listener.added_to_multizone(self._group_uuid)

    def multizone_member_removed(self, group_uuid: str) -> None:
        """Handle removed audio group member."""
        casts = self._casts
        if group_uuid not in casts:
            casts[group_uuid] = {"listeners": [], "group_memberships": set()}
        casts[group_uuid]["group_memberships"].discard(self._group_uuid)
        for listener in list(casts[group_uuid]["listeners"]):
            listener.removed_from_multizone(self._group_uuid)

    def multizone_status_received(self) -> None:
        """Handle reception of audio group status."""


class MultizoneManager:
    """Manage audio groups."""

    def __init__(self) -> None:
        # Protect self._casts because it will be accessed from callbacks from
        # the casts' socket_client thread
        self._casts: dict[str, GroupMemberInfo] = {}
        self._groups: dict[str, GroupInfo] = {}

    def add_multizone(self, group_cast: Chromecast) -> None:
        """Start managing a group"""
        self._groups[str(group_cast.uuid)] = {
            "chromecast": group_cast,
            "listener": Listener(group_cast, self._casts),
        }

    def remove_multizone(self, group_uuid: UUID) -> None:
        """Stop managing a group"""
        group_uuid_str = str(group_uuid)
        group = self._groups.pop(group_uuid_str, None)
        # Inform all group members that they are no longer members
        if group is not None:
            group["listener"]._mz.reset_members()  # pylint: disable=protected-access
        for member in self._casts.values():
            member["group_memberships"].discard(group_uuid_str)

    def register_listener(
        self, member_uuid: UUID, listener: MultiZoneManagerListener
    ) -> None:
        """Register a listener for audio group changes of cast uuid.
        On update will call:
        listener.added_to_multizone(group_uuid)
            The cast has been added to group uuid
        listener.removed_from_multizone(group_uuid)
            The cast has been removed from group uuid
        listener.multizone_new_media_status(group_uuid, media_status)
            The group uuid, of which the cast is a member, has new status
        listener.multizone_new_cast_status(group_uuid, cast_status)
            The group uuid, of which the cast is a member, has new status
        """
        member_uuid_str = str(member_uuid)
        if member_uuid_str not in self._casts:
            self._casts[member_uuid_str] = {"listeners": [], "group_memberships": set()}
        self._casts[member_uuid_str]["listeners"].append(listener)

    def deregister_listener(
        self, member_uuid: UUID, listener: MultiZoneManagerListener
    ) -> None:
        """Deregister listener for audio group changes of cast uuid."""
        self._casts[str(member_uuid)]["listeners"].remove(listener)

    def get_multizone_memberships(self, member_uuid: UUID) -> list[str]:
        """Return a list of audio groups in which cast member_uuid is a member"""
        return list(self._casts[str(member_uuid)]["group_memberships"])

    def get_multizone_mediacontroller(self, group_uuid: UUID) -> MediaController:
        """Get mediacontroller of a group"""
        return self._groups[str(group_uuid)]["chromecast"].media_controller


class MultizoneController(BaseController):
    """Controller to monitor audio group members."""

    def __init__(self, uuid: UUID) -> None:
        self._members: dict[str, str] = {}
        self._status_listeners: list[MultiZoneControllerListener] = []
        self._uuid = str(uuid)
        super().__init__(MULTIZONE_NAMESPACE, target_platform=True)

    def _add_member(self, uuid: str, name: str) -> None:
        if uuid not in self._members:
            self._members[uuid] = name
            _LOGGER.debug(
                "(%s) Added member %s(%s), members: %s",
                self._uuid,
                uuid,
                name,
                self._members,
            )
            for listener in list(self._status_listeners):
                listener.multizone_member_added(uuid)

    def _remove_member(self, uuid: str) -> None:
        name = self._members.pop(uuid, "<Unknown>")
        _LOGGER.debug(
            "(%s) Removed member %s(%s), members: %s",
            self._uuid,
            uuid,
            name,
            self._members,
        )
        for listener in list(self._status_listeners):
            listener.multizone_member_removed(uuid)

    def register_listener(self, listener: MultiZoneControllerListener) -> None:
        """Register a listener for audio group changes. On update will call:
        listener.multizone_member_added(uuid)
        listener.multizone_member_removed(uuid)
        listener.multizone_status_received()
        """
        self._status_listeners.append(listener)

    @property
    def members(self) -> list[str]:
        """Return a list of audio group members."""
        return list(self._members.keys())

    def reset_members(self) -> None:
        """Reset audio group members."""
        for uuid in list(self._members):
            self._remove_member(uuid)

    def update_members(self) -> None:
        """Update audio group members."""
        self.send_message({MESSAGE_TYPE: TYPE_GET_STATUS})

    def get_casting_groups(self) -> None:
        """Send GET_CASTING_GROUPS message."""
        self.send_message({MESSAGE_TYPE: TYPE_GET_CASTING_GROUPS})

    def receive_message(  # pylint: disable=too-many-return-statements
        self, _message: CastMessage, data: dict
    ) -> bool:
        """Called when a multizone message is received."""
        if data[MESSAGE_TYPE] == TYPE_DEVICE_ADDED:
            uuid = data["device"]["deviceId"]
            name = data["device"]["name"]
            self._add_member(uuid, name)
            return True

        if data[MESSAGE_TYPE] == TYPE_DEVICE_REMOVED:
            uuid = data["deviceId"]
            self._remove_member(uuid)
            return True

        if data[MESSAGE_TYPE] == TYPE_DEVICE_UPDATED:
            uuid = data["device"]["deviceId"]
            name = data["device"]["name"]
            self._add_member(uuid, name)
            return True

        if data[MESSAGE_TYPE] == TYPE_MULTIZONE_STATUS:
            members = data["status"]["devices"]
            members = {member["deviceId"]: member["name"] for member in members}
            removed_members = list(set(self._members.keys()) - set(members.keys()))
            added_members = list(set(members.keys()) - set(self._members.keys()))
            _LOGGER.debug(
                "(%s) Added members %s, Removed members: %s",
                self._uuid,
                added_members,
                removed_members,
            )

            for uuid in removed_members:
                self._remove_member(uuid)
            for uuid in added_members:
                self._add_member(uuid, members[uuid])

            for listener in list(self._status_listeners):
                listener.multizone_status_received()

            return True

        if data[MESSAGE_TYPE] == TYPE_SESSION_UPDATED:
            # A temporary group has been formed
            return True

        if data[MESSAGE_TYPE] == TYPE_CASTING_GROUPS:
            # Answer to GET_CASTING_GROUPS
            return True

        return False

    def tear_down(self) -> None:
        """Called when controller is destroyed."""
        super().tear_down()

        self._status_listeners = []
