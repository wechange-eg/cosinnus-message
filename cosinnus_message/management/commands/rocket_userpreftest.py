import logging

from django.core.management.base import BaseCommand

from cosinnus_message.rocket_chat import RocketChatConnection
from cosinnus.utils.group import get_cosinnus_group_model
from cosinnus.models.group import CosinnusPortal
from django.contrib.auth import get_user_model


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Command(BaseCommand):
    """
    Sets all group room's topics anew
    """
    

    def handle(self, *args, **options):
        rocket = RocketChatConnection(stdout=self.stdout, stderr=self.stderr)
        sascha = get_user_model().objects.get(email='saschanarr@gmail.com')
        rocket.get_user_preferences(sascha)
        
        
        
        