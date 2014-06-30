# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext_lazy as _
from django.utils.html import escape

from postman.forms import BaseWriteForm


from cosinnus_message.fields import UserSelect2MultipleChoiceField
import six
from django.template.loader import render_to_string


class CustomWriteForm(BaseWriteForm):
    """The form for an authenticated user, to compose a message."""
    # specify help_text only to avoid the possible default 'Enter text to search.' of ajax_select v1.2.5
    recipients = UserSelect2MultipleChoiceField(label=_("Recipients"), help_text='', 
                                                data_view='user_select2_view')
    
    class Meta(BaseWriteForm.Meta):
        fields = ('recipients', 'subject', 'body')
        
    def __init__(self, *args, **kwargs):
        super(CustomWriteForm, self).__init__(*args, **kwargs)
        
        # retrieve the attached objects ids to select them in the update view
        users = []
        initial_users = kwargs['initial'].get('recipients', None)
        if initial_users:
            for username in initial_users.split(', '):
                users.append( get_user_model()._default_manager.get(username=username) )
                # delete the initial data or our select2 field initials will be overwritten by django
                del kwargs['initial']['recipients']
                del self.initial['recipients']
                
            # TODO: sascha: returning unescaped html here breaks the javascript of django-select2
            preresults = [("user:" + six.text_type(user.id), escape(user.first_name) + " " + escape(user.last_name),)#render_to_string('cosinnus_message/user_select_pill.html', {'type':'user','text':escape(user.first_name) + " " + escape(user.last_name)}),)
                       for user in users]
            
            # we need to cheat our way around select2's annoying way of clearing initial data fields
            self.fields['recipients'].choices = preresults #((1, 'hi'),)
            self.fields['recipients'].initial = [key for key,val in preresults] #[1]
        

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
