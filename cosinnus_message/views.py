# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import transaction
from django.utils.translation import ugettext_lazy as _
from django.views.generic import RedirectView, ListView, CreateView
from django.views.generic.detail import DetailView
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User

from django_select2 import Select2View, NO_ERR_RESP

from cosinnus.views.mixins.group import (RequireReadMixin, RequireWriteMixin,
    FilterGroupMixin, GroupFormKwargsMixin)
from cosinnus.views.mixins.tagged import TaggedListMixin
from cosinnus.views.mixins.user import UserFormKwargsMixin
from cosinnus_message.models import Message
from cosinnus.models.group import CosinnusGroup


class MessageFormMixin(object):

    def dispatch(self, request, *args, **kwargs):
        self.form_view = kwargs.get('form_view', None)
        return super(MessageFormMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(MessageFormMixin, self).get_context_data(**kwargs)
        context.update({'form_view': self.form_view})
        return context

    def get_form_kwargs(self):
        kwargs = super(MessageFormMixin, self).get_form_kwargs()
        kwargs.update({
            'group': self.group,
            'user': self.request.user,
        })
        return kwargs

    def form_valid(self, form):
        with transaction.commit_manually():
            try:
                form.instance.creator = self.request.user
                form.instance.save()  # necessary for instance.recipients
                # send the actual mail
                form.instance.send(self.request)
                ret = super(MessageFormMixin, self).form_valid(form)
            except Exception as e:
                transaction.rollback()
                messages.error(self.request,
                    _('Error sending mail! - %(reason)s' % {'reason': str(e)}))
                return self.form_invalid(form)
            else:
                transaction.commit()
                return ret

    def get_success_url(self):
        return reverse('cosinnus:message:list',
                       kwargs={'group': self.group.slug})


class MessageIndexView(RequireReadMixin, RedirectView):

    def get_redirect_url(self, **kwargs):
        return reverse('cosinnus:message:list',
                       kwargs={'group': self.group.slug})

message_index_view = MessageIndexView.as_view()


class MessageListView(RequireReadMixin, FilterGroupMixin, TaggedListMixin,
                      ListView):
    model = Message

    def get_queryset(self, **kwargs):
        """
        Filter from view all private messages where the user is not
        recipient or creator
        """
        # TODO Django>=1.7: change to chained select_relatad calls
        qs = super(MessageListView, self).get_queryset(
            select_related=('creator', 'recipients',))
        user = self.request.user
        return qs.filter_for_user(user if user.is_authenticated() else None)

message_list_view = MessageListView.as_view()


class MessageDetailView(RequireReadMixin, FilterGroupMixin, DetailView):

    model = Message

    def get_queryset(self, **kwargs):
        """
        Disallow viewing private messages if not owner or recipient
        """
        # TODO Django>=1.7: change to chained select_relatad calls
        qs = super(MessageDetailView, self).get_queryset(
            select_related=('creator', 'recipients',))
        user = self.request.user
        return qs.filter_for_user(user if user.is_authenticated() else None)

message_detail_view = MessageDetailView.as_view()


class UserSelect2View(Select2View):
    def check_all_permissions(self, request, *args, **kwargs):
        user = request.user 
        if not user.is_authenticated():
            raise PermissionDenied
        
    def get_results(self, request, term, page, context):
        term = term.lower()
        
        # username is not used as filter for the term for now, might confuse users why a search result is found
        users = User.objects.filter( Q(first_name__icontains=term) | Q(last_name__icontains=term))# | Q(username__icontains=term))
        # filter all groups the user is a member of, and all public groups for the term
        # use CosinnusGroup.objects.get_cached() to search in all groups instead
        groups = set(CosinnusGroup.objects.get_for_user(request.user)).union(CosinnusGroup.objects.public())
        groups = [ group for group in groups if term in group.name.lower() ]
        
        # these result sets are what select2 uses to build the choice list
        results = [ ("user:"+str(user.id), "%s %s" % (user.first_name, user.last_name),) for user in users ]
        results.extend([ ("group:"+str(group.id), "[[ %s ]]" % (group.name),) for group in groups ])
        
        return (NO_ERR_RESP, False, results) # Any error response, Has more results, options list
