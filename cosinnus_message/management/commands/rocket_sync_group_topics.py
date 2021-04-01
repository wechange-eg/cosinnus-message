import logging

from django.core.management.base import BaseCommand

from cosinnus_message.rocket_chat import RocketChatConnection
from cosinnus.utils.group import get_cosinnus_group_model
from cosinnus.models.group import CosinnusPortal


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Command(BaseCommand):
    """
    Sets all group room's topics anew
    """
    

    def handle(self, *args, **options):
        rocket = RocketChatConnection(stdout=self.stdout, stderr=self.stderr)
        current_portal = CosinnusPortal.get_current()
        for group in get_cosinnus_group_model().objects.filter(portal=current_portal, is_active=True):
            rocket.group_set_topic_to_url(group)
