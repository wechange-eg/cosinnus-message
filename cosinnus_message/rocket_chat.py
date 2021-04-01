import logging
import mimetypes
import os
import re

from cosinnus.models.group_extra import CosinnusSociety, CosinnusProject,\
    CosinnusConference
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
from cosinnus.models.group import CosinnusPortal, CosinnusGroupMembership
from cosinnus.models import MEMBERSHIP_ADMIN
from cosinnus.models.membership import MEMBERSHIP_MEMBER,\
    MEMBERSHIP_INVITED_PENDING, MEMBERSHIP_PENDING
from cosinnus.models.profile import PROFILE_SETTING_ROCKET_CHAT_ID, PROFILE_SETTING_ROCKET_CHAT_USERNAME
import traceback
from cosinnus.utils.user import filter_active_users, filter_portal_users
import six
from annoying.functions import get_object_or_None

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
    
    GROUP_ROOM_NAMES = ['general', 'news']
    GROUP_ROOM_SETTINGS_AND_NAMES = [
        (settings.COSINNUS_CHAT_GROUP_GENERAL, 'general',),
        (settings.COSINNUS_CHAT_GROUP_NEWS, 'news'),
    ]

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
            if type(value) in six.string_types:
                value = value % settings.__dict__['_wrapped'].__dict__
            response = self.rocket.settings_update(setting, value).json()
            if not response.get('success'):
                self.stderr.write('ERROR! ' + str(setting) + ': ' + str(value) + ':: ' + str(response))
            else:
                self.stdout.write('OK! ' + str(setting) + ': ' + str(value)) 
        self.oauth_sync()
        
    def create_missing_users(self, skip_inactive=False, force_group_membership_sync=False):
        """ 
        Create missing user accounts in rocketchat (and verify that ones with an existing
        connection still exist in rocketchat properly).
        Inactive user accounts and ones that never logged in will also be created.
        Will never create accounts for users with __unverified__ emails.
            
        @param skip_inactive: if True, will not create any accounts for inactive users
        @param force_group_membership_sync: if True, will also re-do and sync all group
            memberships, for all users. (default: only sync memberships for users created 
            during this run)
        """
        users = filter_portal_users(get_user_model().objects.all())
        users = users.exclude(email__startswith='__unverified__')
        if skip_inactive:
            users = filter_active_users(users)
        count = len(users)
        for i, user in enumerate(users):
            result = self.ensure_user_account_sanity(user, force_group_membership_sync=force_group_membership_sync)
            self.stdout.write('User %i/%i. Success: %s \t %s' % (i, count, str(result), user.email),)

    def users_sync(self, skip_update=False):
        """
        Sync active users that have already been created in rocketchat.
        Will not create new users.
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
                self.stderr.write('users_sync: ' + str(response), response)
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
        for group_model in (CosinnusConference, CosinnusSociety, CosinnusProject):
            groups = group_model.objects.filter(is_active=True, portal=portal)
            
            
            count = len(groups)
            for i, group in enumerate(groups):
                self.stdout.write('%s %i/%i' % (str(group_model), i, count), ending='\r')
                self.stdout.flush()
                self.groups_create(group)


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
                logger.error('RocketChat: get_user_id: no username given')
                return
            response = self.rocket.users_info(username=username).json()
            if not response.get('success'):
                logger.exception('get_user_id: ' + str(response.get('errorType', '<No Error Type>')), extra={'trace': traceback.format_stack(), 'username': username, 'response': response})
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
            # FIXME: what is this condition? ignores group_type name
            if group_type == 'general':
                group_name = settings.COSINNUS_CHAT_GROUP_GENERAL % group.slug
            else:
                group_name = settings.COSINNUS_CHAT_GROUP_NEWS % group.slug
            response = self.rocket.groups_info(room_name=group_name).json()
            if not response.get('success'):
                logger.error('RocketChat: get_group_id ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
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
        :return: A user object if the creation was done without errors.
        """
        if not hasattr(user, 'cosinnus_profile'):
            return
        profile = user.cosinnus_profile
        data = {
            "email": user.email.lower(),
            "name": user.get_full_name() or str(user.id),
            "password": user.password or get_random_string(length=16),
            "username": profile.rocket_username,
            "active": user.is_active,
            "verified": True,
            "requirePasswordChange": False,
        }
        response = self.rocket.users_create(**data).json()
        if not response.get('success'):
            logger.error('RocketChat: users_create: ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

        # Save Rocket.Chat User ID to user instance
        user_id = response.get('user', {}).get('_id')
        profile = user.cosinnus_profile
        profile.settings[PROFILE_SETTING_ROCKET_CHAT_ID] = user_id
        # Update profile settings without triggering signals to prevent cycles
        type(profile).objects.filter(pk=profile.pk).update(settings=profile.settings)
        return user

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
                logger.error('RocketChat: get_user_id ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
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
            logger.error('RocketChat: users_update_username: ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
    
    def check_user_account_status(self, user):
        """ Read-only check whether or not the user exists in rocket chat.
            @return:   True if the user account exists.
                        False if the user account definitely does not exist.
                        None if another error occurred or was returned, or the service was unavailable. """
        user_id = self.get_user_id(user)
        if not user_id:
            return False
        else:
            response = self.rocket.users_info(user_id=user_id)
            if response.status_code == 200 and response.json().get('success', False) and response.json().get('user', None):
                # user account is healthy
                return True
            elif response.status_code == 400 and response.json().get('error', '').lower() == 'user not found.':
                return False
            else:
                logger.info('Rocketchat check_user_account_status: users_info response returned a status code or error message we could not interpret.',
                    extra={'response-text': response.text, 'response_code': response.status_code})
                return None
    
    def ensure_user_account_sanity(self, user, force_group_membership_sync=False):
        """ A helper function that can always be safely called on any user object.
            Checks if the user account exists.
            @param force_group_membership_sync: if True, will also re-do group memberships for active users
                instead of only for freshly created accounts
            @param return: True if the account was either healthy or was newly created. False (and causes logs) otherwise """
        if not hasattr(user, 'cosinnus_profile'):
            # just return here, appearently this is a special/corrupted user account
            logger.error('RocketChat: Could not perform ensure_user_account_sanity: User object has no CosinnusProfile!', extra={'user_id': getattr(user, 'id', None)})
            return None
        
        # check for False, as None would mean unknown status
        status = self.check_user_account_status(user)
        if status is False:
            user = self.users_create(user)
            # re-check again to make sure the user was actually created
            if user and self.check_user_account_status(user):
                logger.info('ensure_user_account_sanity successfully created new rocketchat user account', extra={'user_id': getattr(user, 'id', None)})
                # newly created user, do a invite to their group memberships' rooms
                self.force_redo_user_room_memberships(user)
                return True
            else:
                logger.info('ensure_user_account_sanity attempted to create a new rocketchat user account, but failed!', extra={'user_id': getattr(user, 'id', None)})
                return False
        elif status is None:
            logger.error('RocketChat: ensure_user_account_sanity was called, but could not do anything as `check_user_account_status` received an unknown status code.')
            return False
        
        # status is True, account exists
        if force_group_membership_sync:
            self.force_redo_user_room_memberships(user)
        return True
    
    def force_redo_user_room_membership_for_group(self, user, group):
        """ A helper function that will re-do all room memberships by
            saving each user's membership (and having the invite-room hooks trigger) """
        membership = get_object_or_None(CosinnusGroupMembership, group__portal=CosinnusPortal.get_current(), user=user, group=group)
        if membership:
            # force the re-invite
            self.invite_or_kick_for_membership(membership)
    
    def force_redo_user_room_memberships(self, user):
        """ A helper function that will re-do all room memberships by
            saving each user's membership (and having the invite-room hooks trigger) """
        for membership in CosinnusGroupMembership.objects.filter(group__portal=CosinnusPortal.get_current(), user=user):
            # force the re-invite
            self.invite_or_kick_for_membership(membership)
            # saving causes conference room memberships to be re-done
            membership.save()
    
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
            logger.error('RocketChat: users_info status code: ' + str(response.text), extra={'response': response})
            return
        response = response.json()
        if not response.get('success'):
            logger.error('RocketChat: users_info response: ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
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
                logger.error(f'users_update (force={force_user_update}) base user: ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

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
                logger.error(f'users_update (force={force_user_update}) avatar: ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

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
            logger.error('RocketChat: users_disable: ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

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
            logger.error('RocketChat: users_enable: ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
    
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
            logger.error('RocketChat: users_delete: ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
    
    def get_group_room_name(self, group):
        """ Returns the rocketchat room name for a CosinnusGroup, for use in any URLs.
            Creates a room for the group if it doesn't exist yet """
        room_id = group.settings.get(f'{PROFILE_SETTING_ROCKET_CHAT_ID}_general', None)
        # create group if it didn't exist
        if not room_id:
            self.groups_create(group)
            room_id = group.settings.get(f'{PROFILE_SETTING_ROCKET_CHAT_ID}_general', None)
        response = self.rocket.groups_info(room_id=room_id).json()
        if not response.get('success'):
            logger.error('RocketChat: groups_request: groups_info ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
            return None
        group_name = response.get('group', {}).get('name', None)
        return group_name
    
    def groups_request(self, group, user, force_sync_membership=False):
        """
        Returns name of group if user is member of group, otherwise creates private group for group request
        (with user and group admins as members) and returns group name
        :param group:
        :param user:
        :param force_sync_membership: if True, and the user is a member of the CosinnusGroup,
            the user will be added to the rocketchat group again (useful to make sure
            that users are *really* members of the group)
        :return:
        """
        group_name = ''
        if group.is_member(user):
            group_name = self.get_group_room_name(group)
            if force_sync_membership:
                self.force_redo_user_room_membership_for_group(user, group)
        else:
            # Create private group
            group_name = f'{group.slug}-{get_random_string(7)}'
            if not hasattr(user, 'cosinnus_profile'):
                return
            profile = user.cosinnus_profile
            members = [str(u.id) for u in group.actual_admins] + [profile.rocket_username, ]
            response = self.rocket.groups_create(group_name, members=members).json()
            if not response.get('success'):
                logger.error('RocketChat: groups_request: groups_create ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
            group_name = response.get('group', {}).get('name')
            room_id = response.get('group', {}).get('_id')

            # Make user moderator of group
            user_id = user.cosinnus_profile.settings.get(PROFILE_SETTING_ROCKET_CHAT_ID)
            if user_id:
                response = self.rocket.groups_add_moderator(room_id=room_id, user_id=profile.rocket_username).json()
                if not response.get('success'):
                    logger.error('RocketChat: groups_request: groups_add_moderator ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

            # Set description of group
            desc = ''
            if group.type == group.TYPE_PROJECT:
                desc = _('Request about your project "%(group_name)s"')
            else:
                desc = _('Request about your group "%(group_name)s"')
            response = self.rocket.groups_set_description(room_id=room_id,
                                                          description=desc % {'group_name': group.name}).json()
            if not response.get('success'):
                logger.error('RocketChat: groups_request: groups_set_description ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

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
            logger.error('RocketChat: Direct create_private_group groups_create', extra={'response': response})
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
                    logger.error('RocketChat: Direct create_private_group groups_add_moderator', extra={'response': response})
        return room_id

    def groups_create(self, group):
        """
        Create default channels for group or project or conference, if they doesn't exist yet:
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

        # Create general and news channel
        for room_name_setting, group_room_name in self.GROUP_ROOM_SETTINGS_AND_NAMES:
            # check if group room exists
            room_id = group.settings.get(f'{PROFILE_SETTING_ROCKET_CHAT_ID}_{group_room_name}', None)
            if room_id:
                response = self.rocket.groups_info(room_id=room_id).json()
                if response.get('success'):
                    # room existed, don't create
                    continue
            
            group_name = room_name_setting % group.slug
            response = self.rocket.groups_create(name=group_name, members=member_usernames).json()
            
            if not response.get('success'):
                # Duplicate group name?
                if response.get('errorType') == 'error-duplicate-channel-name':
                    # Assign Rocket.Chat group ID to WECHANGE group
                    response = self.rocket.groups_info(room_name=group_name).json()
                    if not response.get('success'):
                        logger.error('RocketChat: groups_create: groups_info ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
                    room_id = response.get('group', {}).get('_id')
                    if room_id:
                        # Update group settings without triggering signals to prevent cycles
                        group.settings[f'{PROFILE_SETTING_ROCKET_CHAT_ID}_{group_room_name}'] = room_id
                        type(group).objects.filter(pk=group.pk).update(settings=group.settings)
                    continue
                elif response.get('errorType') in ('error-room-archived', 'error-archived-duplicate-name'):
                    # group has an archived room, which is probably a different one
                    # we rename the old room to a random one, leave it archived, and create the new room properly
                    old_room_id = self.get_group_id(group, group_type=group_room_name)
                    if old_room_id:
                        random_room_name = group_name + '-' + get_random_string(6)
                        # we need to unarchive the room to rename it
                        response = self.rocket.groups_unarchive(room_id=old_room_id).json()
                        if not response.get('success'):
                            logger.error('RocketChat: groups_unarchive (groups_create archive deduplication) ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
                            continue
                        response = self.rocket.groups_rename(room_id=old_room_id, name=random_room_name).json()
                        if not response.get('success'):
                            logger.error('RocketChat: groups_rename (groups_create archive deduplication) ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
                            continue
                        response = self.rocket.groups_archive(room_id=old_room_id).json()
                        if not response.get('success'):
                            logger.error('RocketChat: groups_archive (groups_create archive deduplication) ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
                            continue
                        # if successfully renamed, we're free to try to create out new room again
                        response = self.rocket.groups_create(name=group_name, members=member_usernames).json()
                        # if successful, we let this run into the regular group-setting room name assignment
                        if not response.get('success'):
                            logger.error('RocketChat: groups_rename (groups_create archive deduplication) ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
                            continue
                else:
                    logger.error('RocketChat: groups_create ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
            
            if response.get('success'):
                room_id = response.get('group', {}).get('_id')
                if room_id:
                    # Add moderators
                    for user_id in admin_ids:
                        response = self.rocket.groups_add_moderator(room_id=room_id, user_id=user_id).json()
                        if not response.get('success'):
                            logger.error('RocketChat: groups_create: groups_add_moderator ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
                    # Update group settings without triggering signals to prevent cycles
                    group.settings[f'{PROFILE_SETTING_ROCKET_CHAT_ID}_{group_room_name}'] = room_id
                    type(group).objects.filter(pk=group.pk).update(settings=group.settings)
    
                    # Set description
                    response = self.rocket.groups_set_description(room_id=room_id, description=group.name).json()
                    if not response.get('success'):
                        logger.error('RocketChat: groups_create: groups_set_description ' + response.get('errorType', '<No Error Type>'), extra={'response': response})


    def groups_rename(self, group):
        """
        Update default channels for group or project
        :param group:
        :return:
        """
        # Rename general and news channel
        for room_setting, room in self.GROUP_ROOM_SETTINGS_AND_NAMES:
            room_id = self.get_group_id(group, group_type=room)
            if room_id:
                room_name = room_setting % group.slug
                response = self.rocket.groups_rename(room_id=room_id, name=room_name).json()
                if not response.get('success'):
                    logger.error('RocketChat: groups_rename ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

    def groups_archive(self, group):
        """
        Archive default channels for group or project
        :param group:
        :return:
        """
        # Archive general and news channel
        for room in self.GROUP_ROOM_NAMES:
            room_id = self.get_group_id(group, group_type=room)
            if room_id:
                response = self.rocket.groups_archive(room_id=room_id).json()
                if not response.get('success'):
                    logger.error('RocketChat: groups_archive ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

    def groups_unarchive(self, group):
        """
        Unarchive default channels for group or project
        :param group:
        :return:
        """
        # Unarchive general and news channel
        for room in self.GROUP_ROOM_NAMES:
            room_id = self.get_group_id(group, group_type=room)
            if room_id:
                response = self.rocket.groups_unarchive(room_id=room_id).json()
                if not response.get('success'):
                    logger.error('RocketChat: groups_unarchive ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

    def groups_delete(self, group):
        """
        Delete default channels for group or project
        :param group:
        :return:
        """
        # Delete general and news channel
        for room in self.GROUP_ROOM_NAMES:
            room_id = self.get_group_id(group, group_type=room)
            if room_id:
                response = self.rocket.groups_delete(room_id=room_id).json()
                if not response.get('success'):
                    logger.error('RocketChat: groups_delete ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

    def invite_or_kick_for_membership(self, membership):
        """ For a CosinnusGroupMembership, force do:
                either kick or invite and promote or demote a user depending on their status """
        is_pending = membership.status in (MEMBERSHIP_PENDING, MEMBERSHIP_INVITED_PENDING)
        if is_pending:
            self.groups_kick(membership)
        else:
            self.groups_invite(membership)
            if membership.status == MEMBERSHIP_ADMIN:
                self.groups_add_moderator(membership)
            else:
                self.groups_remove_moderator(membership)
    
    def groups_invite(self, membership):
        """
        Create membership for default channels
        :param group:
        :return:
        """
        user_id = self.get_user_id(membership.user)
        if not user_id:
            return
        
        # Create role in general and news group
        for room in self.GROUP_ROOM_NAMES:
            room_id = self.get_group_id(membership.group, group_type=room)
            if room_id:
                response = self.rocket.groups_invite(room_id=room_id, user_id=user_id).json()
                if not response.get('success'):
                    logger.error('RocketChat: groups_invite ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

    def groups_kick(self, membership):
        """
        Delete membership for default channels
        :param group:
        :return:
        """
        user_id = self.get_user_id(membership.user)
        if not user_id:
            return
        
        # Remove role in general and news group
        for room in self.GROUP_ROOM_NAMES:
            room_id = self.get_group_id(membership.group, group_type=room)
            if room_id:
                response = self.rocket.groups_kick(room_id=room_id, user_id=user_id).json()
                if not response.get('success'):
                    logger.error('RocketChat: groups_kick ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

    def groups_add_moderator(self, membership):
        """
        Add role to user in group
        :param group:
        :return:
        """
        user_id = self.get_user_id(membership.user)
        if not user_id:
            return
        
        # Add moderator in general and news group
        for room in self.GROUP_ROOM_NAMES:
            room_id = self.get_group_id(membership.group, group_type=room)
            if room_id:
                response = self.rocket.groups_add_moderator(room_id=room_id, user_id=user_id).json()
                if not response.get('success') and not response.get('errorType', '') == 'error-user-already-moderator':
                    logger.error('RocketChat: groups_add_moderator ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

    def groups_remove_moderator(self, membership):
        """
        Remove role from user in group
        :param group:
        :return:
        """
        user_id = self.get_user_id(membership.user)
        if not user_id:
            return
        
        # Remove moderator in general and news group
        for room in self.GROUP_ROOM_NAMES:
            room_id = self.get_group_id(membership.group, group_type=room)
            if room_id:
                response = self.rocket.groups_remove_moderator(room_id=room_id, user_id=user_id).json()
                if not response.get('success') and not response.get('errorType', '') == 'error-user-not-moderator':
                    logger.error('RocketChat: groups_remove_moderator ' + response.get('errorType', '<No Error Type>'), extra={'response': response})

    def add_member_to_room(self, user, room_id):
        """ Add a member to a given room """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        response = self.rocket.groups_invite(room_id=room_id, user_id=user_id).json()
        if not response.get('success'):
            logger.error('RocketChat: Direct room_add_member: ' + response.get('errorType', '<No Error Type>'), extra={'user_email': user.email, 'response': response})

    def remove_member_from_room(self, user, room_id):
        """ Remove a member for a given room """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        response = self.rocket.groups_kick(room_id=room_id, user_id=user_id).json()
        if not response.get('success'):
            logger.error('RocketChat: Direct room_remove_member: ' + response.get('errorType', '<No Error Type>'), extra={'user_email': user.email, 'response': response})

    def add_moderator_to_room(self, user, room_id):
        """ Add a moderator to a given room """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        response = self.rocket.groups_add_moderator(room_id=room_id, user_id=user_id).json()
        if not response.get('success'):
            logger.error('RocketChat: Direct room_remove_moderator: ' + response.get('errorType', '<No Error Type>'), extra={'user_email': user.email, 'response': response})

    def remove_moderator_from_room(self, user, room_id):
        """ Remove a moderator for a given room """
        user_id = self.get_user_id(user)
        if not user_id:
            return
        response = self.rocket.groups_remove_moderator(room_id=room_id, user_id=user_id).json()
        if not response.get('success'):
            logger.error('RocketChat: Direct groups_remove_moderator: ' + response.get('errorType', '<No Error Type>'), extra={'user_email': user.email, 'response': response})

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
            logger.error('RocketChat: notes_create', extra={'response': response})
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
            logger.error('RocketChat: notes_update', extra={'response': response})

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
        #         logger.error('RocketChat: notes_attachments_update', extra={'response': response})

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
                logger.error('RocketChat: notes_attachments_update', extra={'response': response})
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
            logger.error('RocketChat: notes_delete', extra={'response': response})

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
                    logger.error('RocketChat: unread_messages did not receive a success response: ' + response.get('errorType', '<No Error Type>'), extra={'response': response})
                    return 0
                user_connection = get_cached_rocket_connection(rocket_username=profile.rocket_username, password=user.password,
                                             server_url=settings.COSINNUS_CHAT_BASE_URL, reset=True) # resets cache

            response = user_connection.subscriptions_get()

            # if we didn't receive a successful response, the server may be down or the user logged out
            # reset the user connection and let the response be tried on the next run
            if not response.status_code == 200:
                delete_cached_rocket_connection(rocket_username=profile.rocket_username)
                logger.warn('RocketChat: Rocket: unread_message_count: non-200 response.',
                            extra={'response': response, 'status': response.status_code, 'content': response.content})
                return 0

            # check if we got proper data back from the API
            response_json = response.json()
            if not response_json.get('success'):
                logger.error('RocketChat: subscriptions_get did not return a success', response_json)
                return 0

            # add all unread channel updates and return
            return sum(subscription['unread'] for subscription in response_json['update'])

        except RocketConnectionException as e:
            logger.warn('RocketChat: unread message count: connection exception',
                     extra={'exception': e})
        except Exception as e:
            logger.error('RocketChat: unread message count: unexpected exception',
                     extra={'exception': e})
            logger.exception(e)
