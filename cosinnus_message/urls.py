# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf.urls import patterns, url
#from django.views.generic.base import RedirectView


cosinnus_root_patterns = patterns('', )

cosinnus_group_patterns = patterns('cosinnus_message.views',
    url(r'^$', 'index', name='index'),
    # this doesn't work as a redirect to root
    #url(r'^$', RedirectView.as_view(url='/posteingang/')),
)

urlpatterns = cosinnus_group_patterns + cosinnus_root_patterns
