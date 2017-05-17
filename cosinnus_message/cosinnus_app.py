# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from cosinnus.conf import settings
from cosinnus.core.registries.attached_objects import attached_object_registry

def register():
    if 'cosinnus_message' in getattr(settings, 'COSINNUS_DISABLED_COSINNUS_APPS', []):
        return
    
    # Import here to prevent import side effects
    from django.utils.translation import ugettext_lazy as _
    from django.utils.translation import pgettext_lazy

    from cosinnus.core.registries import app_registry, url_registry

    from cosinnus_message.urls import (cosinnus_group_patterns,
        cosinnus_root_patterns)

    app_registry.register('cosinnus_message', 'message', _('Message'))
    attached_object_registry.register('postman.Message',
                             'cosinnus_message.utils.renderer.MessageRenderer')
    url_registry.register('cosinnus_message', cosinnus_root_patterns,
        cosinnus_group_patterns)

    # makemessages replacement protection
    name = pgettext_lazy("the_app", "message")