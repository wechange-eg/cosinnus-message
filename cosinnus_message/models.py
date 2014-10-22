# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from cosinnus_message.conf import settings # we need this import here!

import django
if django.VERSION[:2] < (1, 7):
    from cosinnus_message import cosinnus_app
    cosinnus_app.register()
