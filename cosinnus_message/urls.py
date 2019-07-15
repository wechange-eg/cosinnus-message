# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf.urls import url

from cosinnus_message.views import *

app_name = 'message'

cosinnus_root_patterns = [
    url(r'^messages/$', RocketChatIndexView.as_view(), name='message-global'),
    url(r'^messages/write/(?P<username>[^/]+)/$', RocketChatWriteView.as_view(), name='message-write'),
    url(r'^messages/write/group/(?P<slug>[^/]+)/$', RocketChatWriteGroupView.as_view(), name='message-write-group'),
]

cosinnus_group_patterns = [
]

urlpatterns = cosinnus_group_patterns + cosinnus_root_patterns
