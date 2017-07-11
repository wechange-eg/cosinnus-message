# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect

from django_select2 import Select2View, NO_ERR_RESP

from cosinnus.models.group import CosinnusGroup
from postman.views import ConversationView, MessageView, csrf_protect_m,\
    login_required_m, _get_referer
from django.views.generic.base import View
from postman.models import Message
from django.http.response import Http404
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.html import escape
from django.template.loader import render_to_string
from cosinnus.utils.urls import safe_redirect
from django.contrib.auth import get_user_model
from cosinnus.utils.permissions import check_user_can_see_user
from cosinnus.models.tagged import BaseTagObject
from cosinnus.utils.user import filter_active_users,\
    get_user_query_filter_for_search_terms, get_group_select2_pills,\
    get_user_select2_pills

try:
    from django.utils.timezone import now  # Django 1.4 aware datetimes
except ImportError:
    from datetime import datetime
    now = datetime.now
from django.utils.translation import ugettext_lazy as _

User = get_user_model()


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



class UpdateMessageMixin(object):
    """
    Code common to the archive/delete/undelete actions.

    Attributes:
        ``field_bit``: a part of the name of the field to update
        ``success_msg``: the displayed text in case of success
    Optional attributes:
        ``field_value``: the value to set in the field
        ``success_url``: where to redirect to after a successful POST

    """
    http_method_names = ['post']
    field_value = None
    field_bit = None
    recipient_only_field_bit = None
    success_url = None

    @csrf_protect_m
    @login_required_m
    def dispatch(self, *args, **kwargs):
        return super(UpdateMessageMixin, self).dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        next_url = _get_referer(request) or 'postman_inbox'
        
        """ This is all we wanted to do that we needed to override the postman views for """
        pks = request.POST.get('pks', None)
        if pks is None:
            pks = [k.split('__')[1] for k,v in request.POST.items() if 'delete_pk' in k and v=='true']

        tpks = request.POST.get('tpks', None)
        if tpks is None:
            tpks = [k.split('__')[1] for k,v in request.POST.items() if 'delete_tpk' in k and v=='true']
        
        if pks or tpks:
            user = request.user
            filter = Q(pk__in=pks) | Q(thread__in=tpks)
            if self.recipient_only_field_bit:
                recipient_rows = Message.objects.as_recipient(user, filter).update(**{self.recipient_only_field_bit: self.field_value})
            else:
                recipient_rows = Message.objects.as_recipient(user, filter).update(**{'recipient_{0}'.format(self.field_bit): self.field_value})
                sender_rows = Message.objects.as_sender(user, filter).update(**{'sender_{0}'.format(self.field_bit): self.field_value})
            if not (recipient_rows or sender_rows):
                raise Http404  # abnormal enough, like forged ids
            messages.success(request, self.success_msg, fail_silently=True)
            next_url = request.GET.get('next', None)
            next_url = safe_redirect(next_url, request) if next_url else None
            return redirect(next_url or self.success_url or request.META.get('HTTP_REFERER', reverse('postman:inbox')))
        else:
            messages.warning(request, _("Select at least one object."), fail_silently=True)
            return redirect(next_url)


class ArchiveView(UpdateMessageMixin, View):
    """Mark messages/conversations as archived."""
    field_bit = 'archived'
    success_msg = _("Messages or conversations successfully archived.")
    field_value = True


class DeleteView(UpdateMessageMixin, View):
    """Mark messages/conversations as deleted."""
    field_bit = 'deleted_at'
    success_msg = _("Messages or conversations successfully deleted.")
    field_value = now()
    
class MarkAsReadView(UpdateMessageMixin, View):
    """Mark messages/conversations as read."""
    recipient_only_field_bit = 'read_at'
    success_msg = _("Messages were marked as read.")
    field_value = now()


class UndeleteView(UpdateMessageMixin, View):
    """Revert messages/conversations from marked as deleted."""
    field_bit = 'deleted_at'
    success_msg = _("Messages or conversations successfully recovered.")








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
        groups = [group for group in groups if all([term.lower() in group.name.lower() for term in terms])]

        # these result sets are what select2 uses to build the choice list
        
        
        
        #results = [("user:" + six.text_type(user.id), render_to_string('cosinnus/common/user_select_pill.html', {'type':'user','text':escape(user.first_name) + " " + escape(user.last_name), 'user': user}),)
        #           for user in users]
        #results.extend([("group:" + six.text_type(group.id), render_to_string('cosinnus/common/user_select_pill.html', {'type':'group','text':escape(group.name)}),)
        #               for group in groups])
        
        results = get_user_select2_pills(users)
        results.extend(get_group_select2_pills(groups))

        # Any error response, Has more results, options list
        return (NO_ERR_RESP, False, results)



