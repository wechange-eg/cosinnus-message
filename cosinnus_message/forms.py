# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from cosinnus.forms.group import GroupKwargModelFormMixin
from cosinnus.forms.tagged import TagObjectFormMixin
from cosinnus.views.mixins.group import GroupFormKwargsMixin

from cosinnus_message.models import Message


class MessageForm(GroupKwargModelFormMixin, TagObjectFormMixin,
                  forms.ModelForm):

    class Meta:
        model = Message
        fields = ('title', 'isbroadcast', 'isprivate', 'recipients', 'text')

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
