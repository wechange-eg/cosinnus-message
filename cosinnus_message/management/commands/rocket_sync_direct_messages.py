import logging

from django.core.management.base import BaseCommand

from cosinnus_message.rocket_chat import RocketChatConnection


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Command(BaseCommand):
    """
    Sync direct messages with Rocket.Chat
    """

    def handle(self, *args, **options):
        rocket = RocketChatConnection(stdout=self.stdout, stderr=self.stderr)
        rocket.sync_direct_messages()
