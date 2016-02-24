from django.contrib.auth.models import User

from django_select2 import (HeavyModelSelect2MultipleChoiceField)
from cosinnus_message.views import UserSelect2View
from django.core.exceptions import ValidationError
from cosinnus.conf import settings
from django.http.response import Http404
from cosinnus.models.group import CosinnusGroup
from django_select2.util import JSFunction

class UserSelect2MultipleChoiceField(HeavyModelSelect2MultipleChoiceField):
    queryset = User.objects
    search_fields = ['username__icontains', ]
    data_view = UserSelect2View
    
    def __init__(self, *args, **kwargs):
        """ Enable returning HTML formatted results in django-select2 return views!
            Note: You are responsible for cleaning the content, i.e. with  django.utils.html.escape()! """
        super(UserSelect2MultipleChoiceField, self).__init__(*args, **kwargs)
        self.widget.options['escapeMarkup'] = JSFunction('function(m) { return m; }')
        # this doesn't seem to help in removing the <div> tags
        #self.widget.options['formatResult'] = JSFunction('function(data) { return data.text; }')
        #self.widget.options['formatSelection'] = JSFunction('function(data) { return data.text; }')
    
    def clean(self, value):
        """ We organize the ids gotten back from the recipient select2 field.
            This is a list of mixed ids which could either be groups or users.
            See cosinnus_messages.views.UserSelect2View for how these ids are built.
            
            Example for <value>: [u'user:1', u'group:4'] 
        """
                
        if self.required and not value:
            raise ValidationError(self.error_messages['required'])
        
        group_ids = []
        user_ids = []
        for val in value:
            value_type, value_id = val.split(':')
            if value_type == 'user':
                user_ids.append(int(value_id))
            elif value_type == 'group':
                group_ids.append(int(value_id))
            else:
                if settings.DEBUG:
                    raise Http404("Programming error: message recipient field contained unrecognised id '%s'" % val)

        # unpack the members of the selected groups
        groups = CosinnusGroup.objects.get_cached(pks=group_ids)
        recipients = set()
        for group in groups:
            recipients.update(group.users.all().exclude(is_active=False).exclude(last_login__exact=None))
            
        # combine the groups users with the directly selected users
        recipients.update( User.objects.filter(id__in=user_ids).exclude(is_active=False).exclude(last_login__exact=None) )

        return list(recipients)
    