# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.urlresolvers import reverse
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils.translation import ugettext_lazy as _
from django.views.generic import RedirectView, ListView, CreateView
from django.views.generic.detail import DetailView

from cosinnus.views.mixins.group import (RequireReadMixin, RequireWriteMixin,
    FilterGroupMixin, GroupFormKwargsMixin)
from cosinnus.views.mixins.tagged import TaggedListMixin

from cosinnus_message.forms import MessageForm
from cosinnus_message.models import Message


class MessageFormMixin(object):

    def dispatch(self, request, *args, **kwargs):
        self.form_view = kwargs.get('form_view', None)
        return super(MessageFormMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(MessageFormMixin, self).get_context_data(**kwargs)
        context.update({'form_view': self.form_view})
        return context

    def form_valid(self, form):
        send_mail_error = False
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
                send_mail_error = True
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
        qs = super(MessageDetailView, self).get_queryset()
        user = self.request.user
        return qs.filter_for_user(user if user.is_authenticated() else None)

message_detail_view = MessageDetailView.as_view()


class MessageSendView(RequireWriteMixin, FilterGroupMixin, MessageFormMixin,
                      GroupFormKwargsMixin, CreateView):

    form_class = MessageForm
    model = Message
    template_name = 'cosinnus_message/message_send.html'

    def get_form(self, form_class):
        """ Filter selectible recipients by this group's users """
        form = super(MessageSendView, self).get_form(form_class)
        uids = self.group.members
        uids.remove(self.request.user.id)
        form.fields['recipients'].queryset = get_user_model() \
                ._default_manager.filter(id__in=uids)
        return form

message_send_view = MessageSendView.as_view()
