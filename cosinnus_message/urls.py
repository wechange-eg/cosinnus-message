# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf.urls import url
from cosinnus_message.views import IndexView

app_name = 'message'

cosinnus_root_patterns = [
    url(r'^$', IndexView.as_view(), name='message-global'),
]

cosinnus_group_patterns = [
]

urlpatterns = cosinnus_group_patterns + cosinnus_root_patterns
