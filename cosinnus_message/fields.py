from django.contrib.auth.models import User

from django_select2 import (AutoModelSelect2MultipleField, 
        HeavyModelSelect2MultipleChoiceField,Select2View)
from cosinnus_message.views import UserSelect2View


class UserSelect2MultipleChoiceField(HeavyModelSelect2MultipleChoiceField):
    queryset = User.objects
    search_fields = ['username__icontains', ]
    data_view = UserSelect2View
    
    def clean(self, value):
        ret = super(UserSelect2MultipleChoiceField, self).clean(value)
        # Postman doesn't like working with recipients as querysets
        return list(ret)