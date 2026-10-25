"""
Controller to monitor audio group members.
"""

from __future__ import annotations

import abc
import logging
from collections.abc import Callable, Iterable, Set as AbstractSet
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict
from uuid import UUID

from . import BaseController, CallbackType, add_listener
from .media import MediaController, MediaStatusListener, MediaStatus
from .receiver import CastStatus, CastStatusListener
from ..const import CAST_TYPE_GROUP, MESSAGE_TYPE
from ..error import PyChromecastError, RequestFailed
from ..models import CastInfo
from ..response_handler import WaitResponse

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
TYPE_SET_PLAYBACK_DEVICES = "SET_PLAYBACK_DEVICES"


@dataclass(frozen=True)
class PlaybackSession:
    """Capabilities of the playback session attached to a multizone endpoint."""

    app_allows_grouping: bool | None
    is_video_content: bool | None
    stream_transfer_supported: bool | None


@dataclass(frozen=True)
class SessionEndpoint:
    """Endpoint which currently owns a playback session."""

    device_id: str
    host: str
    port: int
    session_id: str | None


@dataclass(frozen=True)
class PlaybackSessionUpdate:
    """Change of the set of devices playing a session.

    changed_devices may be empty, it's always empty on copies sent to other
    connections than the one which made the change.
    """

    name: str
    changed_devices: list[str]
    failed_devices: list[str]
    session_endpoint: SessionEndpoint | None


def _normalize_device_id(device_id: str) -> str:
    """Return device id in dashed form, devices report both forms."""
    try:
        return str(UUID(device_id))
    except ValueError:
        return device_id


def _parse_playback_session(data: dict[str, Any]) -> PlaybackSession:
    return PlaybackSession(
        data.get("appAllowsGrouping"),
        data.get("isVideoContent"),
        data.get("streamTransferSupported"),
    )


def _parse_session_update(data: dict[str, Any]) -> PlaybackSessionUpdate:
    endpoint = None
    if endpoint_data := data.get("sessionEndpoint"):
        endpoint = SessionEndpoint(
            _normalize_device_id(endpoint_data["deviceId"]),
            endpoint_data["ipAddress"],
            endpoint_data["port"],
            endpoint_data.get("sessionId"),
        )
    return PlaybackSessionUpdate(
        data.get("name", ""),
        [_normalize_device_id(uuid) for uuid in data.get("changedDevices", [])],
        [_normalize_device_id(uuid) for uuid in data.get("failedDevices", [])],
        endpoint,
    )


class GroupInfo(TypedDict):
    """Chromecast connection, multizone controller and monitor of a device or group."""

    chromecast: Chromecast
    controller: MultizoneController
    monitor: _EndpointMonitor


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

    def multizone_playback_session_updated(self, update: PlaybackSessionUpdate) -> None:
        """The set of devices playing the session has changed."""


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

    def multizone_sessions_changed(self) -> None:
        """The devices playing a playback session may have changed.

        Not abstract to keep existing listeners working.
        """


class _EndpointMonitor(
    CastStatusListener, ConnectionStatusListener, MultiZoneControllerListener
):
    """Monitor of a device or group managed by a MultizoneManager.

    Requests the multizone status when the playback session may have changed,
    it's only reported in response to a status request, and tells the manager.
    """

    def __init__(
        self,
        manager: MultizoneManager,
        cast: Chromecast,
        controller: MultizoneController,
    ) -> None:
        self._manager = manager
        self._mz = controller
        self._uuid = str(cast.uuid)
        self._session_id: str | None = None
        self._unregister = [
            cast.register_status_listener(self),
            cast.register_connection_listener(self),
            controller.register_listener(self),
        ]

    @property
    def session_id(self) -> str | None:
        """Return the id of the session the endpoint runs, from its status."""
        return self._session_id

    def stop(self) -> None:
        """Unregister the monitor."""
        for unregister in self._unregister:
            unregister()

    def _request_status(self) -> None:
        with suppress(PyChromecastError):
            self._mz.update_members()

    def new_cast_status(self, status: CastStatus) -> None:
        """Request status if the endpoint plays another session."""
        if status.session_id != self._session_id:
            self._session_id = status.session_id
            self._request_status()
            self._manager.on_sessions_changed()

    def new_connection_status(self, status: ConnectionStatus) -> None:
        """Request status when connected."""
        if status.status == CONNECTION_STATUS_CONNECTED:
            self._request_status()

    def multizone_member_added(self, group_uuid: str) -> None:
        """Members are only changed by a status, or a broadcast of the change."""

    def multizone_member_removed(self, group_uuid: str) -> None:
        """Members are only changed by a status, or a broadcast of the change."""

    def multizone_status_received(self) -> None:
        """Report the new status."""
        self._manager.on_sessions_changed()

    def multizone_playback_session_updated(self, update: PlaybackSessionUpdate) -> None:
        """Request status when the devices playing the session change."""
        self._request_status()


