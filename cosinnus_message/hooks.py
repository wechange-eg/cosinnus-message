from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from oauth2_provider.signals import app_authorized

from cosinnus_message.rocket_chat import RocketChatConnection,\
    delete_cached_rocket_connection
from cosinnus.models import UserProfile, CosinnusGroupMembership
from cosinnus.models.group import MEMBERSHIP_PENDING, MEMBERSHIP_INVITED_PENDING
from cosinnus.models.group_extra import CosinnusSociety, CosinnusProject
from cosinnus_note.models import Note
from cosinnus.core import signals

import logging
logger = logging.getLogger(__name__)


if settings.COSINNUS_ROCKET_ENABLED:
    def handle_app_authorized(sender, request, token, **kwargs):
        rocket = RocketChatConnection()
        rocket.users_update(token.user, request=request)

    app_authorized.connect(handle_app_authorized)
    
    @receiver(pre_save, sender=get_user_model())
    def handle_user_updated(sender, instance, created, **kwargs):
        # TODO: does this hook trigger correctly?
        # this handles the user update, it is not in post_save!
        if instance.id:
            try:
                rocket = RocketChatConnection()
                old_instance = get_user_model().objects.get(pk=instance.id)
                force = any([getattr(instance, fname) != getattr(old_instance, fname) \
                                for fname in ('password', 'first_name', 'last_name', 'email')])
                password_updated = bool(instance.password != old_instance.password)
                rocket.users_update(instance, force_user_update=force, update_password=password_updated)
            except Exception as e:
                logger.exception(e)
    
    
    @receiver(signals.user_password_changed)
    def handle_user_password_updated(sender, user, **kwargs):
        try:
            rocket = RocketChatConnection()
            rocket.users_update(user, force_user_update=True, update_password=True)
            delete_cached_rocket_connection(user)
        except Exception as e:
            logger.exception(e)
    
    @receiver(post_save, sender=UserProfile)
    def handle_profile_updated(sender, instance, created, **kwargs):
        try:
            rocket = RocketChatConnection()
            if created:
                rocket.users_create(instance.user)
            else:
                rocket.users_update(instance.user)
        except Exception as e:
            logger.exception(e)

    @receiver(pre_save, sender=CosinnusSociety)
    def handle_cosinnus_society_updated(sender, instance, **kwargs):
        try:
            rocket = RocketChatConnection()
            if instance.id:
                old_instance = CosinnusSociety.objects.get(pk=instance.id)
                if instance.slug != old_instance.slug:
                    rocket.groups_rename(instance)
            else:
                rocket.groups_create(instance)
        except Exception as e:
            logger.exception(e)

    @receiver(pre_save, sender=CosinnusProject)
    def handle_cosinnus_project_updated(sender, instance, **kwargs):
        try:
            rocket = RocketChatConnection()
            if instance.id:
                old_instance = CosinnusProject.objects.get(pk=instance.id)
                if instance.slug != old_instance.slug:
                    rocket.groups_rename(instance)
            else:
                rocket.groups_create(instance)
        except Exception as e:
            logger.exception(e)

    @receiver(post_delete, sender=CosinnusSociety)
    def handle_cosinnus_society_deleted(sender, instance, **kwargs):
        try:
            rocket = RocketChatConnection()
            rocket.groups_archive(instance)
        except Exception as e:
            logger.exception(e)

    @receiver(post_delete, sender=CosinnusProject)
    def handle_cosinnus_project_deleted(sender, instance, **kwargs):
        try:
            rocket = RocketChatConnection()
            rocket.groups_archive(instance)
        except Exception as e:
            logger.exception(e)

    @receiver(pre_save, sender=CosinnusGroupMembership)
    def handle_membership_updated(sender, instance, **kwargs):
        try:
            rocket = RocketChatConnection()
            is_pending = instance.status in (MEMBERSHIP_PENDING, MEMBERSHIP_INVITED_PENDING)
            if instance.id:
                old_instance = CosinnusGroupMembership.objects.get(pk=instance.id)
                #status_changed = instance.status != old_instance.status
                was_pending = old_instance.status in (MEMBERSHIP_PENDING, MEMBERSHIP_INVITED_PENDING)
                user_changed = instance.user_id != old_instance.user_id
                group_changed = instance.group_id != old_instance.group_id
                is_moderator_changed = instance.is_moderator != old_instance.is_moderator
    
                # Invalidate old membership
                if (is_pending and not was_pending) or user_changed or group_changed:
                    rocket.groups_kick(old_instance)
    
                # Create new membership
                if (was_pending and not is_pending) or user_changed or group_changed:
                    rocket.groups_invite(instance)
    
                # Update membership
                if not is_pending and is_moderator_changed:
                    # Upgrade
                    if not old_instance.is_moderator and instance.is_moderator:
                        rocket.groups_add_moderator(instance)
                    # Downgrade
                    elif old_instance.is_moderator and not instance.is_moderator:
                        rocket.groups_remove_moderator(instance)
            elif not is_pending:
                # Create new membership
                rocket.groups_invite(instance)
                if instance.is_moderator:
                    rocket.groups_add_moderator(instance)
        except Exception as e:
            logger.exception(e)

    @receiver(post_delete, sender=CosinnusGroupMembership)
    def handle_membership_deleted(sender, instance, **kwargs):
        try:
            rocket = RocketChatConnection()
            rocket.groups_kick(instance)
        except Exception as e:
            logger.exception(e)

    @receiver(post_save, sender=Note)
    def handle_note_updated(sender, instance, created, **kwargs):
        try:
            rocket = RocketChatConnection()
            if created:
                rocket.notes_create(instance)
            else:
                rocket.notes_update(instance)
        except Exception as e:
            logger.exception(e)

    @receiver(post_delete, sender=Note)
    def handle_note_deleted(sender, instance, **kwargs):
        rocket = RocketChatConnection()
        rocket.notes_delete(instance)


    @receiver(signals.pre_userprofile_delete)
    def handle_note_deleted(sender, profile, **kwargs):
        """ Called when a user deletes their account. Completely deletes the user's rocket profile """
        rocket = RocketChatConnection()
        rocket.users_delete(profile.user)
