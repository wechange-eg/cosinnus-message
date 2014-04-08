# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf.urls import patterns, url


cosinnus_root_patterns = patterns('', )

cosinnus_group_patterns = patterns('cosinnus_message.views',
    url(r'^$',
        'message_index_view',
        name='index'),

    url(r'^list/$',
        'message_list_view',
        name='list'),

    url(r'^send/$',
        'message_send_view',
        {'form_view': 'send'},
        name='send'),

    url(r'^(?P<slug>[^/]+)/$',
        'message_detail_view',
        name='message'),
)

urlpatterns = cosinnus_group_patterns + cosinnus_root_patterns
