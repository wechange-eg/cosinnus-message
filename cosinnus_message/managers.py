# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.contenttypes.models import ContentType
from django.db import models

from taggit.models import TaggedItem


class MessageManager(models.Manager):

    def tags(self):
        event_type = ContentType.objects.get(app_label="cosinnus_message", model="message")

        tag_names = []
        for ti in TaggedItem.objects.filter(content_type_id=event_type):
            if not ti.tag.name in tag_names:
                tag_names.append(ti.tag.name)

        return tag_names
