from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from oauth2_provider.signals import app_authorized

from cosinnus_message.rocket_chat import RocketChatConnection
from cosinnus.models import UserProfile, CosinnusGroupMembership
from cosinnus.models.group import MEMBERSHIP_PENDING, MEMBERSHIP_INVITED_PENDING
from cosinnus.models.group_extra import CosinnusSociety, CosinnusProject
from cosinnus_note.models import Note


def handle_app_authorized(sender, request, token, **kwargs):
    rocket = RocketChatConnection()
    rocket.users_update(token.user, request=request)

app_authorized.connect(handle_app_authorized)


@receiver(post_save, sender=get_user_model())
def handle_user_updated(sender, instance, created, **kwargs):
    rocket = RocketChatConnection()
    if created:
        rocket.users_create(instance)
    else:
        rocket.users_update(instance)


@receiver(post_save, sender=UserProfile)
def handle_profile_updated(sender, instance, created, **kwargs):
    if not created:
        rocket = RocketChatConnection()
        rocket.users_update(instance.user)


#@receiver(post_delete, sender=get_user_model())
#def handle_user_deleted(sender, instance, **kwargs):
#    rocket = RocketChatConnection()
#    rocket.disable_user(instance)


@receiver(pre_save, sender=CosinnusSociety)
def handle_cosinnus_society_updated(sender, instance, **kwargs):
    rocket = RocketChatConnection()
    if instance.id:
        old_instance = CosinnusSociety.objects.get(pk=instance.id)
        if instance.slug != old_instance.slug:
            rocket.groups_rename(instance)
    else:
        rocket.groups_create(instance)


@receiver(pre_save, sender=CosinnusProject)
def handle_cosinnus_project_updated(sender, instance, **kwargs):
    rocket = RocketChatConnection()
    if instance.id:
        old_instance = CosinnusProject.objects.get(pk=instance.id)
        if instance.slug != old_instance.slug:
            rocket.groups_rename(instance)
    else:
        rocket.groups_create(instance)


@receiver(post_delete, sender=CosinnusSociety)
def handle_cosinnus_society_deleted(sender, instance, **kwargs):
    rocket = RocketChatConnection()
    rocket.groups_archive(instance)


@receiver(post_delete, sender=CosinnusProject)
def handle_cosinnus_project_deleted(sender, instance, **kwargs):
    rocket = RocketChatConnection()
    rocket.groups_archive(instance)


@receiver(pre_save, sender=CosinnusGroupMembership)
def handle_membership_updated(sender, instance, **kwargs):
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


@receiver(post_delete, sender=CosinnusGroupMembership)
def handle_membership_deleted(sender, instance, **kwargs):
    rocket = RocketChatConnection()
    rocket.groups_kick(instance)


@receiver(post_save, sender=Note)
def handle_note_updated(sender, instance, created, **kwargs):
    rocket = RocketChatConnection()
    if created:
        rocket.notes_create(instance)
    else:
        rocket.notes_update(instance)


@receiver(post_delete, sender=Note)
def handle_note_deleted(sender, instance, **kwargs):
    rocket = RocketChatConnection()
    rocket.notes_delete(instance)
