"""
Controller to monitor audio group members.
"""
import logging

from . import BaseController

_LOGGER = logging.getLogger(__name__)

MESSAGE_TYPE = "type"
MULTIZONE_NAMESPACE = "urn:x-cast:com.google.cast.multizone"
TYPE_DEVICE_ADDED = "DEVICE_ADDED"
TYPE_DEVICE_UPDATED = "DEVICE_UPDATED"
TYPE_DEVICE_REMOVED = "DEVICE_REMOVED"
TYPE_GET_STATUS = "GET_STATUS"
TYPE_MULTIZONE_STATUS = "MULTIZONE_STATUS"


class MultizoneController(BaseController):
    """ Controller to monitor audio group members. """

    def __init__(self, uuid, callback=None):
        self._members = {}
        self._callback = callback
        self._uuid = uuid
        super(MultizoneController, self).__init__(MULTIZONE_NAMESPACE,
                                                  target_platform=True)

    def _add_member(self, uuid, name):
        if uuid not in self._members:
            self._members[uuid] = name
            _LOGGER.debug("(%s) Added member %s(%s), members: %s",
                          self._uuid, uuid, name, self._members)
            if self._callback:
                self._callback.multizone_member_added(uuid)

    def _remove_member(self, uuid):
        name = self._members.pop(uuid, '<Unknown>')
        _LOGGER.debug("(%s) Removed member %s(%s), members: %s",
                      self._uuid, uuid, name, self._members)
        if self._callback:
            self._callback.multizone_member_removed(uuid)

    def get_members(self):
        """ Get audio group members. """
        self.send_message({MESSAGE_TYPE: TYPE_GET_STATUS})

    def receive_message(self, message, data):
        """ Called when a media message is received. """
        if data[MESSAGE_TYPE] == TYPE_DEVICE_ADDED:
            uuid = data['device']['deviceId']
            name = data['device']['name']
            self._add_member(uuid, name)
            return True

        if data[MESSAGE_TYPE] == TYPE_DEVICE_REMOVED:
            uuid = data['deviceId']
            self._remove_member(uuid)
            return True

        if data[MESSAGE_TYPE] == TYPE_DEVICE_UPDATED:
            uuid = data['device']['deviceId']
            name = data['device']['name']
            self._add_member(uuid, name)
            return True

        if data[MESSAGE_TYPE] == TYPE_MULTIZONE_STATUS:
            members = data['status']['devices']
            members = \
                {member['deviceId']: member['name'] for member in members}
            removed_members = \
                list(set(self._members.keys())-set(members.keys()))
            added_members = list(set(members.keys())-set(self._members.keys()))
            _LOGGER.debug("(%s) Added members %s, Removed members: %s",
                          self._uuid, added_members, removed_members)

            for uuid in removed_members:
                self._remove_member(uuid)
            for uuid in added_members:
                self._add_member(uuid, members[uuid])

            return True

        return False