class _GroupMonitor(
    _EndpointMonitor,
    MediaStatusListener,
):
    """Monitor of a group managed by a MultizoneManager."""

    def __init__(
        self,
        manager: MultizoneManager,
        group_cast: Chromecast,
        controller: MultizoneController,
    ) -> None:
        """Initialize the monitor."""
        super().__init__(manager, group_cast, controller)
        self._unregister.append(
            group_cast.media_controller.register_status_listener(self)
        )

    def new_cast_status(self, status: CastStatus) -> None:
        """Handle reception of a new CastStatus."""
        super().new_cast_status(status)
        self._manager.on_group_cast_status(self._uuid, status)

    def new_media_status(self, status: MediaStatus) -> None:
        """Handle reception of a new MediaStatus."""
        self._manager.on_group_media_status(self._uuid, status)

    def load_media_failed(self, queue_item_id: int, error_code: int) -> None:
        """Called when load media failed."""

    def new_connection_status(self, status: ConnectionStatus) -> None:
        """Handle reception of a new ConnectionStatus."""
        super().new_connection_status(status)
        if status.status in (
            CONNECTION_STATUS_DISCONNECTED,
            CONNECTION_STATUS_LOST,
        ):
            self._mz.reset_members()

    def multizone_member_added(self, group_uuid: str) -> None:
        """Handle added audio group member."""
        self._manager.on_group_member_added(self._uuid, group_uuid)

    def multizone_member_removed(self, group_uuid: str) -> None:
        """Handle removed audio group member."""
        self._manager.on_group_member_removed(self._uuid, group_uuid)


