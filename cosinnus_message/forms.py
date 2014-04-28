# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from postman.forms import BaseWriteForm

from cosinnus.forms.group import GroupKwargModelFormMixin
from cosinnus.forms.tagged import TagObjectFormMixin
from cosinnus.views.mixins.group import GroupFormKwargsMixin

from cosinnus_message.models import Message
from cosinnus_message.fields import UserSelect2MultipleChoiceField


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


class CustomWriteForm(BaseWriteForm):
    """The form for an authenticated user, to compose a message."""
    # specify help_text only to avoid the possible default 'Enter text to search.' of ajax_select v1.2.5
    recipients = UserSelect2MultipleChoiceField(label=_("Recipients"), help_text='')
    
    class Meta(BaseWriteForm.Meta):
        fields = ('recipients', 'subject', 'body')


class CustomReplyForm(CustomWriteForm):
    def __init__(self, *args, **kwargs):
        recipient = kwargs.pop('recipient', None)
        super(CustomReplyForm, self).__init__(*args, **kwargs)
        self.recipient = recipient
        self.fields['recipients'].label = _('Additional Recipients')
        self.fields['recipients'].required = False

    def clean(self):
        if not self.recipient:
            raise forms.ValidationError(
                _("Undefined recipient."))
        return super(CustomReplyForm, self).clean()

    def save(self, *args, **kwargs):
        return super(CustomReplyForm, self).save(
            self.recipient, *args, **kwargs)
