# -*- coding: utf-8 -*-
from django.contrib import admin

from cosinnus_message.models import Message

class MessageModelAdmin(admin.ModelAdmin):
    pass

admin.site.register(Message, MessageModelAdmin)