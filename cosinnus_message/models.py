# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.urlresolvers import reverse
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from django.contrib.sites.models import get_current_site

from cosinnus.utils.functions import unique_aware_slugify
from cosinnus.models.tagged import BaseTaggableObjectModel
from cosinnus_message.managers import MessageManager

from cosinnus.conf import settings
from cosinnus.core import mail

class Message(BaseTaggableObjectModel):
    """
    A message sent to the whole group (broadcast) or to selected group members
    """
    SORT_FIELDS_ALIASES = [
        ('title', 'title'), ('creator', 'creator'), ('created', 'created'),
    ]

    text = models.TextField(_('Text'))

    isbroadcast = models.BooleanField(_('Broadcast'), blank=False, null=False, default=False)
    isprivate = models.BooleanField(_('Private'), blank=False, null=False, default=False)
    recipients = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_('Recipients'), blank=True, null=True, related_name='messages')

    objects = MessageManager()

    class Meta:
        ordering = ['-created', 'title']
        verbose_name = _('Message')
        verbose_name_plural = _('Messages')

    def __init__(self, *args, **kwargs):
        super(Message, self).__init__(*args, **kwargs)
        self._meta.get_field('creator').verbose_name = _('Author')

    def send(self):
        '''
            Sends the Message to the email addresses of all recipients, as BCC.
        '''
        recipients = [recipient.email for recipient in self.recipients.all()]
        sender_address = self.creator.email if settings.SHOW_MESSAGE_SENDER_EMAIL else settings.DEFAULT_FROM_EMAIL

        template_data = {
            'group': self.group.name,
            'sender': self.creator.first_name,
            'title':self.title,
            'text':self.text,
            'message_url': 'http://' + get_current_site(None).domain + reverse('cosinnus:message:message', kwargs={'group':self.group.slug, 'slug':self.slug}),
        }

        subject = _('%(sender)s via %(group)s: "%(title)s"') % template_data

        mail.send_mail('', subject, "cosinnus_message/email.txt", template_data, sender_address, bcc=recipients)

    def save(self, *args, **kwargs):
        if not self.slug:
            unique_aware_slugify(self, slug_source='title', slug_field='slug', group=self.group)
        super(Message, self).save(*args, **kwargs)

    def get_absolute_url(self):
        kwargs = {'group': self.group.slug, 'slug': self.slug}
        return reverse('cosinnus:message:message', kwargs=kwargs)

