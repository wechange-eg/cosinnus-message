# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect

from django_select2 import Select2View, NO_ERR_RESP

from cosinnus.models.group import CosinnusGroup
from postman.views import ConversationView, MessageView


class CosinnusMessageView(MessageView):
    """Display one specific message."""
    
    def get_context_data(self, **kwargs):
        """ clear the body text, do not quote the message when replying """
        context = super(CosinnusMessageView, self).get_context_data(**kwargs)
        if context['form']:
            context['form'].initial['body'] = None
        return context

class CosinnusConversationView(ConversationView):
    """Display a conversation."""
    
    def get_context_data(self, **kwargs):
        """ clear the body text, do not quote the message when replying """
        context = super(CosinnusConversationView, self).get_context_data(**kwargs)
        if context['form']:
            context['form'].initial['body'] = None
        return context


def index(request, *args, **kwargs):
    return HttpResponseRedirect(reverse('postman-index'))


class UserSelect2View(Select2View):
    """
    This view is used as API backend to serve the suggestions for the message recipient field.
    """

    def check_all_permissions(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated():
            raise PermissionDenied

    def get_results(self, request, term, page, context):
        term = term.lower()

        # username is not used as filter for the term for now, might confuse
        # users why a search result is found
        users = User.objects.filter(
            Q(first_name__icontains=term) |
            Q(last_name__icontains=term)
        )  # | Q(username__icontains=term))
        # Filter all groups the user is a member of, and all public groups for
        # the term.
        # Use CosinnusGroup.objects.get_cached() to search in all groups
        # instead
        groups = set(CosinnusGroup.objects.get_for_user(request.user)).union(
            CosinnusGroup.objects.public())
        groups = [group for group in groups if term in group.name.lower()]

        # these result sets are what select2 uses to build the choice list
        results = [("user:" + six.text_type(user.id), "%s %s" % (user.first_name, user.last_name),)
                   for user in users]
        results.extend([("group:" + six.text_type(group.id), "[[ %s ]]" % (group.name),)
                       for group in groups])

        # Any error response, Has more results, options list
        return (NO_ERR_RESP, False, results)
