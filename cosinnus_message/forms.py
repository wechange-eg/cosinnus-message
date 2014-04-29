# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django import forms
from django.utils.translation import ugettext_lazy as _
from postman.forms import BaseWriteForm

from cosinnus_message.fields import UserSelect2MultipleChoiceField


class CustomWriteForm(BaseWriteForm):
    """The form for an authenticated user, to compose a message."""
    # specify help_text only to avoid the possible default 'Enter text to search.' of ajax_select v1.2.5
    recipients = UserSelect2MultipleChoiceField(label=_("Recipients"), help_text='', 
                                                data_view='user_select2_view')
    
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
