# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django.forms.models import ModelForm

from cosinnus_message.models import Message

class MessageForm(ModelForm):

    class Meta:
        model = Message
        fields = ('title', 'recipients', 'text')

    def __init__(self, *args, **kwargs):
        super(MessageForm, self).__init__(*args, **kwargs)
        # instance = getattr(self, 'instance', None)

    # def clean_recipients(self):
    #    instance = getattr(self, 'instance', None)
    #    if instance:
    #        return self.cleaned_data['recipients']
