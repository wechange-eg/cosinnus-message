# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings  # noqa

from appconf import AppConf


class CosinnusMessageConf(AppConf):
    SHOW_MESSAGE_SENDER_EMAIL = False
