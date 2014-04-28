# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _

from cosinnus.core import mail
from cosinnus.models.tagged import BaseTaggableObjectModel

from cosinnus_message.conf import settings


class MessageQuerySet(models.query.QuerySet):

    def filter_for_user(self, user):
        q = Q(isprivate=False)
        if user:
            recipient_of = list(self._clone().filter(recipients__id=user.pk)
                                             .values_list('id', flat=True)
                                             .order_by())
            q |= Q(creator_id=user.pk) | Q(id__in=recipient_of)
        return self.filter(q)


class MessageManager(models.Manager):

    use_for_related_fields = True

    def get_queryset(self):
        return MessageQuerySet(self.model, using=self._db)

    get_query_set = get_queryset

    def filter_for_user(self, user):
        return self.get_queryset().filter_for_user(user)


class Message(BaseTaggableObjectModel):
    """
    A message sent to the whole group (broadcast) or to selected group members
    """
    SORT_FIELDS_ALIASES = [
        ('title', 'title'), ('creator', 'creator'), ('created', 'created'),
    ]

    text = models.TextField(_('Text'))

    isbroadcast = models.BooleanField(_('Broadcast'), blank=False, null=False,
        default=False)
    isprivate = models.BooleanField(_('Private'), blank=False, null=False,
        default=False)
    recipients = models.ManyToManyField(settings.AUTH_USER_MODEL,
        verbose_name=_('Recipients'), blank=True, null=True,
        related_name='messages')

    objects = MessageManager()

    class Meta(BaseTaggableObjectModel.Meta):
        ordering = ['-created', 'title']
        verbose_name = _('Message')
        verbose_name_plural = _('Messages')

    def __init__(self, *args, **kwargs):
        super(Message, self).__init__(*args, **kwargs)
        self._meta.get_field('creator').verbose_name = _('Author')

    def send(self, request):
        """
        Sends the Message to the email addresses of all recipients, as BCC.
        """
        recipients = [recipient.email for recipient in self.recipients.all()]
        sender_address = settings.DEFAULT_FROM_EMAIL
        if settings.COSINNUS_MESSAGE_SHOW_MESSAGE_SENDER_EMAIL:
            sender_address = self.creator.email

        template_data = {
            'group': self.group.name,
            'sender': self.creator.first_name,
            'title': self.title,
            'text': self.text,
            'protocol': 'https' if request.is_secure() else 'http',
            'domain': request.get_host(),
            'url_path': reverse('cosinnus:message:message', kwargs={
                'group': self.group.slug,
                'slug': self.slug
            }),
        }

        subject = _('%(sender)s via %(group)s: "%(title)s"') % template_data

        mail.send_mail('', subject, "cosinnus_message/email.txt",
            template_data, sender_address, bcc=recipients)

    def get_absolute_url(self):
        kwargs = {'group': self.group.slug, 'slug': self.slug}
        return reverse('cosinnus:message:message', kwargs=kwargs)


import django
if django.VERSION[:2] < (1, 7):
    from cosinnus_message import cosinnus_app
    cosinnus_app.register()
