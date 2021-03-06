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
from oauth2_provider.models import Application

from rocketchat_API.APIExceptions.RocketExceptions import RocketAuthenticationException,\
    RocketConnectionException
from rocketchat_API.rocketchat import RocketChat as RocketChatAPI
from cosinnus.models.group import CosinnusPortal
from cosinnus.models import MEMBERSHIP_ADMIN
from cosinnus.models.membership import MEMBERSHIP_MEMBER
from cosinnus.models.profile import PROFILE_SETTING_ROCKET_CHAT_ID, PROFILE_SETTING_ROCKET_CHAT_USERNAME
import traceback
from cosinnus.utils.user import filter_active_users, filter_portal_users

logger = logging.getLogger(__name__)

ROCKETCHAT_USER_CONNECTION_CACHE_KEY = 'cosinnus/core/portal/%d/rocketchat-user-connection/%s/'


def get_cached_rocket_connection(rocket_username, password, server_url, reset=False):
    """ Retrieves a cached rocketchat connection or creates a new one and caches it.
        @param reset: Resets the cached connection and connects a fresh one immediately """
    cache_key = ROCKETCHAT_USER_CONNECTION_CACHE_KEY % (CosinnusPortal.get_current().id, rocket_username)

    if reset:
        cache.delete(cache_key)
        rocket_connection = None
    else:
        rocket_connection = cache.get(cache_key)
        # check if rocket connection is still alive, if not, remove it from cache
        alive = False
        try:
            alive = rocket_connection.me().status_code == 200
        except:
            pass
        if not alive:
            cache.delete(cache_key)
            rocket_connection = None

    if rocket_connection is None:
        rocket_connection = RocketChat(user=rocket_username, password=password, server_url=server_url)
        cache.set(cache_key, rocket_connection, settings.COSINNUS_CHAT_CONNECTION_CACHE_TIMEOUT)
    return rocket_connection


def delete_cached_rocket_connection(rocket_username):
    """ Deletes a cached rocketchat connection or creates a new one and caches it """
    cache_key = ROCKETCHAT_USER_CONNECTION_CACHE_KEY % (CosinnusPortal.get_current().id, rocket_username)
    cache.delete(cache_key)


