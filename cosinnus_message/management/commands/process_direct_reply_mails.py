import logging

from django.core.management.base import BaseCommand

from cosinnus.models.group import CosinnusPortal
from cosinnus_message.utils import process_direct_reply_messages
from cosinnus_message.models import CosinnusMailbox


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Command(BaseCommand):
    def handle(self, *args, **options):
        mailboxes = CosinnusMailbox.active_mailboxes.filter(cosinnusmailbox__portal=CosinnusPortal.get_current())
        
        if len(mailboxes) == 0:
            return
        
        for mailbox in mailboxes:
            logger.info(
                'Gathering messages for %s',
                mailbox.name
            )
            messages = mailbox.get_new_mail()
            for message in messages:
                logger.info(
                    'Received %s (from %s)',
                    message.subject,
                    message.from_address
                )
        
        process_direct_reply_messages()
        