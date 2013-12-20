# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf.urls import patterns, url, include

from cosinnus_message.views import (MessageIndexView, MessageListView,
                                    MessageSendView, MessageDetailView)


cosinnus_root_patterns = patterns('',
)

cosinnus_group_patterns = patterns('',
    url(r'^$', MessageIndexView.as_view(), name='index'),
    url(r'^list/$', MessageListView.as_view(), name='list'),
    url(r'^send/$', MessageSendView.as_view(), {'form_view': 'send'}, name='send'),
    url(r'^(?P<slug>[^/]+)/$', MessageDetailView.as_view(), name='message'),
)


urlpatterns = cosinnus_group_patterns + cosinnus_root_patterns
