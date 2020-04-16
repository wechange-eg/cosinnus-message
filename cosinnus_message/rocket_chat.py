import logging
import mimetypes
import os
import re

from cosinnus.models.group_extra import CosinnusSociety, CosinnusProject
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _

from rocketchat_API.APIExceptions.RocketExceptions import RocketAuthenticationException
from rocketchat_API.rocketchat import RocketChat as RocketChatAPI
from cosinnus.models.group import MEMBERSHIP_MEMBER, MEMBERSHIP_ADMIN,\
    CosinnusPortal
from cosinnus.models.profile import PROFILE_SETTING_ROCKET_CHAT_ID, PROFILE_SETTING_ROCKET_CHAT_USERNAME

logger = logging.getLogger(__name__)

ROCKETCHAT_USER_CONNECTION_CACHE_KEY = 'cosinnus/core/portal/%d/rocketchat-user-connection/%s/'


def get_cached_rocket_connection(user, password, server_url, reset=False):
    """ Retrieves a cached rocketchat connection or creates a new one and caches it.
        @param reset: Resets the cached connection and connects a fresh one immediately """
    cache_key = ROCKETCHAT_USER_CONNECTION_CACHE_KEY % (CosinnusPortal.get_current().id, user)
    
    if reset:
        cache.delete(cache_key)
        rocket_connection = None
    else:
        rocket_connection = cache.get(cache_key)
    
    if rocket_connection is None:
        rocket_connection = RocketChat(user=user, password=password, server_url=server_url)
        cache.set(cache_key, rocket_connection)
    return rocket_connection


def delete_cached_rocket_connection(user):
    """ Deletes a cached rocketchat connection or creates a new one and caches it """
    cache_key = ROCKETCHAT_USER_CONNECTION_CACHE_KEY % (CosinnusPortal.get_current().id, user)
    


class RocketChat(RocketChatAPI):

    def rooms_upload(self, rid, file, **kwargs):
        """
        Overwrite base method to allow filename and mimetye kwargs
        """
        filename = kwargs.pop('filename', os.path.basename(file))
        mimetype = kwargs.pop('mimetype', mimetypes.guess_type(file)[0])
        files = {
            'file': (filename, open(file, 'rb'), mimetype),
        }
        return self.__call_api_post('rooms.upload/' + rid, kwargs=kwargs, use_json=False, files=files)


