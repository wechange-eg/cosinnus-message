# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from multiform import InvalidArgument

from cosinnus.forms.group import GroupKwargModelFormMixin
from cosinnus.forms.tagged import get_form

from cosinnus_message.models import Message


class _MessageForm(GroupKwargModelFormMixin, forms.ModelForm):

    class Meta:
        model = Message
        fields = ('title', 'isbroadcast', 'isprivate', 'recipients', 'text')

    def __init__(self, user, *args, **kwargs):
        super(_MessageForm, self).__init__(*args, **kwargs)

        # Filter selectible recipients by this group's users
        uids = self.group.members
        uids.remove(user.id)
        self.fields['recipients'].queryset = get_user_model()._default_manager \
                                                             .filter(id__in=uids)

    def clean_recipients(self):
        """
        Overrides recipient selection if broadcast was selected and send to
        *all* group members
        """
        recipients = self.cleaned_data['recipients']
        broadcast = self.cleaned_data['isbroadcast']
        if not broadcast and not recipients:
            raise ValidationError(
                _('Please select a recipient for the message!'),
                code='missing_recipient'
            )
        if broadcast:
            recipients = self.fields['recipients'].queryset.all()

        return recipients


class MessageForm(get_form(_MessageForm, attachable=False)):

    def dispatch_init_user(self, name, user):
        if name == 'obj':
            return user
        return InvalidArgument
