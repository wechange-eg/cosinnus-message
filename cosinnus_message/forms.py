# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django.forms.models import ModelForm
from django.contrib.auth import get_user_model

from cosinnus_message.models import Message
from cosinnus.views.mixins.group import GroupFormKwargsMixin

class MessageForm(ModelForm, GroupFormKwargsMixin):

    class Meta:
        model = Message
        fields = ('title', 'isbroadcast', 'isprivate', 'recipients', 'text')

    def __init__(self, *args, **kwargs):
        super(MessageForm, self).__init__(*args, **kwargs)

    def clean_recipients(self):
        """ override recipient selection if broadcast was selected and send to ALL group members """
        recipients = self.cleaned_data['recipients']
        broadcast = self.cleaned_data['isbroadcast']
        if broadcast:
            recipients = self.fields['recipients'].queryset.all()

        return recipients
