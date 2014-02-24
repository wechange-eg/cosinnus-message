# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.urlresolvers import reverse
from django.http import (HttpResponseRedirect)
from django.utils.translation import ungettext, ugettext_lazy as _
from django.contrib.auth import get_user_model
from django.views.generic import (RedirectView, ListView, CreateView)
from django.views.generic.detail import DetailView

from cosinnus.views.mixins.group import (RequireReadMixin, RequireWriteMixin,
    FilterGroupMixin, GroupFormKwargsMixin)
from cosinnus.views.mixins.tagged import TaggedListMixin

from cosinnus_message.models import Message
from cosinnus_message.forms import MessageForm
from cosinnus.views.group import UserSelectMixin
from django.core.exceptions import PermissionDenied

from django.contrib import messages
from django.db import transaction

def is_recipient_or_owner(user, msg):
    """ is the given user creator or one of the recipients of the given message? """
    return user.id in [rec.id for rec in msg.recipients.all()] or user.id == msg.creator.id


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
                self.object = form.save(commit=False)
                self.object.group = self.group
                self.object.creator = self.request.user
                self.object.save()
                form.save_m2m()

                # send the actual mail
                self.object.send()
            except Exception as e:
                transaction.rollback()
                messages.error(self.request, _('Error sending mail! - %(reason)s' % {'reason':str(e)}))
                send_mail_error = True
            else:
                transaction.commit()

        if send_mail_error:
            return self.form_invalid(form)
        else:
            return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('cosinnus:message:list',
                       kwargs={'group': self.group.slug})


class MessageIndexView(RequireReadMixin, RedirectView):

    def get_redirect_url(self, **kwargs):
        return reverse('cosinnus:message:list',
                        kwargs={'group': self.group.slug})


class MessageListView(RequireReadMixin, FilterGroupMixin, TaggedListMixin, ListView):
    model = Message

    def get_queryset(self, **kwargs):
        """ Filter from view all private messages where the user is not recipient or creator """
        user = self.request.user
        group_qs = FilterGroupMixin.get_queryset(self, **kwargs)

        privates = group_qs.filter(isprivate=True)
        # filter all private messages (if logged in, filter only other user's private messages)
        if user.username:
            privates = [m for m in privates if not is_recipient_or_owner(user, m)]

        private_ids = [m.id for m in privates]
        filtered_qs = group_qs.exclude(id__in=private_ids)

        return filtered_qs


class MessageDetailView(RequireReadMixin, FilterGroupMixin, DetailView, UserSelectMixin):

    model = Message

    def get_object(self, queryset=None):
        """ disallow viewing private messages if not owner or recipient """
        obj = DetailView.get_object(self, queryset=queryset)
        user = self.request.user

        if obj.isprivate:
            isloggedin = user.username
            if not isloggedin or not is_recipient_or_owner(user, obj):
                # TODO: Sascha: how should throw an unauthorized error?
                raise PermissionDenied()

        return obj


class MessageSendView(RequireWriteMixin, FilterGroupMixin, MessageFormMixin,
                      CreateView, GroupFormKwargsMixin):

    form_class = MessageForm
    model = Message
    template_name = 'cosinnus_message/message_send.html'

    def get_object(self, queryset=None):
        return CreateView.get_object(self, queryset=queryset)

    def get_initial(self):
        initial = super(MessageSendView, self).get_initial()
        return initial

    def get_form(self, form_class):
        """ Filter selectible recipients by this group's users """
        form = CreateView.get_form(self, form_class)
        uids = self.group.members
        if self.request.user:
            uids.remove(self.request.user.id)
        form.fields['recipients'].queryset = get_user_model()._default_manager.filter(id__in=uids)
        return form

    def form_valid(self, form):
        return MessageFormMixin.form_valid(self, form)

    def get_context_data(self, **kwargs):
        context = super(MessageSendView, self).get_context_data(**kwargs)
        tags = Message.objects.tags()
        context.update({
            'tags': tags
        })

        return context