class RocketChat(RocketChatAPI):

    def __init__(self, *args, **kwargs):
        # this fixes the re-used dict from the original rocket API object
        self.headers = {}
        super(RocketChat, self).__init__(*args, **kwargs)

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

    def oauth_sync(self):
        app, created = Application.objects.get_or_create(
            client_type='confidential',
            authorization_grant_type='authorization-code',
            redirect_uris=f'{self.rocket.server_url}/_oauth/{settings.COSINNUS_PORTAL_NAME}',
            skip_authorization=True
        )
        # FIXME: Create/update oauth client app on Rocket.Chat, once version 3.4 is released
        # https://github.com/RocketChat/Rocket.Chat/pull/14912

    def settings_update(self):
        for setting, value in settings.COSINNUS_CHAT_SETTINGS.items():
            value = value % settings.__dict__['_wrapped'].__dict__
            response = self.rocket.settings_update(setting, value).json()
            if not response.get('success'):
                self.stderr.write('ERROR! ' + str(setting) + ': ' + str(value) + ':: ' + str(response))
            else:
                self.stdout.write('OK! ' + str(setting) + ': ' + str(value)) 
        self.oauth_sync()

    def users_sync(self, skip_update=False):
        """
        Sync users
        @param skip_update: if True, skips updating existing users
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
        users = filter_active_users(filter_portal_users(get_user_model().objects.all()))
        
        count = len(users)
        for i, user in enumerate(users):
            self.stdout.write('User %i/%i' % (i, count), ending='\r')
            self.stdout.flush()

            if not hasattr(user, 'cosinnus_profile'):
                return
            profile = user.cosinnus_profile
            rocket_username = profile.rocket_username

            rocket_user = rocket_users.get(rocket_username)

            # User with different username but same email address exists?
            if not rocket_user and user.email.lower() in rocket_emails_usernames.keys():
                # Change username in DB
                rocket_username = rocket_emails_usernames.get(user.email.lower())
                rocket_user = rocket_users.get(rocket_username)

                profile.settings[PROFILE_SETTING_ROCKET_CHAT_USERNAME] = rocket_username
                profile.save(update_fields=['settings'])

            # Username exists?
            if rocket_user:
                if skip_update:
                    continue
                
                changed = False
                # TODO: Introducing User.updated_at would improve performance here
                rocket_emails = (e['address'] for e in rocket_user.get('emails'))
                # Email address changed?
                if user.email.lower() not in rocket_emails:
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
        portal = CosinnusPortal.get_current()
        
        # Sync WECHANGE groups
        groups = CosinnusSociety.objects.filter(is_active=True, portal=portal)
        groups = groups.filter(Q(**{f'settings__{PROFILE_SETTING_ROCKET_CHAT_ID}_general__isnull': True}) |
                               Q(**{f'settings__{PROFILE_SETTING_ROCKET_CHAT_ID}_general': None}))
        count = len(groups)
        for i, group in enumerate(groups):
            self.stdout.write('Group %i/%i' % (i, count), ending='\r')
            self.stdout.flush()
            self.groups_create(group)

        # Sync WECHANGE projects
        projects = CosinnusProject.objects.filter(is_active=True, portal=portal)
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
        if not hasattr(user, 'cosinnus_profile'):
            return
        profile = user.cosinnus_profile
        if not profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_ID):
            username = profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_USERNAME)
            if not username:
                logger.error('get_user_id', 'no username given')
                return
            response = self.rocket.users_info(username=username).json()
            if not response.get('success'):
                logger.exception('get_user_id: ' + str(response), extra={'trace': traceback.print_stack(), 'username': username})
                return
            user_data = response.get('user')
            rocket_chat_id = user_data.get('_id')
            profile.settings[PROFILE_SETTING_ROCKET_CHAT_ID] = rocket_chat_id
            # Update profile settings without triggering signals to prevent cycles
            type(profile).objects.filter(pk=profile.pk).update(settings=profile.settings)
        return profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_ID)

    def get_group_id(self, group, group_type='general'):
        """
        Returns Rocket.Chat ID from group settings or Rocket.Chat API
        :param user:
        :return:
        """
        key = f'{PROFILE_SETTING_ROCKET_CHAT_ID}_{group_type}'
        if not group.settings.get(key):
            if group_type == 'general':
                group_name = settings.COSINNUS_CHAT_GROUP_GENERAL % group.slug
            else:
                group_name = settings.COSINNUS_CHAT_GROUP_NEWS % group.slug
            response = self.rocket.groups_info(room_name=group_name).json()
            if not response.get('success'):
                logger.error('get_group_id', response)
                return
            group_data = response.get('group')
            rocket_chat_id = group_data.get('_id')
            group.settings[key] = rocket_chat_id
            # Update group settings without triggering signals to prevent cycles
            type(group).objects.filter(pk=group.pk).update(settings=group.settings)
        return group.settings.get(key)

    def users_create_or_update(self, user, request=None):
        if not hasattr(user, 'cosinnus_profile'):
            return
        if PROFILE_SETTING_ROCKET_CHAT_ID in user.cosinnus_profile.settings:
            return self.users_update(user, request)
        else:
            return self.users_create(user, request)

    def users_create(self, user, request=None):
        """
        Create user with name, email address and avatar
        :return:
        """
        if not hasattr(user, 'cosinnus_profile'):
            return
        profile = user.cosinnus_profile
        data = {
            "email": user.email.lower(),
            "name": user.get_full_name() or str(user.id),
            "password": user.password,
            "username": profile.rocket_username,
            "active": user.is_active,
            "verified": True,
            "requirePasswordChange": False,
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
        if not hasattr(user, 'cosinnus_profile'):
            return
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

    def users_update(self, user, request=None, force_user_update=False, update_password=False):
        """
        Updates user name, email address and avatar
        :return:
        """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        if not hasattr(user, 'cosinnus_profile'):
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

        # Update name, email address, password
        if force_user_update or user_data.get('name') != user.get_full_name() or user_data.get('email') != user.email.lower():
            profile = user.cosinnus_profile
            data = {
                "username": profile.rocket_username,
                "name": user.get_full_name(),
                "email": user.email.lower(),
                #"active": user.is_active,
                "verified": True,
                "requirePasswordChange": False,
            }
            # updating the password invalidates existing user sessions, so use it only
            # when actually needed
            if update_password:
                data.update({
                    "password": user.password,
                })
            response = self.rocket.users_update(user_id=user_id, **data).json()
            if not response.get('success'):
                logger.error('users_update', response)

        # Update Avatar URL
        avatar_url = user.cosinnus_profile.avatar.url if user.cosinnus_profile.avatar else ''
        if avatar_url:
            if request:
                avatar_url = request.build_absolute_uri(avatar_url)
            else:
                portal_domain = CosinnusPortal.get_current().get_domain()
                avatar_url = f'{portal_domain}{avatar_url}'
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
    
    def users_delete(self, user):
        """
        Delete a user
        :return:
        """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        response = self.rocket.users_delete(user_id=user_id).json()
        if not response.get('success'):
            logger.error('users_delete', response)
    
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
            if not hasattr(user, 'cosinnus_profile'):
                return
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

    def create_private_room(self, group_name, moderator_user, member_users=None, additional_admin_users=None):
        """ Create a private group with a user as first member and moderator.
            @param moderator_user: user who will become both a member and moderator
            @param member_users: list of users who become members. may contain the moderator_user again
            @return: the rocketchat room_id """
        if not hasattr(moderator_user, 'cosinnus_profile'):
            return
        # create group
        member_users = member_users or []
        members = [moderator_user.cosinnus_profile.rocket_username, ] + [member.cosinnus_profile.rocket_username for member in member_users]
        members = list(set(members))
        response = self.rocket.groups_create(group_name, members=members).json()
        if not response.get('success'):
            logger.error('Direct create_private_group groups_create', response)
        group_name = response.get('group', {}).get('name')
        room_id = response.get('group', {}).get('_id')

        # Make user moderator of group
        admin_users = list(additional_admin_users) if additional_admin_users else []
        admin_users.append(moderator_user)
        admin_users = list(set(admin_users))
        for admin_user in admin_users:
            user_id = admin_user.cosinnus_profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_ID)
            if user_id:
                response = self.rocket.groups_add_moderator(room_id=room_id, user_id=user_id).json()
                if not response.get('success'):
                    logger.error('Direct create_private_group groups_add_moderator', response)
        return room_id

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
        room_id = self.get_group_id(group, group_type='general')
        if room_id:
            room_name = settings.COSINNUS_CHAT_GROUP_GENERAL % group.slug
            response = self.rocket.groups_rename(room_id=room_id, name=room_name).json()
            if not response.get('success'):
                logger.error('groups_rename', response)

        # Rename news channel
        room_id = self.get_group_id(group, group_type='news')
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
        room_id = self.get_group_id(group, group_type='general')
        if room_id:
            response = self.rocket.groups_archive(room_id=room_id).json()
            if not response.get('success'):
                logger.error('groups_archive', response)

        # Archive, news channel
        room_id = self.get_group_id(group, group_type='news')
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

        # Create role in general group
        room_id = self.get_group_id(membership.group, group_type='general')
        if room_id:
            response = self.rocket.groups_invite(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_invite', response)

        # Create role in news group
        room_id = self.get_group_id(membership.group, group_type='news')
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
        room_id = self.get_group_id(membership.group, group_type='general')
        if room_id:
            response = self.rocket.groups_kick(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_kick', response)

        # Remove role in news group
        room_id = self.get_group_id(membership.group, group_type='news')
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
        room_id = self.get_group_id(membership.group, group_type='general')
        if room_id:
            response = self.rocket.groups_add_moderator(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_add_moderator', response)

        # Remove role in news group
        room_id = self.get_group_id(membership.group, group_type='news')
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
        room_id = self.get_group_id(membership.group, group_type='general')
        if room_id:
            response = self.rocket.groups_remove_moderator(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_remove_moderator', response)

        # Remove role in news group
        room_id = self.get_group_id(membership.group, group_type='news')
        if room_id:
            response = self.rocket.groups_remove_moderator(room_id=room_id, user_id=user_id).json()
            if not response.get('success'):
                logger.error('groups_remove_moderator', response)

    def add_member_to_room(self, user, room_id):
        """ Add a member to a given room """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        response = self.rocket.groups_invite(room_id=room_id, user_id=user_id).json()
        if not response.get('success'):
            logger.error('Direct room_add_member', response, extra={'user_email': user.email})

    def remove_member_from_room(self, user, room_id):
        """ Remove a member for a given room """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        response = self.rocket.groups_kick(room_id=room_id, user_id=user_id).json()
        if not response.get('success'):
            logger.error('Direct room_remove_member' +  str(response), extra={'user_email': user.email})

    def add_moderator_to_room(self, user, room_id):
        """ Add a moderator to a given room """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        response = self.rocket.groups_add_moderator(room_id=room_id, user_id=user_id).json()
        if not response.get('success'):
            logger.error('Direct room_remove_moderator', response, extra={'user_email': user.email})

    def remove_moderator_from_room(self, user, room_id):
        """ Remove a moderator for a given room """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        response = self.rocket.groups_remove_moderator(room_id=room_id, user_id=user_id).json()
        if not response.get('success'):
            logger.error('Direct groups_remove_moderator', response, extra={'user_email': user.email})

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
        room_id = self.get_group_id(note.group, group_type='news')
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
        room_id = self.get_group_id(note.group, group_type='news')
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
        room_id = self.get_group_id(note.group, group_type='news')
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
        room_id = self.get_group_id(note.group, group_type='news')
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
        if not hasattr(user, 'cosinnus_profile'):
            return
        profile = user.cosinnus_profile

        try:
            try:
                user_connection = get_cached_rocket_connection(rocket_username=profile.rocket_username, password=user.password,
                                             server_url=settings.COSINNUS_CHAT_BASE_URL)
            except RocketAuthenticationException:
                user_id = user.cosinnus_profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_ID)
                if not user_id:
                    # user not connected to rocketchat
                    return 0
                # try to re-initi the user's account and reconnect
                response = self.rocket.users_update(user_id=user_id, password=user.password).json()
                if not response.get('success'):
                    logger.error('unread_messages did not receive a success response', 'users_update', response)
                    return 0
                user_connection = get_cached_rocket_connection(rocket_username=profile.rocket_username, password=user.password,
                                             server_url=settings.COSINNUS_CHAT_BASE_URL, reset=True) # resets cache

            response = user_connection.subscriptions_get()

            # if we didn't receive a successful response, the server may be down or the user logged out
            # reset the user connection and let the response be tried on the next run
            if not response.status_code == 200:
                delete_cached_rocket_connection(rocket_username=profile.rocket_username)
                logger.warn('Rocket: unread_message_count: non-200 response.',
                            extra={'response': response, 'status': response.status_code, 'content': response.content})
                return 0

            # check if we got proper data back from the API
            response_json = response.json()
            if not response_json.get('success'):
                logger.error('Rocket: subscriptions_get did not return a success', response_json)
                return 0

            # add all unread channel updates and return
            return sum(subscription['unread'] for subscription in response_json['update'])

        except RocketConnectionException as e:
            logger.warn('Rocketchat unread message count: connection exception',
                     extra={'exception': e})
        except Exception as e:
            logger.error('Rocketchat unread message count: unexpected exception',
                     extra={'exception': e})
            logger.exception(e)
