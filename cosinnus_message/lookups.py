from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied

from django.db.models import Q

from ajax_select import LookupChannel


class MessageRecipientLookup(LookupChannel):
    model = User

    def get_query(self, q, request):
        #user = request.user

        query = q.encode('utf-8')
        results = User.objects.filter(Q(username_contains=query) | Q(firstname_contains=query) | Q(lastname_contains=query))
        print ">> got results in lookup:", results
        return results

    def get_result(self, obj):
        print ">> huhu"
        return obj.get_full_name()

    def format_match(self, obj):
        return obj.get_full_name()

    def format_item_display(self, obj):
        return obj.get_full_name()

    def check_auth(self, request):
        if not request.user.is_authenticated:
            raise PermissionDenied

