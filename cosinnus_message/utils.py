# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django_mailbox.models import Message

def process_direct_reply_messages():
    """ Will check all existing django_mail Messages:
        - drop all mail addressed to emails not matching the Pattern: direct-reply+<portal-id>+<hash>@<mailbox-domain> 
        - take all mail for this portal. 
            - if there is a hash matching a postman message, match sender to user, reply as that user using body text
            - delete the mail, no matter if a match was found or not
        - retain the rest (other portals might be using the same mailbox)
        """
    print ">> now processing messages:", Message.objects.all().count()