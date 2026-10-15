"""The verified security principal every authorization check receives."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Principal:
    user: Any
    organization: Any
    role: str
    investigation: Any = None

    @property
    def organization_id(self):
        return self.organization.id

    @property
    def user_id(self):
        return self.user.pk

    def has_role(self, *roles: str) -> bool:
        return self.role in roles