class MultizoneManager:
    """Manage audio groups, and the playback sessions of devices."""

    def __init__(self) -> None:
        # Protect self._casts because it will be accessed from callbacks from
        # the casts' socket_client thread
        self._casts: dict[str, GroupMemberInfo] = {}
        self._groups: dict[str, GroupInfo] = {}

    def add_multizone(self, group_cast: Chromecast) -> MultizoneController:
        """Start managing a device or group.

        The members of a group are told about the group's status. Returns the
        multizone controller of the device or group, for registering listeners.
        """
        controller = MultizoneController(group_cast.uuid)
        monitor: _EndpointMonitor
        if group_cast.cast_type == CAST_TYPE_GROUP:
            monitor = _GroupMonitor(self, group_cast, controller)
        else:
            monitor = _EndpointMonitor(self, group_cast, controller)

        self._groups[str(group_cast.uuid)] = {
            "chromecast": group_cast,
            "controller": controller,
            "monitor": monitor,
        }
        group_cast.register_handler(controller)
        return controller

    def remove_multizone(self, group_uuid: UUID | str) -> None:
        """Stop managing a device or group"""
        group_uuid_str = str(group_uuid)
        group = self._groups.pop(group_uuid_str, None)
        # Inform all group members that they are no longer members
        if group is not None:
            group["controller"].reset_members()
            group["monitor"].stop()
            group["chromecast"].unregister_handler(group["controller"])
        for member in self._casts.values():
            member["group_memberships"].discard(group_uuid_str)
        self.on_sessions_changed()

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

    def get_multizone_mediacontroller(self, group_uuid: UUID | str) -> MediaController:
        """Get mediacontroller of a group"""
        return self._groups[str(group_uuid)]["chromecast"].media_controller

    def get_multizone_members(self, group_uuid: UUID | str) -> list[str]:
        """Return the members of a device or group.

        If it runs a playback session, the leader, the device running the
        session, is listed first if it's managed.
        """
        group = self._groups[str(group_uuid)]
        members = group["controller"].members
        monitor = group["monitor"]
        if monitor.session_id is None:
            return members

        def is_leader(uuid: str) -> bool:
            # The leader runs the session with the session id of the group,
            # the other members run sessions of their own
            member = self._groups.get(uuid)
            return (
                member is not None
                and member["monitor"].session_id == monitor.session_id
            )

        return sorted(members, key=lambda uuid: not is_leader(uuid))

    def get_session_endpoint(self, device: UUID) -> UUID | None:
        """Return the device or group owning the session a device or group plays.

        A device or group owning a session is its own endpoint. Returns None if
        the device plays no session. The devices playing the session are the
        members of the device or group.
        """
        owner = self._find_session_owner(device)
        if owner is None:
            return None
        return owner["chromecast"].uuid

    def update_session_devices(
        self,
        endpoint: UUID,
        *,
        add: AbstractSet[UUID] = frozenset(),
        remove: AbstractSet[UUID] = frozenset(),
        timeout: float = 10.0,
    ) -> PlaybackSessionUpdate | None:
        """Add devices to, or remove devices from, the session of an endpoint.

        The endpoint is the device or group owning the session, see
        get_session_endpoint. All devices must have been added with
        add_multizone. Blocks until the change is done, returns None if nothing
        changes.

        Raises RequestFailed if the endpoint isn't managed or runs no session, no
        device would be left, a device isn't managed or the change fails, and
        RequestTimeout if there's no response.
        """
        group = self._groups.get(str(endpoint))
        if group is None:
            raise RequestFailed(f"set playback devices, {endpoint} isn't managed")
        session_id = group["monitor"].session_id
        if session_id is None:
            raise RequestFailed(f"set playback devices, {endpoint} runs no session")
        controller = group["controller"]

        members = {UUID(member) for member in controller.members}
        target = (members - remove) | add
        if target == members:
            return None
        if not target:
            raise RequestFailed("set playback devices, no device would be left")

        devices = []
        for uuid in target:
            member = self._groups.get(str(uuid))
            if member is None:
                raise RequestFailed(
                    f"set playback devices, no address known for device {uuid}"
                )
            devices.append(member["chromecast"].cast_info)

        waiter = WaitResponse(timeout, "set playback devices")
        controller.set_playback_devices(
            session_id,
            devices,
            callback_function=waiter.callback,
        )
        waiter.wait_response()
        assert waiter.response is not None
        return _parse_session_update(waiter.response)

    def on_sessions_changed(self) -> None:
        """Tell the listeners the devices playing a session may have changed.

        Called by the monitors of the managed devices and groups.
        """
        for cast in list(self._casts.values()):
            for listener in list(cast["listeners"]):
                listener.multizone_sessions_changed()

    def on_group_cast_status(self, group_uuid: str, status: CastStatus) -> None:
        """Tell the members of a group about its new status.

        Called by the monitors of the managed groups.
        """
        for listener in self._member_listeners(group_uuid):
            listener.multizone_new_cast_status(group_uuid, status)

    def on_group_media_status(self, group_uuid: str, status: MediaStatus) -> None:
        """Tell the members of a group about its new media status.

        Called by the monitors of the managed groups.
        """
        for listener in self._member_listeners(group_uuid):
            listener.multizone_new_media_status(group_uuid, status)

    def on_group_member_added(self, group_uuid: str, member_uuid: str) -> None:
        """Tell a device it was added to a group.

        Called by the monitors of the managed groups.
        """
        member = self._member(member_uuid)
        member["group_memberships"].add(group_uuid)
        for listener in list(member["listeners"]):
            listener.added_to_multizone(group_uuid)

    def on_group_member_removed(self, group_uuid: str, member_uuid: str) -> None:
        """Tell a device it was removed from a group.

        Called by the monitors of the managed groups.
        """
        member = self._member(member_uuid)
        member["group_memberships"].discard(group_uuid)
        for listener in list(member["listeners"]):
            listener.removed_from_multizone(group_uuid)

    def _member(self, member_uuid: str) -> GroupMemberInfo:
        """Return the memberships and listeners of a device."""
        return self._casts.setdefault(
            member_uuid, {"listeners": [], "group_memberships": set()}
        )

    def _member_listeners(self, group_uuid: str) -> list[MultiZoneManagerListener]:
        """Return the listeners of the members of a group."""
        group = self._groups.get(group_uuid)
        if group is None:
            return []
        return [
            listener
            for member_uuid in group["controller"].members
            if member_uuid in self._casts
            for listener in list(self._casts[member_uuid]["listeners"])
        ]

    def _session_members(self, group: GroupInfo) -> list[str]:
        """Return the devices playing the session a device or group owns.

        Returns an empty list if it owns no session.
        """
        controller = group["controller"]
        # Followers report the session_id but no playback session
        if group["monitor"].session_id is None or controller.playback_session is None:
            return []
        members = controller.members
        # A dynamic group the session has left can keep reporting both for
        # minutes, but its only member is then another device
        if len(members) == 1 and members[0] != str(group["chromecast"].uuid):
            return []
        return members

    def _find_session_owner(self, device: UUID) -> GroupInfo | None:
        """Return the endpoint which owns the playback session a device plays.

        The device's own receiver status can't be used, the members of a group
        which don't host it run a session of their own. Returns None if the
        device plays no session.
        """
        device_str = str(device)
        # A group isn't a member of its own session
        own = self._groups.get(device_str)
        if own is not None and self._session_members(own):
            return own
        for endpoint in list(self._groups.values()):
            if device_str in self._session_members(endpoint):
                return endpoint
        return None


