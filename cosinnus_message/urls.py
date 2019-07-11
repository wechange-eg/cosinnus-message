# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf.urls import url

from cosinnus_message.api.views import MessageExportView
from cosinnus_message.views import MessageIndexView

app_name = 'message'

cosinnus_root_patterns = [
    url(r'^messages/$', MessageIndexView.as_view(), name='message-global'),
    url(r'^messages/export/', MessageExportView.as_view(), name='message-export'),
]

cosinnus_group_patterns = [
]

urlpatterns = cosinnus_group_patterns + cosinnus_root_patterns
