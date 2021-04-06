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
    COSINNUS_ROCKET_ENABLED = False
    COSINNUS_ROCKET_EXPORT_ENABLED = False
    
    COSINNUS_CHAT_BASE_URL = None
    COSINNUS_CHAT_GROUP_GENERAL = '%s-general'
    COSINNUS_CHAT_GROUP_NEWS = '%s-news'
    COSINNUS_CHAT_SETTINGS = {
        # General
        'UTF8_Names_Validation': '[0-9a-zA-Z-_.äÄöÖüÜß]+',
        'Favorite_Rooms': True,
        'Iframe_Restrict_Access': False,

        # Accounts
        # 'Accounts_AllowAnonymousRead': False,
        # 'Accounts_AllowAnonymousWrite': False,
        # 'Accounts_AllowDeleteOwnAccount': False,
        'Accounts_AllowUserProfileChange': False,
        'Accounts_AllowUserAvatarChange': True,
        'Accounts_AllowRealNameChange': True,
        'Accounts_AllowEmailChange': True,
        'Accounts_AllowPasswordChange': False,
        # 'Accounts_AllowUserStatusMessageChange': True,
        'Accounts_AllowUsernameChange': False,
        'Accounts_Default_User_Preferences_sidebarGroupByType': True,
        'Accounts_Default_User_Preferences_sidebarShowUnread': True,
        'Accounts_ShowFormLogin': False,  # Required to be able to login as bot on first deployment
        'Accounts_RegistrationForm': 'Disabled',
        'Accounts_RegistrationForm_LinkReplacementText': '',
        'Accounts_TwoFactorAuthentication_By_Email_Enabled': False,
        'Email_Changed_Email_Subject': 'Your Registration has been received',
        'Email_Changed_Email': 'Thank you for signing up. Your E-Mail validation link will arrive shortly.',
        'Accounts_Send_Email_When_Activating': False,
        'Accounts_Send_Email_When_Deactivating': False,
        'Accounts_Registration_AuthenticationServices_Enabled': False,
        'Accounts_TwoFactorAuthentication_Enforce_Password_Fallback': False,
        'Accounts_TwoFactorAuthentication_Enabled': False,

        # Layout
        'Layout_Home_Body': '''<p>Willkommen beim %(COSINNUS_BASE_PAGE_TITLE_TRANS)s Rocket.Chat!</p>

        <p>Schreibt private Nachrichten im Browser, per Smartphone- oder Desktop-App in Echtzeit an andere, in Projekten und Gruppen oder in eigenen Kanälen.</p>
        
        <p>Wenn du die App nach der Installation &ouml;ffnest, klicke auf <strong>Mit einem Server verbinden</strong>. Gebe im nachfolgenden Fenster folgende<strong> Serveradresse ein</strong>: <a href="%(COSINNUS_PORTAL_URL)s" target="_blank" rel="nofollow noopener noreferrer">%(COSINNUS_PORTAL_URL)s</a> und klicke auf <strong>Verbinden</strong>. Klicke auf <strong>Enter Chat</strong> und gib deine %(COSINNUS_BASE_PAGE_TITLE_TRANS)s Zugangsdaten in das sich &ouml;ffnende Fenster.</p>
        
            <p>Die Rocket.Chat-Desktops-Apps für Windows, MacOS und Linux stehen <a title="Rocket.Chat desktop apps" href="https://rocket.chat/download" target="_blank" rel="noopener">hier</a> zum Download bereit..</p>
            <p>Die native Mobile-App Rocket.Chat für Android und iOS ist bei <a title="Rocket.Chat+ on Google Play" href="https://play.google.com/store/apps/details?id=chat.rocket.android" target="_blank" rel="noopener">Google Play</a> und im  <a title="Rocket.Chat+ on the App Store" href="https://itunes.apple.com/app/rocket-chat/id1148741252" target="_blank" rel="noopener">App Store</a> erhältlich.</p>
            <p>Weitere Informationen finden Sie in der <a title="Rocket.Chat Documentation" href="https://rocket.chat/docs/" target="_blank" rel="noopener">Dokumentation</a>.</p>
            
        ''',
        'Layout_Terms_of_Service': '<a href="https://wechange.de/cms/datenschutz/">Nutzungsbedingungen</a><br><a href="https://wechange.de/cms/datenschutz/">Datenschutz</a>',
        'Layout_Login_Terms': '',
        'Layout_Privacy_Policy': '<a href="https://wechange.de/cms/datenschutz/">Datenschutz</a>',
        # 'UI_Group_Channels_By_Type': False,
        'UI_Use_Real_Name': True,

        # Rate Limiter
        'API_Enable_Rate_Limiter_Limit_Calls_Default': 10000,

        # Nachrichten
        'API_Embed': False,
        'Message_HideType_au': False,
    }
    COSINNUS_CHAT_USER = None
    COSINNUS_CHAT_PASSWORD = None
    
    # rocket authentication timeout is 30 days  by default
    COSINNUS_CHAT_CONNECTION_CACHE_TIMEOUT = 60 * 24 * 30
    
    # enables the read-only mode for the legacy postman messages system and shows an
    # "archived messages button" in the user profile
    COSINNUS_POSTMAN_ARCHIVE_MODE = False 
    