# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from cosinnus_message.conf import settings # we need this import here!

from django_mailbox.signals import message_received
from django_mailbox.models import Mailbox
from django.dispatch import receiver
from cosinnus.models.group import CosinnusPortal
from django.db import models
from django.utils.translation import ugettext_lazy as _

@receiver(message_received)
def new_message_receiver(sender, message, **args):
    print "I just recieved a message titled %s from a mailbox named %s" % (message.subject, message.mailbox.name,)
    print ">> in portal:", CosinnusPortal.get_current()
    
print ">> registered receiver", settings.SITE_ID

class CosinnusMailbox(Mailbox):
    
    portal = models.ForeignKey(CosinnusPortal, verbose_name=_('Portal'), related_name='mailboxes', 
        null=False, blank=False, default=1) # port_id 1 is created in a datamigration!
    
    class Meta:
        verbose_name = "Cosinnus Mailbox"
        verbose_name_plural = "Cosinnus Mailboxes"

import django
if django.VERSION[:2] < (1, 7):
    from cosinnus_message import cosinnus_app
    cosinnus_app.register()


