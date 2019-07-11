from django.conf import settings
from django.contrib.auth import get_user_model

from rocketchat_API.rocketchat import RocketChat


class RocketChatConnection:

    CHAT_URL = settings.COSINNUS_CHAT_BASE_URL
    CHAT_USER = settings.COSINNUS_CHAT_USER
    CHAT_PASSWORD = settings.COSINNUS_CHAT_PASSWORD
    rocket = None
    stdout, stderr = None, None

    def __init__(self, stdout=None, stderr=None):
        self.rocket = RocketChat(self.CHAT_USER, self.CHAT_PASSWORD, server_url=self.CHAT_URL)
        if stdout:
            self.stdout = stdout
        if stderr:
            self.stderr = stderr

    def sync_users(self):
        """
        Sync users
        :return:
        """
        # Get existing rocket users
        rocket_users = dict((u['username'], u) for u in self.rocket.users_list().json()['users'])

        users = get_user_model().objects.filter(is_active=True)
        count = len(users)
        for i, user in enumerate(users):
            self.stdout.write('User %i/%i' % (i, count), ending='\r')
            self.stdout.flush()
            rocket_user = rocket_users.get(user.username, None)

            if rocket_user:
                changed = False
                # TODO: Introducing User.updated_at would improve performance here
                rocket_emails = (e['address'] for e in rocket_user['emails'])
                # Email address changed?
                if user.email not in rocket_emails:
                    changed = True
                # Name changed?
                elif user.get_full_name() != rocket_user['name']:
                    changed = True
                # Avatar changed?
                else:
                    rocket_avatar_url = self.rocket.users_get_avatar(username=user.username).url
                    if user.avatar.url != rocket_avatar_url:
                        changed = True
                if changed:
                    # Update rocket user
                    self.rocket.users_update(user.username,
                                             name=user.get_full_name(),
                                             email=user.email)
                    self.rocket.users_set_avatar(user.avatar.url)

            else:
                # Create rocket user
                self.rocket.users_create(email=user.email,
                                         name=user.get_full_name(),
                                         username=user.username)
                self.rocket.users_set_avatar(user.avatar.url)

    def sync_direct_messages(self):
        """
        Sync direct messages
        :return:
        """
        from postman.models import Message
        messages = Message.objects.all(sender_archived=False,
                                       recipient_archived=False,
                                       sender_deleted_at__isnull=True,
                                       recipient_deleted_at__isnull=True).order_by('sent_at')
        message_template = '%(subject)s: %(body)s'

        for message in messages:
            result = self.rocket.im_create(username=message.sender)
            message = message_template % {
                'subject': message.subject,
                'body': message.body,
            }
            self.rocket.chat_post_message(text=message,
                                          room_id=result.json()['result']['rid'])
