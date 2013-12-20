# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.urlresolvers import reverse
from django.http import (HttpResponseRedirect)
from django.utils.translation import ungettext, ugettext_lazy as _
from django.views.generic import (RedirectView, ListView, CreateView)
from django.views.generic.detail import DetailView

from cosinnus.views.mixins.group import (RequireReadMixin, RequireWriteMixin,
    FilterGroupMixin)
from cosinnus.views.mixins.tagged import TaggedListMixin

from cosinnus_message.models import Message
from cosinnus_message.forms import MessageForm


class MessageFormMixin(object):

    def dispatch(self, request, *args, **kwargs):
        self.form_view = kwargs.get('form_view', None)
        return super(MessageFormMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(MessageFormMixin, self).get_context_data(**kwargs)
        context.update({'form_view': self.form_view})
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.group = self.group
        self.object.author = self.request.user
        self.object.save()
        form.save_m2m()

        self.object.send()

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

class MessageDetailView(RequireReadMixin, FilterGroupMixin, DetailView):
    model = Message


class MessageSendView(RequireWriteMixin, FilterGroupMixin, MessageFormMixin,
                      CreateView):

    form_class = MessageForm
    model = Message
    template_name = 'cosinnus_message/message_send.html'

    def get_object(self, queryset=None):
        return CreateView.get_object(self, queryset=queryset)

    def get_initial(self):
        initial = super(MessageSendView, self).get_initial()
        return initial

    def form_valid(self, form):
        return MessageFormMixin.form_valid(self, form)

    def get_context_data(self, **kwargs):
        context = super(MessageSendView, self).get_context_data(**kwargs)
        tags = Message.objects.tags()
        context.update({
            'tags': tags
        })

        return context

