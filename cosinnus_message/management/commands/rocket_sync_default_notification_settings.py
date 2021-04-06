import logging

from django.core.management.base import BaseCommand

from cosinnus_message.rocket_chat import RocketChatConnection
from cosinnus.utils.group import get_cosinnus_group_model
from cosinnus.models.group import CosinnusPortal
from cosinnus.utils.user import filter_portal_users
from cosinnus.conf import settings
from django.contrib.auth import get_user_model
from cosinnus_message.utils.utils import save_rocketchat_mail_notification_preference_for_user_setting


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Command(BaseCommand):
    """
    For all users who have *not yet* set any rocketchat mail notification preference, 
    this will set the portal's default setting as their mail notification preference.
    Users who have saved their preference before are left untouched.
    
    This is not neccessary to run on new portals, as the setting is set on user creation already.
    """

    def handle(self, *args, **options):
        default_setting = settings.COSINNUS_DEFAULT_ROCKETCHAT_NOTIFICATION_SETTING
        
        rocket = RocketChatConnection(stdout=self.stdout, stderr=self.stderr)
        users = filter_portal_users(get_user_model().objects.all())
        users = users.exclude(email__startswith='__unverified__')
        users = users.exclude(password__exact='').exclude(password=None)
        count = 0
        errors = 0
        total = len(users)
        for user in users:
            pref = rocket.get_user_email_preference(user)
            # if the user hasn't got a definite value set in their profile, we set the portal's default
            if not pref:
                try:
                    save_rocketchat_mail_notification_preference_for_user_setting(
                        user,
                        default_setting
                    )
                    self.stdout.write(f'User {count+1}/{total} ({errors} Errors): Applied default setting {default_setting}')
                except Exception as e:
                    errors += 1
                    self.stdout.write(f'User {count+1}/{total} ({errors} Errors): Error! {str(e)}')
            else:
                self.stdout.write(f'User {count+1}/{total} ({errors} Errors): Skipping (they had setting "{pref}")')
            count += 1
