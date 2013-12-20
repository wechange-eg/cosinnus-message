# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf.urls import patterns, url, include

from cosinnus_message.views import MessageIndexView

from ajax_select import urls as ajax_select_urls
from dajaxice.core import dajaxice_autodiscover, dajaxice_config



dajaxice_autodiscover()

cosinnus_root_patterns = patterns('',
)

cosinnus_group_patterns = patterns('',
    url(r'^$', MessageIndexView.as_view(), name='index'),
)

urlpatterns = patterns('',
    url(r'^lookups/', include(ajax_select_urls)),
    url(r'^messages/', include('postman.urls')),
)

urlpatterns += cosinnus_group_patterns + cosinnus_root_patterns
