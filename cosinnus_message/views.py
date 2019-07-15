from __future__ import unicode_literals

from cosinnus_message.rocket_chat import RocketChatConnection

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.views.generic import TemplateView
from django.views.generic.base import View

from django_select2 import Select2View, NO_ERR_RESP

from cosinnus.models.group import CosinnusGroup
from cosinnus.utils.permissions import check_user_can_see_user, check_user_superuser
from cosinnus.utils.user import filter_active_users, get_user_query_filter_for_search_terms, \
    get_group_select2_pills, get_user_select2_pills
from cosinnus.templatetags.cosinnus_tags import full_name

try:
    from django.utils.timezone import now  # Django 1.4 aware datetimes
except ImportError:
    from datetime import datetime
    now = datetime.now


User = get_user_model()


class BaseRocketChatView(TemplateView):

    template_name = 'cosinnus_message/rocket_chat.html'
    base_url = settings.COSINNUS_CHAT_BASE_URL

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['url'] = self.get_rocket_chat_url()
        return context

    def get_rocket_chat_url(self):
        return self.base_url


class RocketChatIndexView(BaseRocketChatView):

    pass


class RocketChatWriteView(BaseRocketChatView):

    def get_rocket_chat_url(self):
        user = None
        username = self.kwargs.get('username')
        if username:
            user = get_user_model().objects.filter(username=username).first()
        if user:
            return f'{self.base_url}/direct/{user.id}/'
        else:
            return self.base_url


class RocketChatWriteGroupView(BaseRocketChatView):

    queryset = CosinnusGroup.objects.filter(is_active=True)

    def get_object(self):
        slug = self.kwargs.get('slug')
        if slug:
            return self.queryset.get(slug=slug)
        return

    def get_rocket_chat_url(self):
        """
        Returns Rocket.Chat group URL with user is member of group,
        creates a new private group with group admins if not
        :return:
        """
        group_name = ''
        group = self.get_object()
        if not group:
            return self.base_url
        user = self.request.user
        group_name = ''
        if user and user.is_authenticated:
            rocket = RocketChatConnection()
            group_name = rocket.groups_request(group, user)

        if group_name:
            return f'{self.base_url}/group/{group_name}/'
        return self.base_url


class UserSelect2View(Select2View):
    """
    This view is used as API backend to serve the suggestions for the message recipient field.
    """

    def check_all_permissions(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            raise PermissionDenied

    def get_results(self, request, term, page, context):
        terms = term.strip().lower().split(' ')
        q = get_user_query_filter_for_search_terms(terms)

        users = filter_active_users(User.objects.filter(q).exclude(id__exact=request.user.id))
        # as a last filter, remove all users that that have their privacy setting to "only members of groups i am in",
        # if they aren't in a group with the user
        users = [user for user in users if check_user_can_see_user(request.user, user)]


        # | Q(username__icontains=term))
        # Filter all groups the user is a member of, and all public groups for
        # the term.
        # Use CosinnusGroup.objects.get_cached() to search in all groups
        # instead
        groups = set(CosinnusGroup.objects.get_for_user(request.user)).union(
            CosinnusGroup.objects.public())

        forum_slug = getattr(settings, 'NEWW_FORUM_GROUP_SLUG', None)
        groups = [group for group in groups if all([term.lower() in group.name.lower() for term in terms]) and (check_user_superuser(request.user) or group.slug != forum_slug)]

        # these result sets are what select2 uses to build the choice list
        #results = [("user:" + six.text_type(user.id), render_to_string('cosinnus/common/user_select_pill.html', {'type':'user','text':escape(user.first_name) + " " + escape(user.last_name), 'user': user}),)
        #           for user in users]
        #results.extend([("group:" + six.text_type(group.id), render_to_string('cosinnus/common/user_select_pill.html', {'type':'group','text':escape(group.name)}),)
        #               for group in groups])

        # sort results

        users = sorted(users, key=lambda useritem: full_name(useritem).lower())
        groups = sorted(groups, key=lambda groupitem: groupitem.name.lower())

        results = get_user_select2_pills(users)
        results.extend(get_group_select2_pills(groups))

        # Any error response, Has more results, options list
        return (NO_ERR_RESP, False, results)