class MultizoneController(BaseController):
    """Controller to monitor audio group members."""

    def __init__(self, uuid: UUID) -> None:
        self._members: dict[str, str] = {}
        self._playback_session: PlaybackSession | None = None
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

    def register_listener(
        self, listener: MultiZoneControllerListener
    ) -> Callable[[], None]:
        """Register a listener for audio group changes. On update will call:
        listener.multizone_member_added(uuid)
        listener.multizone_member_removed(uuid)
        listener.multizone_status_received()
        listener.multizone_playback_session_updated(update)

        Returns a function which unregisters the listener.
        """
        return add_listener(self._status_listeners, listener)

    @property
    def members(self) -> list[str]:
        """Return a list of audio group members."""
        return list(self._members.keys())

    @property
    def playback_session(self) -> PlaybackSession | None:
        """Return the playback session reported in the last multizone status.

        None if no session is attached to this endpoint, also after a session
        update says the session moved to another endpoint.
        """
        return self._playback_session

    def reset_members(self) -> None:
        """Reset audio group members."""
        self._playback_session = None
        for uuid in list(self._members):
            self._remove_member(uuid)

    def update_members(self, *, callback_function: CallbackType | None = None) -> None:
        """Update audio group members."""
        self.send_message(
            {MESSAGE_TYPE: TYPE_GET_STATUS}, callback_function=callback_function
        )

    def get_casting_groups(self) -> None:
        """Send GET_CASTING_GROUPS message."""
        self.send_message({MESSAGE_TYPE: TYPE_GET_CASTING_GROUPS})

    def set_playback_devices(
        self,
        session_id: str,
        devices: Iterable[CastInfo],
        *,
        session_name: str | None = None,
        callback_function: CallbackType | None = None,
    ) -> None:
        """Set the devices playing a session, without interrupting playback.

        Must be sent to the endpoint which currently owns the session, devices
        is the complete set of devices which should play the session. The
        session may move to another endpoint, see
        PlaybackSessionUpdate.session_endpoint in the response.

        Depending on the app, moving the session to devices which aren't
        playing it may restart playback on them. Adding the new devices first
        and then removing the old ones doesn't.

        The callback is called with True and the PLAYBACK_SESSION_UPDATED
        response if all devices were changed, else with False and the response,
        for example INVALID_REQUEST if this isn't the session's endpoint.
        """
        device_list = [
            {
                "deviceId": str(device.uuid),
                "ipAddress": device.host,
                "port": device.port,
            }
            for device in devices
        ]
        if not device_list:
            raise ValueError("A session must play on at least one device")

        message: dict[str, Any] = {
            MESSAGE_TYPE: TYPE_SET_PLAYBACK_DEVICES,
            "sessionId": session_id,
            "deviceList": device_list,
        }
        if session_name is not None:
            message["sessionName"] = session_name

        def handle_response(msg_sent: bool, response: dict | None) -> None:
            if not callback_function:
                return
            callback_function(
                msg_sent
                and response is not None
                and response.get(MESSAGE_TYPE) == TYPE_SESSION_UPDATED
                and not response.get("failedDevices"),
                response,
            )

        self.send_message(message, callback_function=handle_response)

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

            playback_session = data["status"].get("playbackSession")
            self._playback_session = (
                _parse_playback_session(playback_session)
                if playback_session is not None
                else None
            )

            for listener in list(self._status_listeners):
                listener.multizone_status_received()

            return True

        if data[MESSAGE_TYPE] == TYPE_SESSION_UPDATED:
            # The devices playing the session changed, the session may have
            # moved to a new endpoint
            update = _parse_session_update(data)
            _LOGGER.debug("(%s) Playback session updated: %s", self._uuid, update)
            endpoint = update.session_endpoint
            if endpoint is not None and endpoint.device_id != self._uuid:
                _LOGGER.debug(
                    "(%s) Playback session moved to %s", self._uuid, endpoint.device_id
                )
                self._playback_session = None
            for listener in list(self._status_listeners):
                listener.multizone_playback_session_updated(update)
            return True

        if data[MESSAGE_TYPE] == TYPE_CASTING_GROUPS:
            # Answer to GET_CASTING_GROUPS
            return True

        return False

    def tear_down(self) -> None:
        """Called when controller is destroyed."""
        super().tear_down()

        self._status_listeners = []
