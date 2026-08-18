import logging
from typing import List, Optional
from config import settings
from models.user import User

logger = logging.getLogger(__name__)

class EntraConnector:
    """Microsoft Entra ID (Azure AD) connector"""

    def __init__(self):
        self.logger = logger
        self._cache: dict = {}  # Simple role cache

    async def get_user_roles(self, user_id: str) -> List[str]:
        """Get user roles from Entra ID group membership"""
        # Check cache first
        if user_id in self._cache:
            return self._cache[user_id]

        try:
            # In Fase 0, return roles based on config mapping
            # Real implementation: query Microsoft Graph API
            # https://graph.microsoft.com/v1.0/users/{user_id}/memberOf
            roles = await self._fetch_roles_from_graph(user_id)
            self._cache[user_id] = roles
            self.logger.info(f"User {user_id} roles: {roles}")
            return roles
        except Exception as e:
            self.logger.error(f"Error getting roles for {user_id}: {e}")
            return ["Guest"]

    async def _fetch_roles_from_graph(self, user_id: str) -> List[str]:
        """Fetch roles from Microsoft Graph API"""
        # Placeholder for real Graph API call
        # Will be implemented when Entra ID credentials are available
        # For now returns default role
        return ["Guest"]

    async def validate_token(self, token: str) -> Optional[User]:
        """Validate JWT token from Entra ID"""
        try:
            import jwt
            claims = jwt.decode(
                token,
                options={"verify_signature": False},
                algorithms=["RS256"]
            )
            user_id = claims.get("upn") or claims.get("preferred_username") or claims.get("email", "")
            email = claims.get("email") or user_id
            roles = await self.get_user_roles(user_id)

            return User(
                user_id=user_id,
                email=email,
                roles=roles,
                is_admin="Admin" in roles
            )
        except Exception as e:
            self.logger.error(f"Token validation failed: {e}")
            return None

    async def validate_connection(self) -> bool:
        """Test Entra ID connection"""
        try:
            # In production: verify Graph API connectivity
            # For Fase 0 development: check if credentials are configured
            if not settings.entra_tenant_id or settings.entra_tenant_id == "your-tenant-id":
                self.logger.warning("⚠️  Entra ID not configured (using placeholder credentials)")
                return False
            self.logger.info("✅ Entra ID configured")
            return True
        except Exception as e:
            self.logger.error(f"❌ Entra ID check failed: {e}")
            return False
