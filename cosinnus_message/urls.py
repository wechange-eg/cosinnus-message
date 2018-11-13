# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf.urls import url
from cosinnus_message import views

app_name = 'message'

cosinnus_root_patterns = []

cosinnus_group_patterns = [
    url(r'^$', views.index, name='index'),
    # this doesn't work as a redirect to root
    #url(r'^$', RedirectView.as_view(url='/posteingang/')),
]

urlpatterns = cosinnus_group_patterns + cosinnus_root_patterns
