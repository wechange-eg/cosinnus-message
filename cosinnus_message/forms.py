# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext_lazy as _

from postman.forms import BaseWriteForm


from cosinnus.utils.permissions import check_user_can_see_user,\
    check_user_superuser
from cosinnus.utils.user import get_user_select2_pills, get_group_select2_pills
from cosinnus.fields import UserSelect2MultipleChoiceField
from cosinnus.models.group import CosinnusGroup

from cosinnus.conf import settings


def user_write_permission_filter(sender, recipient, recipients_list):
    """ Make sure the users can interact with each other """
    if check_user_can_see_user(sender, recipient):
        return None
    return 'This user is private and you are not in any groups/projects with them!'
    

class CustomWriteForm(BaseWriteForm):
    """The form for an authenticated user, to compose a message."""
    # specify help_text only to avoid the possible default 'Enter text to search.' of ajax_select v1.2.5
    recipients = UserSelect2MultipleChoiceField(label=_("Recipients"), help_text='', 
                                                data_view='postman:user_select2_view')
    
    exchange_filter = staticmethod(user_write_permission_filter)
    
    restricted_recipient_flag = False
    
    class Meta(BaseWriteForm.Meta):
        fields = ('recipients', 'subject', 'body')
        
    def __init__(self, *args, **kwargs):
        super(CustomWriteForm, self).__init__(*args, **kwargs)
        
        # retrieve the attached objects ids to select them in the update view
        users = []
        initial_users = kwargs['initial'].get('recipients', None)
        preresults = []
        if initial_users:
            usernames = initial_users.split(', ')
            users = get_user_model().objects.filter(username__in=usernames)
            preresults = get_user_select2_pills(users, text_only=True)
            # delete the initial data or our select2 field initials will be overwritten by django
            if 'recipients' in kwargs['initial']:
                del kwargs['initial']['recipients']
            if 'recipients' in self.initial:
                del self.initial['recipients']
            
        elif 'data' in kwargs and kwargs['data'].getlist('recipients'):
            user_ids, group_ids = self.fields['recipients'].get_user_and_group_ids_for_value(kwargs['data'].getlist('recipients'))
            
            # restrict writing to the forum group
            try:
                forum_group_id = CosinnusGroup.objects.get_cached(slugs=getattr(settings, 'NEWW_FORUM_GROUP_SLUG')).id
                if forum_group_id in group_ids and not check_user_superuser(kwargs['sender']):
                    self.restricted_recipient_flag = True
            except CosinnusGroup.DoesNotExist:
                pass
            
            users = get_user_model().objects.filter(id__in=user_ids)
            groups = CosinnusGroup.objects.get_cached(pks=group_ids)
            # save away for later
            self.targetted_groups = groups
            
            preresults = get_user_select2_pills(users, text_only=True)
            preresults.extend(get_group_select2_pills(groups, text_only=True))
                
        # TODO: sascha: returning unescaped html here breaks the javascript of django-select2
        # we need to cheat our way around select2's annoying way of clearing initial data fields
        self.fields['recipients'].choices = preresults
        self.fields['recipients'].initial = [key for key,val in preresults]
        self.initial['recipients'] = self.fields['recipients'].initial
    
    def clean_recipients(self):
        if self.restricted_recipient_flag:
            raise forms.ValidationError(_('Only Administrators may send a message to this project/group!'))
        return super(CustomWriteForm, self).clean_recipients()


class CustomReplyForm(CustomWriteForm):
    
    exchange_filter = staticmethod(user_write_permission_filter)
    
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
