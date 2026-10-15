"""Users (email as username) and verified identity links (D2)."""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=200, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []
    objects = UserManager()

    class Meta:
        ordering = ("email",)

    def __str__(self) -> str:
        return self.email


class UserIdentity(models.Model):
    """A corporate identity that this user owns. `verified_via=oauth` rows are
    written by the connector link flow from the provider's signed identity;
    `admin` rows are asserted by an organization admin and flagged as such."""

    PROVIDER_MICROSOFT = "microsoft"
    PROVIDER_GOOGLE = "google"
    PROVIDER_CHOICES = [(PROVIDER_MICROSOFT, "Microsoft"), (PROVIDER_GOOGLE, "Google")]
    VERIFIED_OAUTH = "oauth"
    VERIFIED_ADMIN = "admin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="identities")
    provider = models.CharField(max_length=16, choices=PROVIDER_CHOICES)
    external_id = models.CharField(max_length=255)
    email = models.EmailField(blank=True, default="")
    verified_via = models.CharField(
        max_length=8, choices=[(VERIFIED_OAUTH, "OAuth"), (VERIFIED_ADMIN, "Admin")]
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_id"], name="uniq_identity_per_provider"
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.email or self.external_id}"
