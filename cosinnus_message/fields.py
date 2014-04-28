from django.contrib.auth.models import User

from django_select2 import AutoModelSelect2MultipleField


class UserSelect2MultipleChoiceField(AutoModelSelect2MultipleField):
    queryset = User.objects
    search_fields = ['username__icontains', ]
    
    def clean(self, value):
        ret = super(UserSelect2MultipleChoiceField, self).clean(value)
        # Postman doesn't like working with recipients as querysets
        return list(ret)