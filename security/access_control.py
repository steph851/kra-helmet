"""
ACCESS CONTROL — role-based access control for KRA Helmet.
BOUNDARY: Checks permissions only. Never executes actions.
Roles: admin, operator, viewer, api_client
Permissions: read, write, approve, configure, export
"""
import os
import json
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class Role(Enum):
    """User roles with increasing privilege."""
    VIEWER = "viewer"        # Read-only access
    OPERATOR = "operator"    # Read + write (onboard, file, check)
    ADMIN = "admin"          # Full access including approvals
    API_CLIENT = "api_client"  # Programmatic access


class Permission(Enum):
    """Granular permissions."""
    READ = "read"
    WRITE = "write"
    APPROVE = "approve"
    CONFIGURE = "configure"
    EXPORT = "export"
    MANAGE_USERS = "manage_users"


# Role → permission mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {Permission.READ},
    Role.OPERATOR: {Permission.READ, Permission.WRITE, Permission.EXPORT},
    Role.ADMIN: {
        Permission.READ, Permission.WRITE, Permission.APPROVE,
        Permission.CONFIGURE, Permission.EXPORT, Permission.MANAGE_USERS,
    },
    Role.API_CLIENT: {Permission.READ, Permission.WRITE, Permission.EXPORT},
}


@dataclass
class User:
    """User with role and metadata."""
    username: str
    role: Role
    api_key_hash: str = ""
    active: bool = True
    created_at: str = ""
    last_login: str = ""


class AccessControl:
    """Role-based access control system."""

    def __init__(self):
        self._users_path = Path(__file__).parent.parent / "config" / "users.json"
        self._users: dict[str, User] = {}
        self._load_users()

    def _load_users(self):
        """Load users from config."""
        if self._users_path.exists():
            try:
                data = json.loads(self._users_path.read_text(encoding="utf-8"))
                for u in data.get("users", []):
                    self._users[u["username"]] = User(
                        username=u["username"],
                        role=Role(u.get("role", "viewer")),
                        api_key_hash=u.get("api_key_hash", ""),
                        active=u.get("active", True),
                        created_at=u.get("created_at", ""),
                        last_login=u.get("last_login", ""),
                    )
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_users(self):
        """Save users to config."""
        self._users_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "users": [
                {
                    "username": u.username,
                    "role": u.role.value,
                    "api_key_hash": u.api_key_hash,
                    "active": u.active,
                    "created_at": u.created_at,
                    "last_login": u.last_login,
                }
                for u in self._users.values()
            ]
        }
        self._users_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def check_permission(self, username: str, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        user = self._users.get(username)
        if not user or not user.active:
            return False
        return permission in ROLE_PERMISSIONS.get(user.role, set())

    def require_permission(self, username: str, permission: Permission):
        """Raise PermissionError if user lacks permission."""
        if not self.check_permission(username, permission):
            raise PermissionError(
                f"User '{username}' lacks '{permission.value}' permission"
            )

    def get_user(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self._users.get(username)

    def create_user(self, username: str, role: Role, api_key_hash: str = "") -> User:
        """Create a new user."""
        from datetime import datetime, timezone, timedelta
        EAT = timezone(timedelta(hours=3))

        user = User(
            username=username,
            role=role,
            api_key_hash=api_key_hash,
            active=True,
            created_at=datetime.now(EAT).isoformat(),
        )
        self._users[username] = user
        self._save_users()
        return user

    def update_role(self, username: str, new_role: Role, admin_user: str):
        """Update user role (requires admin)."""
        self.require_permission(admin_user, Permission.MANAGE_USERS)
        user = self._users.get(username)
        if not user:
            raise ValueError(f"User not found: {username}")
        user.role = new_role
        self._save_users()

    def deactivate_user(self, username: str, admin_user: str):
        """Deactivate a user (requires admin)."""
        self.require_permission(admin_user, Permission.MANAGE_USERS)
        user = self._users.get(username)
        if not user:
            raise ValueError(f"User not found: {username}")
        user.active = False
        self._save_users()

    def list_users(self, admin_user: str) -> list[dict]:
        """List all users (requires admin)."""
        self.require_permission(admin_user, Permission.MANAGE_USERS)
        return [
            {
                "username": u.username,
                "role": u.role.value,
                "active": u.active,
                "created_at": u.created_at,
            }
            for u in self._users.values()
        ]

    def get_permissions(self, username: str) -> list[str]:
        """Get list of permissions for a user."""
        user = self._users.get(username)
        if not user or not user.active:
            return []
        return [p.value for p in ROLE_PERMISSIONS.get(user.role, set())]
