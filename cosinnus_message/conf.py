# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings  # noqa

from appconf import AppConf


class CosinnusMessageConf(AppConf):
    pass


class CosinnusMessageDefaultSettings(AppConf):
    """ Settings without a prefix namespace to provide default setting values for other apps.
        These are settings used by default in cosinnus apps, such as avatar dimensions, etc.
    """
    
    class Meta:
        prefix = ''
        
    POSTMAN_DISALLOW_ANONYMOUS = True  # No anonymous messaging
    POSTMAN_AUTO_MODERATE_AS = True  # Auto accept all messages
    POSTMAN_SHOW_USER_AS = 'username'