class RocketChatConnection:

    rocket = None
    stdout, stderr = None, None

    def __init__(self, user=settings.COSINNUS_CHAT_USER, password=settings.COSINNUS_CHAT_PASSWORD,
                 url=settings.COSINNUS_CHAT_BASE_URL, stdout=None, stderr=None):
        # get a cached version of the rocket connection
        self.rocket = get_cached_rocket_connection(user, password, url)
        
        if stdout:
            self.stdout = stdout
        if stderr:
            self.stderr = stderr
    
    def settings_update(self):
        for setting, value in settings.COSINNUS_CHAT_SETTINGS.items():
            response = self.rocket.settings_update(setting, value).json()
            if not response.get('success'):
                self.stderr.write(str(response))

    def users_sync(self):
        """
        Sync users
        :return:
        """
        # Get existing rocket users
        rocket_users = {}
        rocket_emails_usernames = {}
        size = 100
        offset = 0
        while True:
            response = self.rocket.users_list(size=size, offset=offset).json()
            if not response.get('success'):
                self.stderr.write('users_sync', response)
                break
            if response['count'] == 0:
                break

            for rocket_user in response['users']:
                rocket_users[rocket_user['username']] = rocket_user
                for email in rocket_user.get('emails', []):
                    if not email.get('address'):
                        continue
                    rocket_emails_usernames[email['address']] = rocket_user['username']
            offset += response['count']

        # Check active users in DB
        users = get_user_model().objects.filter(is_active=True)
        count = len(users)
        for i, user in enumerate(users):
            self.stdout.write('User %i/%i' % (i, count), ending='\r')
            self.stdout.flush()

            if not user.cosinnus_profile:
                continue
            profile = user.cosinnus_profile
            rocket_username = profile.rocket_username

            rocket_user = rocket_users.get(rocket_username)

            # User with different username but same email address exists?
            if not rocket_user and user.email in rocket_emails_usernames.keys():
                # Change username in DB
                rocket_username = rocket_emails_usernames.get(user.email)
                rocket_user = rocket_users.get(rocket_username)

                profile.settings[PROFILE_SETTING_ROCKET_CHAT_USERNAME] = rocket_username
                profile.save(update_fields=['settings'])

            # Username exists?
            if rocket_user:
                changed = False
                # TODO: Introducing User.updated_at would improve performance here
                rocket_emails = (e['address'] for e in rocket_user.get('emails'))
                # Email address changed?
                if user.email not in rocket_emails:
                    changed = True
                # Name changed?
                elif user.get_full_name() != rocket_user.get('name'):
                    changed = True
                elif rocket_username != rocket_user.get('username'):
                    changed = True
                # Avatar changed?
                else:
                    rocket_avatar_url = self.rocket.users_get_avatar(username=rocket_username)
                    profile_avatar_url = user.cosinnus_profile.avatar.url if user.cosinnus_profile.avatar else ""
                    if profile_avatar_url != rocket_avatar_url:
                        changed = True
                if changed:
                    self.users_update(user)

            else:
                self.users_create(user)

    def groups_sync(self):
        """
        Sync groups
        :return:
        """
        # Sync WECHANGE groups
        groups = CosinnusSociety.objects.filter(is_active=True)
        groups = groups.filter(Q(**{f'settings__{PROFILE_SETTING_ROCKET_CHAT_ID}_general__isnull': True}) |
                               Q(**{f'settings__{PROFILE_SETTING_ROCKET_CHAT_ID}_general': None}))
        count = len(groups)
        for i, group in enumerate(groups):
            self.stdout.write('Group %i/%i' % (i, count), ending='\r')
            self.stdout.flush()
            self.groups_create(group)

        # Sync WECHANGE projects
        projects = CosinnusProject.objects.filter(is_active=True)
        projects = projects.filter(Q(**{'settings__{PROFILE_SETTING_ROCKET_CHAT_ID}_general__isnull': True}) |
                                   Q(**{'settings__{PROFILE_SETTING_ROCKET_CHAT_ID}_general': None}))
        count = len(projects)
        for i, project in enumerate(projects):
            self.stdout.write('Project %i/%i' % (i, count), ending='\r')
            self.stdout.flush()
            self.groups_create(project)

    def get_user_id(self, user):
        """
        Returns Rocket.Chat ID from user settings or Rocket.Chat API
        :param user:
        :return:
        """
        profile = user.cosinnus_profile
        if not profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_ID):
            username = profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_USERNAME)
            if not username:
                logger.error('get_user_id', 'no username given')
                return
            response = self.rocket.users_info(username=username).json()
            if not response.get('success'):
                logger.error('get_user_id', response)
                return
            user_data = response.get('user')
            rocket_chat_id = user_data.get('_id')
            profile.settings[PROFILE_SETTING_ROCKET_CHAT_ID] = rocket_chat_id
            # Update profile settings without triggering signals to prevent cycles
            type(profile).objects.filter(pk=profile.pk).update(settings=profile.settings)
        return profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_ID)

    def get_group_id(self, group, type='general'):
        """
        Returns Rocket.Chat ID from user settings or Rocket.Chat API
        :param user:
        :return:
        """
        key = f'{PROFILE_SETTING_ROCKET_CHAT_ID}_{type}'
        if not group.settings.get(key):
            if type == 'general':
                group_name = settings.COSINNUS_CHAT_GROUP_GENERAL % group.slug
            else:
                group_name = settings.COSINNUS_CHAT_GROUP_NEWS % group.slug
            response = self.rocket.groups_info(room_name=group_name).json()
            if not response.get('success'):
                logger.error('get_group_id', response)
                return
            user_data = response.get('user')
            rocket_chat_id = user_data.get('_id')
            group.settings[key] = rocket_chat_id
            # Update group settings without triggering signals to prevent cycles
            type(group).objects.filter(pk=group.pk).update(settings=group.settings)
        return group.settings.get(key)

    def users_create(self, user, request=None):
        """
        Create user with name, email address and avatar
        :return:
        """
        if not user.cosinnus_profile:
            return
        profile = user.cosinnus_profile
        data = {
            "email": user.email,
            "name": user.get_full_name(),
            "password": user.password,
            "username": profile.rocket_username,
            "active": user.is_active,
            "verified": True,
        }
        response = self.rocket.users_create(**data).json()
        if not response.get('success'):
            logger.error('users_create', response)

        # Save Rocket.Chat User ID to user instance
        user_id = response.get('user', {}).get('_id')
        profile = user.cosinnus_profile
        profile.settings[PROFILE_SETTING_ROCKET_CHAT_ID] = user_id
        # Update profile settings without triggering signals to prevent cycles
        type(profile).objects.filter(pk=profile.pk).update(settings=profile.settings)

    def users_update_username(self, rocket_username, user):
        """
        Updates username
        :return:
        """
        # Get user ID
        profile = user.cosinnus_profile
        if not profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_ID):
            response = self.rocket.users_info(username=rocket_username).json()
            if not response.get('success'):
                logger.error('get_user_id', response)
                return
            user_data = response.get('user')
            user_id = user_data.get('_id')
            profile.settings[PROFILE_SETTING_ROCKET_CHAT_ID] = user_id
            # Update profile settings without triggering signals to prevent cycles
            type(profile).objects.filter(pk=profile.pk).update(settings=profile.settings)
        user_id = profile.settings[PROFILE_SETTING_ROCKET_CHAT_ID]
        if not user_id:
            return

        # Update username
        response = self.rocket.users_update(user_id=user_id, username=profile.rocket_username).json()
        if not response.get('success'):
            logger.error('users_update', response)

    def users_update(self, user, request=None):
        """
        Updates user name, email address and avatar
        :return:
        """
        user_id = self.get_user_id(user)
        if not user_id:
            return

        # Get user information and ID
        response = self.rocket.users_info(user_id=user_id)
        if not response.status_code == 200:
            logger.error('users_info', response)
            return
        response = response.json()
        if not response.get('success'):
            logger.error('users_info', response)
            return
        user_data = response.get('user')

        # Update name and email address
        if user_data.get('name') != user.get_full_name() or user_data.get('email') != user.email:
            profile = user.cosinnus_profile
            data = {
                "username": profile.rocket_username,
                "name": user.get_full_name(),
                "email": user.email,
                #"active": user.is_active,
                "password": user.password,
            }
            response = self.rocket.users_update(user_id=user_id, **data).json()
            if not response.get('success'):
                logger.error('users_update', response)

        # Update Avatar URL
        avatar_url = user.cosinnus_profile.avatar.url if user.cosinnus_profile.avatar else ''
        if avatar_url:
            if request:
                avatar_url = request.build_absolute_uri(avatar_url)
            else:
                avatar_url = f'{settings.COSINNUS_SITE_PROTOCOL}://{settings.COSINNUS_PORTAL_URL}{avatar_url}'
            response = self.rocket.users_set_avatar(avatar_url, userId=user_id).json()
            if not response.get('success'):
                logger.error('users_update', 'users_set_avatar', response)

    def users_disable(self, user):
        """
        Set user to inactive
        :return:
        """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        data = {
            "active": False,
        }
        response = self.rocket.users_update(user_id=user_id, **data).json()
        if not response.get('success'):
            logger.error('users_disable', response)

    def users_enable(self, user):
        """
        Set user to active
        :return:
        """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        data = {
            "active": True,
        }
        response = self.rocket.users_update(user_id=user_id, **data).json()
        if not response.get('success'):
            logger.error('users_enable', response)

    def groups_request(self, group, user):
        """
        Returns name of group if user is member of group, otherwise creates private group for group request
        (with user and group admins as members) and returns group name
        :param group:
        :param user:
        :return:
        """
        group_name = ''
        if group.is_member(user):
            # Return Rocket.Chat group url
            room_id = group.settings.get(f'{PROFILE_SETTING_ROCKET_CHAT_ID}_general')
            response = self.rocket.groups_info(room_id=room_id).json()
            if not response.get('success'):
                logger.error('groups_request', 'groups_info', response)
            group_name = response.get('group', {}).get('name')
        else:
            # Create private group
            group_name = f'{group.slug}-{get_random_string(7)}'
            profile = user.cosinnus_profile
            members = [str(u.id) for u in group.actual_admins] + [profile.rocket_username, ]
            response = self.rocket.groups_create(group_name, members=members).json()
            if not response.get('success'):
                logger.error('groups_request', 'groups_create', response)
            group_name = response.get('group', {}).get('name')
            room_id = response.get('group', {}).get('_id')

            # Make user moderator of group
            user_id = user.cosinnus_profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_ID)
            if user_id:
                response = self.rocket.groups_add_moderator(room_id=room_id, user_id=profile.rocket_username).json()
                if not response.get('success'):
                    logger.error('groups_request', 'groups_add_moderator', response)

            # Set description of group
            desc = ''
            if group.type == group.TYPE_PROJECT:
                desc = _('Request about your project "%(group_name)s"')
            else:
                desc = _('Request about your group "%(group_name)s"')
            response = self.rocket.groups_set_description(room_id=room_id,
                                                          description=desc % {'group_name': group.name}).json()
            if not response.get('success'):
                logger.error('groups_request', 'groups_set_description', response)

        return group_name

    def groups_create(self, group):
        """
        Create default channels for group or project:
        1. #slug-general: Private group with all members
        2. #slug-news: Private ready-only group with all members, new notes appear here.
        :param group:
        :return:
        """
        memberships = group.memberships.select_related('user', 'user__cosinnus_profile')
        admin_qs = memberships.filter_membership_status(MEMBERSHIP_ADMIN)
        admin_ids = [self.get_user_id(m.user) for m in admin_qs]
        members_qs = memberships.filter_membership_status([MEMBERSHIP_ADMIN, MEMBERSHIP_MEMBER])
        member_usernames = [str(m.user.cosinnus_profile.rocket_username)
                            for m in members_qs if m.user.cosinnus_profile]
        member_usernames.append(settings.COSINNUS_CHAT_USER)

        # Create general channel
        group_name = settings.COSINNUS_CHAT_GROUP_GENERAL % group.slug
        response = self.rocket.groups_create(name=group_name, members=member_usernames).json()
        if not response.get('success'):
            # Duplicate group name?
            if response.get('errorType') == 'error-duplicate-channel-name':
                # Assign Rocket.Chat group ID to WECHANGE group
                response = self.rocket.groups_info(room_name=group_name).json()
                if not response.get('success'):
                    logger.error('groups_create', 'groups_info', response)
                room_id = response.get('group', {}).get('_id')
                if room_id:
                    # Update group settings without triggering signals to prevent cycles
                    group.settings[f'{PROFILE_SETTING_ROCKET_CHAT_ID}_general'] = room_id
                    type(group).objects.filter(pk=group.pk).update(settings=group.settings)
            else:
                logger.error('groups_create', response)
        else:
            room_id = response.get('group', {}).get('_id')
            if room_id:
                # Add moderators
                for user_id in admin_ids:
                    response = self.rocket.groups_add_moderator(room_id=room_id, user_id=user_id).json()
                    if not response.get('success'):
                        logger.error('groups_create', 'groups_add_moderator', response)
                # Update group settings without triggering signals to prevent cycles
                group.settings[f'{PROFILE_SETTING_ROCKET_CHAT_ID}_general'] = room_id
                type(group).objects.filter(pk=group.pk).update(settings=group.settings)

                # Set description
                response = self.rocket.groups_set_description(room_id=room_id, description=group.name).json()
                if not response.get('success'):
                    logger.error('groups_create', 'groups_set_description', response)

        # Create news channel
        group_name = settings.COSINNUS_CHAT_GROUP_NEWS % group.slug
        response = self.rocket.groups_create(name=group_name, members=member_usernames, readOnly=True).json()
        if not response.get('success'):
            # Duplicate group name?
            if response.get('errorType') == 'error-duplicate-channel-name':
                # Assign Rocket.Chat group ID to WECHANGE group
                response = self.rocket.groups_info(room_name=group_name).json()
                if not response.get('success'):
                    logger.error('groups_create', 'groups_info', response)
                room_id = response.get('group', {}).get('_id')
                if room_id:
                    # Update group settings without triggering signals to prevent cycles
                    group.settings[f'{PROFILE_SETTING_ROCKET_CHAT_ID}_news'] = room_id
                    type(group).objects.filter(pk=group.pk).update(settings=group.settings)
            else:
                logger.error('groups_create', response)
        else:
            room_id = response.get('group', {}).get('_id')
            if room_id:
                # Add moderators
                for user_id in admin_ids:
                    response = self.rocket.groups_add_moderator(room_id=room_id, user_id=user_id).json()
                    if not response.get('success'):
                        logger.error('groups_create',  'groups_add_moderator', response)
                # Update group settings without triggering signals to prevent cycles
                group.settings[f'{PROFILE_SETTING_ROCKET_CHAT_ID}_news'] = room_id
                type(group).objects.filter(pk=group.pk).update(settings=group.settings)

                # Set description
                response = self.rocket.groups_set_description(room_id=room_id, description=group.name).json()
                if not response.get('success'):
                    logger.error('groups_create', 'groups_set_description', response)

    def groups_rename(self, group):
        """
        Update default channels for group or project
        :param group:
        :return:
        """
        # Rename general channel
        room_id = self.get_group_id(group, type='general')
        if room_id:
            room_name = settings.COSINNUS_CHAT_GROUP_GENERAL % group.slug
            response = self.rocket.groups_rename(room_id=room_id, name=room_name).json()
            if not response.get('success'):
                logger.error('groups_rename', response)

        # Rename news channel
        room_id = self.get_group_id(group, type='news')
        if room_id:
            room_name = settings.COSINNUS_CHAT_GROUP_NEWS % group.slug
            response = self.rocket.groups_rename(room_id=room_id, name=room_name).json()
            if not response.get('success'):
                logger.error('groups_rename', response)

    def groups_archive(self, group):
        """
        Delete default channels for group or project
        :param group:
        :return:
        """
        # Archive general channel
        room_id = self.get_group_id(group, type='general')
        if room_id:
            response = self.rocket.groups_archive(room_id=room_id).json()
            if not response.get('success'):
                logger.error('groups_archive', response)

        # Archive, news channel
        room_id = self.get_group_id(group, type='news')
        if room_id:
            response = self.rocket.groups_archive(room_id=room_id).json()
            if not response.get('success'):
                logger.error('groups_archive', response)

    def groups_invite(self, membership):
        """
        Create membership for default channels
        :param group:
        :return:
        """
        user_id = self.get_user_id(membership.user)
        if not user_id:
            return

        # Remove role in general group
        room_id = self.get_group_id(membership.group, type='general')
        if room_id:
            response = self.rocket.groups_invite(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_invite', response)

        # Remove role in news group
        room_id = self.get_group_id(membership.group, type='news')
        if room_id:
            response = self.rocket.groups_invite(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_invite', response)

    def groups_kick(self, membership):
        """
        Delete membership for default channels
        :param group:
        :return:
        """
        user_id = self.get_user_id(membership.user)
        if not user_id:
            return

        # Remove role in general group
        room_id = self.get_group_id(membership.group, type='general')
        if room_id:
            response = self.rocket.groups_kick(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_kick', response)

        # Remove role in news group
        room_id = self.get_group_id(membership.group, type='news')
        if room_id:
            response = self.rocket.groups_kick(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_kick', response)

    def groups_add_moderator(self, membership):
        """
        Add role to user in group
        :param group:
        :return:
        """
        user_id = self.get_user_id(membership.user)
        if not user_id:
            return

        # Remove role in general group
        room_id = self.get_group_id(membership.group, type='general')
        if room_id:
            response = self.rocket.groups_add_moderator(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_add_moderator', response)

        # Remove role in news group
        room_id = self.get_group_id(membership.group, type='news')
        if room_id:
            response = self.rocket.groups_add_moderator(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_add_moderator', response)

    def groups_remove_moderator(self, membership):
        """
        Remove role from user in group
        :param group:
        :return:
        """
        user_id = self.get_user_id(membership.user)
        if not user_id:
            return

        # Remove role in general group
        room_id = self.get_group_id(membership.group, type='general')
        if room_id:
            response = self.rocket.groups_remove_moderator(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_remove_moderator', response)

        # Remove role in news group
        room_id = self.get_group_id(membership.group, type='news')
        if room_id:
            response = self.rocket.groups_remove_moderator(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_remove_moderator', response)

    def format_message(self, text):
        """
        Replace WECHANGE formatting language with Rocket.Chat formatting language:
        Rocket.Chat:
            Bold: *Lorem ipsum dolor* ;
            Italic: _Lorem ipsum dolor_ ;
            Strike: ~Lorem ipsum dolor~ ;
            Inline code: `Lorem ipsum dolor`;
            Image: ![Alt text](https://rocket.chat/favicon.ico) ;
            Link: [Lorem ipsum dolor](https://www.rocket.chat/) or <https://www.rocket.chat/ |Lorem ipsum dolor> ;
        :param text:
        :return:
        """
        # Unordered lists: _ to - / * to -
        text = re.sub(r'\n_ ', '\n- ', text)
        text = re.sub(r'\n\* ', '\n- ', text)
        # Italic: * to _
        text = re.sub(r'(^|\n|[^\*])\*($|\n|[^\*])', r'\1_\2', text)
        # Bold: ** to *
        text = re.sub(r'\*\*', '*', text)
        # Strike: ~~ to ~
        text = re.sub(r'~~', '~', text)
        return text

    def notes_create(self, note):
        """
        Create message for new note in default channel of group/project
        :param group:
        :return:
        """
        url = note.get_absolute_url()
        text = self.format_message(note.text)
        message = f'*{note.title}*\n{text}\n\n[{url}]({url})'
        room_id = self.get_group_id(note.group, type='news')
        if not room_id:
            return
        response = self.rocket.chat_post_message(text=message, room_id=room_id).json()
        if not response.get('success'):
            logger.error('notes_create', response)
        msg_id = response.get('message', {}).get('_id')

        # Save Rocket.Chat message ID to note instance
        note.settings['rocket_chat_message_id'] = msg_id
        # Update note settings without triggering signals to prevent cycles
        type(note).objects.filter(pk=note.pk).update(settings=note.settings)

    def notes_update(self, note):
        """
        Update message for note in default channel of group/project
        :param group:
        :return:
        """
        msg_id = note.settings.get('rocket_chat_message_id')
        url = note.get_absolute_url()
        text = self.format_message(note.text)
        message = f'*{note.title}*\n{text}\n\n[{url}]({url})'
        room_id = self.get_group_id(note.group, type='news')
        if not msg_id or not room_id:
            return
        response = self.rocket.chat_update(msg_id=msg_id, room_id=room_id, text=message).json()
        if not response.get('success'):
            logger.error('notes_update', response)

    def notes_attachments_update(self, note):
        """
        Update attachments for note in default channel of group/project
        Unfortunately we cannot delete/update existing uploads, sincee rooms_upload doesn't return the message ID yet
        :param group:
        :return:
        """
        msg_id = note.settings.get('rocket_chat_message_id')
        room_id = self.get_group_id(note.group, type='news')
        if not msg_id or not room_id:
            return

        # Delete existing attachments
        # for att_id in note.settings.get('rocket_chat_attachment_ids', []):
        #     response = self.rocket.chat_delete(room_id=room_id, msg_id=att_id).json()
        #     if not response.get('success'):
        #         logger.error('notes_attachments_update', response)

        # Upload attachments
        # attachment_ids = []
        for att in note.attached_objects.all():
            att_file = att.target_object
            response = self.rocket.rooms_upload(rid=room_id,
                                                file=att_file.file.path,
                                                filename=att_file._sourcefilename,
                                                mimetype=att_file.mimetype,
                                                tmid=msg_id).json()
            if not response.get('success'):
                logger.error('notes_attachments_update', response)
            # attachment_ids.append(response.get('message', {}).get('_id'))

        # note.settings['rocket_chat_attachment_ids'] = attachment_ids
        # Update note settings without triggering signals to prevent cycles
        # type(note).objects.filter(pk=note.pk).update(settings=note.settings)

    def notes_delete(self, note):
        """
        Delete message for note in default channel of group/project
        :param group:
        :return:
        """
        msg_id = note.settings.get('rocket_chat_message_id')
        room_id = self.get_group_id(note.group, type='news')
        if not msg_id or not room_id:
            return
        response = self.rocket.chat_delete(room_id=room_id, msg_id=msg_id).json()
        if not response.get('success'):
            logger.error('notes_delete', response)

    def unread_messages(self, user):
        """
        Get number of unread messages for user
        :param user:
        :return:
        """
        profile = user.cosinnus_profile
        try:
            user_connection = RocketChat(user=profile.rocket_username, password=user.password,
                                         server_url=settings.COSINNUS_CHAT_BASE_URL)
        except RocketAuthenticationException:
            user_id = user.cosinnus_profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_ID)
            if not user_id:
                return 0
            response = self.rocket.users_update(user_id=user_id, password=user.password).json()
            if not response.get('success'):
                logger.error('unread_messages', 'users_update', response)
                return 0
            user_connection = get_cached_rocket_connection(user=profile.rocket_username, password=user.password,
                                         server_url=settings.COSINNUS_CHAT_BASE_URL, reset=True)
            
        response = user_connection.subscriptions_get().json()
            
        # TODO: which exception is received when the user has been logged out with this connection?
        # then call delete_cached_rocket_connection() and retry get_cached_rocket_connection!
        if not response.get('success'):
            logger.error('subscriptions_get', response)
            return 0

        return sum(subscription['unread'] for subscription in response['update'])

