"""Deactivating a user offboards them everywhere (links revoked, investigations
cancelled). Routed through organizations.api so every registered hook runs."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import User


@receiver(pre_save, sender=User)
def _remember_active(sender, instance, **kwargs):
    if instance.pk:
        instance._was_active = User.objects.filter(pk=instance.pk, is_active=True).exists()
    else:
        instance._was_active = True


@receiver(post_save, sender=User)
def _offboard_on_deactivation(sender, instance, **kwargs):
    if getattr(instance, "_was_active", True) and not instance.is_active:
        from organizations.api import offboard_user_everywhere

        offboard_user_everywhere(instance)
