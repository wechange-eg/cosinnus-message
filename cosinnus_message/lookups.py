from django.core.exceptions import PermissionDenied

from ajax_select import LookupChannel

from django.contrib.auth.models import User


class MessageRecipientLookup(LookupChannel):
    model = User
    search_field = 'username'

    def get_query(self, entered_username, request):
        user = request.user
        found_users_qs = User.objects.filter(groups__in=user.groups.all).distinct()
        found_users_qs = found_users_qs.exclude(pk=user.pk).filter(username__icontains=entered_username)
        found_users_ordered_qs = found_users_qs.order_by('username')
        return found_users_ordered_qs

    def check_auth(self, request):
        if not request.user.is_authenticated:
            raise PermissionDenied
