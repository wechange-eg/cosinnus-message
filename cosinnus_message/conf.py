# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from builtins import object
from django.conf import settings  # noqa

from appconf import AppConf


class CosinnusMessageConf(AppConf):
    pass


class CosinnusMessageDefaultSettings(AppConf):
    """ Settings without a prefix namespace to provide default setting values for other apps.
        These are settings used by default in cosinnus apps, such as avatar dimensions, etc.
    """
    
    class Meta(object):
        prefix = ''
        
    POSTMAN_DISALLOW_ANONYMOUS = True  # No anonymous messaging
    POSTMAN_AUTO_MODERATE_AS = True  # Auto accept all messages
    POSTMAN_SHOW_USER_AS = 'username'

    # Chat config
    COSINNUS_CHAT_BASE_URL = None
    COSINNUS_CHAT_GROUP_GENERAL = '%s-general'
    COSINNUS_CHAT_GROUP_NEWS = '%s-news'
    COSINNUS_CHAT_SETTINGS = {
        # General
        'UTF8_Names_Validation': '[0-9a-zA-Z-_.äÄöÖüÜß]+',
        'Favorite_Rooms': True,

        # Accounts
        # 'Accounts_AllowAnonymousRead': False,
        # 'Accounts_AllowAnonymousWrite': False,
        # 'Accounts_AllowDeleteOwnAccount': False,
        'Accounts_AllowUserProfileChange': False,
        'Accounts_AllowUserAvatarChange': True,
        'Accounts_AllowRealNameChange': True,
        'Accounts_AllowEmailChange': True,
        'Accounts_AllowPasswordChange': True,
        # 'Accounts_AllowUserStatusMessageChange': True,
        'Accounts_AllowUsernameChange': True,
        'Accounts_ShowFormLogin': True,
        'Accounts_Default_User_Preferences_sidebarGroupByType': True,
        'Accounts_Default_User_Preferences_sidebarShowUnread': True,


        # Layout
        'Layout_Home_Body': '''<p>Willkommen bei Rocket.Chat!</p>
    <p>Die Rocket.Chat-Desktops-Apps für Windows, MacOS und Linux stehen <a title="Rocket.Chat desktop apps" href="https://rocket.chat/download" target="_blank" rel="noopener">hier</a> zum Download bereit..</p>
    <p>Die native Mobile-App Rocket.Chat für Android und iOS ist bei <a title="Rocket.Chat+ on Google Play" href="https://play.google.com/store/apps/details?id=chat.rocket.android" target="_blank" rel="noopener">Google Play</a> und im  <a title="Rocket.Chat+ on the App Store" href="https://itunes.apple.com/app/rocket-chat/id1148741252" target="_blank" rel="noopener">App Store</a> erhältlich.</p>
    <p>Weitere Informationen finden Sie in der <a title="Rocket.Chat Documentation" href="https://rocket.chat/docs/" target="_blank" rel="noopener">Dokumentation</a>.</p>
    ''',
        'Layout_Terms_of_Service': '<a href="https://plattform-n.org/cms/datenschutz/">Nutzungsbedingungen</a><br><a href="https://wechange.de/cms/datenschutz/">Datenschutz</a>',
        'Layout_Login_Terms': 'Indem Sie fortfahren, stimmen Sie unseren <a href="https://plattform-n.org/cms/nutzungsbedingungen/">Nutzungs-</a> und <a href="https://wechange.de/cms/datenschutz/">Datenschutzbestimmungen</a> zu.',
        'Layout_Privacy_Policy': '<a href="https://wechange.de/cms/datenschutz/">Datenschutz</a>',
        # 'UI_Group_Channels_By_Type': False,
        'UI_Use_Real_Name': True,

        # Rate Limiter
        'API_Enable_Rate_Limiter_Limit_Calls_Default': 100,

        # Nachrichten
        'API_Embed': False,
        'Message_HideType_au': False,
    }
    COSINNUS_CHAT_USER = None
    COSINNUS_CHAT_PASSWORD = None
    
    COSINNUS_CHAT_CONNECTION_CACHE_TIMEOUT = 60 * 60 * 24 * 7 # rocket authentication timeout is 7 days default
