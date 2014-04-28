from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from MySQLdb import escape_string


from postman.fields import BasicCommaSeparatedUserField
from ajax_select.fields import AutoCompleteField

"""
SASCHA: Ok, also dass das Form nicht richtig angezeigt wird liegt denke ich 
sehr sicher an der falschen Ajax_select plugin version (from ajax_select.fields import AutoCompleteField)
mit der das neue Postman nicht mehr klar kommt oder so

Doku ist hier: http://django-postman.readthedocs.org/en/latest/views.html
"""

class CommaSeparatedUserFullnameField(BasicCommaSeparatedUserField, AutoCompleteField):
    def __init__(self, *args, **kwargs):
        if not args and 'channel' not in kwargs:
            kwargs.update([('channel', 'postman_users')])
        super(CommaSeparatedUserFullnameField, self).__init__(*args, **kwargs)

    def set_arg(self, value):
        print ">> val:", value
        if hasattr(self, 'channel'):
            setattr(self, 'channel', value)

        if hasattr(self.widget, 'channel'):
            setattr(self.widget, 'channel', value)

    def clean(self, value):
        print ">> omg"
        return super(CommaSeparatedUserFullnameField, self).clean(value)
        # instead of calling super().clean() i run clean() manually
        # to avoid filter by username from the base class
        # names = super(CommaSeparatedUserFullnameField, self).clean(value)
        names = self.to_python(value)
        self.validate(value)
        self.run_validators(value)

        if not names:
            return []
        params = ', '.join(["'%s'" % escape_string(x.encode('utf-8'))
                             for x in names])
        query = """SELECT a.* FROM auth_user AS a, (
                      SELECT id, CONCAT(first_name, ' ', last_name) AS fullname
                      FROM auth_user) AS b
                    WHERE a.id = b.id AND b.fullname IN (""" + params + """)"""
        users = list(User.objects.raw(query))
        unknown_names = set(names) ^ set([u.get_full_name() for u in users])
        errors = []
        if unknown_names:
            errors.append(self.error_messages['unknown'].format(
                users=', '.join(unknown_names)))
        if errors:
            raise ValidationError(errors)
        return users

