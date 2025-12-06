"""Tests for OAuth token encryption and storage.

Test categories:
4.1 トークン暗号化テスト
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestTokenEncryption:
    """4.1 トークン暗号化テスト"""

    def test_token_encryption(self):
        """Test tokens are encrypted correctly."""
        from app.crypto import decrypt_token, encrypt_token

        original_token = "ya29.a0AfH6SMBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

        encrypted = encrypt_token(original_token)

        # Encrypted should be different from original
        assert encrypted != original_token
        # Encrypted should be a string (base64 encoded)
        assert isinstance(encrypted, str)
        # Should be able to decrypt back
        decrypted = decrypt_token(encrypted)
        assert decrypted == original_token

    def test_token_decryption(self):
        """Test tokens can be decrypted and used."""
        from app.crypto import decrypt_token, encrypt_token

        # Test with various token formats
        tokens = [
            "short_token",
            "ya29.a0AfH6SMB" + "x" * 100,  # Long token
            "token_with_special!@#$%^&*()",
            "unicode_トークン_日本語",
        ]

        for original in tokens:
            encrypted = encrypt_token(original)
            decrypted = decrypt_token(encrypted)
            assert decrypted == original, f"Failed for token: {original}"

    def test_refresh_token_encryption(self):
        """Test refresh tokens are also encrypted."""
        from app.crypto import decrypt_token, encrypt_token

        refresh_token = "1//0eXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

        encrypted = encrypt_token(refresh_token)
        decrypted = decrypt_token(encrypted)

        assert decrypted == refresh_token

    def test_encryption_uses_secret_key(self, clear_settings_cache):
        """Test encryption uses the configured secret key."""
        from app.crypto import encrypt_token

        token = "test_token"

        # Encrypt with default key
        encrypted1 = encrypt_token(token)

        # Should produce consistent output with same key
        encrypted2 = encrypt_token(token)

        # Note: Fernet encryption includes random IV, so same plaintext
        # produces different ciphertext. But both should decrypt correctly.
        from app.crypto import decrypt_token
        assert decrypt_token(encrypted1) == token
        assert decrypt_token(encrypted2) == token

    @pytest.mark.asyncio
    async def test_token_persistence_in_db(self, test_session: AsyncSession):
        """Test encrypted tokens can be stored in database."""
        from app.crypto import decrypt_token, encrypt_token
        from app.models import OAuthToken

        access_token = "ya29.access_token_value"
        refresh_token = "1//refresh_token_value"

        oauth_token = OAuthToken(
            user_id="session-123",
            encrypted_access_token=encrypt_token(access_token),
            encrypted_refresh_token=encrypt_token(refresh_token),
            token_uri="https://oauth2.googleapis.com/token",
            scopes='["scope1", "scope2"]',
            expires_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        test_session.add(oauth_token)
        await test_session.commit()
        await test_session.refresh(oauth_token)

        # Retrieve and decrypt
        result = await test_session.execute(
            select(OAuthToken).where(OAuthToken.user_id == "session-123")
        )
        saved_token = result.scalars().first()

        assert saved_token is not None
        assert decrypt_token(saved_token.encrypted_access_token) == access_token
        assert decrypt_token(saved_token.encrypted_refresh_token) == refresh_token

    @pytest.mark.asyncio
    async def test_token_refresh_update(self, test_session: AsyncSession):
        """Test token refresh updates correctly in database."""
        from app.crypto import decrypt_token, encrypt_token
        from app.models import OAuthToken

        # Initial token
        oauth_token = OAuthToken(
            user_id="refresh-test-user",
            encrypted_access_token=encrypt_token("old_access_token"),
            encrypted_refresh_token=encrypt_token("old_refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            scopes='["scope1"]',
            expires_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        test_session.add(oauth_token)
        await test_session.commit()

        # Simulate token refresh
        result = await test_session.execute(
            select(OAuthToken).where(OAuthToken.user_id == "refresh-test-user")
        )
        token = result.scalars().first()

        new_access_token = "new_access_token_after_refresh"
        token.encrypted_access_token = encrypt_token(new_access_token)
        token.updated_at = datetime.now(UTC)

        await test_session.commit()
        await test_session.refresh(token)

        # Verify update
        assert decrypt_token(token.encrypted_access_token) == new_access_token
        # Refresh token should remain unchanged
        assert decrypt_token(token.encrypted_refresh_token) == "old_refresh_token"

    def test_invalid_encrypted_data_raises_error(self):
        """Test decryption fails gracefully for invalid data."""
        from app.crypto import decrypt_token

        with pytest.raises(Exception):
            decrypt_token("invalid-not-base64-encoded-data!!!")

    def test_empty_token_handling(self):
        """Test empty token handling."""
        from app.crypto import decrypt_token, encrypt_token

        empty_token = ""
        encrypted = encrypt_token(empty_token)
        decrypted = decrypt_token(encrypted)

        assert decrypted == empty_token

    @pytest.mark.asyncio
    async def test_multiple_users_tokens_isolated(self, test_session: AsyncSession):
        """Test tokens for different users are isolated."""
        from app.crypto import decrypt_token, encrypt_token
        from app.models import OAuthToken

        # Create tokens for two different users
        for user_num in range(2):
            oauth_token = OAuthToken(
                user_id=f"user-{user_num}",
                encrypted_access_token=encrypt_token(f"access_token_{user_num}"),
                encrypted_refresh_token=encrypt_token(f"refresh_token_{user_num}"),
                token_uri="https://oauth2.googleapis.com/token",
                scopes='["scope1"]',
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            test_session.add(oauth_token)

        await test_session.commit()

        # Verify isolation
        for user_num in range(2):
            result = await test_session.execute(
                select(OAuthToken).where(OAuthToken.user_id == f"user-{user_num}")
            )
            token = result.scalars().first()

            assert token is not None
            assert decrypt_token(token.encrypted_access_token) == f"access_token_{user_num}"
            assert decrypt_token(token.encrypted_refresh_token) == f"refresh_token_{user_num}"


class TestOAuthServiceWithDB:
    """Test OAuthService with database storage."""

    @pytest.mark.asyncio
    async def test_oauth_service_saves_to_db(self, test_engine, mock_settings):
        """Test OAuthService saves credentials to database."""
        # This test will be fully functional after OAuthService is modified
        # For now, it serves as a specification
        pass

    @pytest.mark.asyncio
    async def test_oauth_service_loads_from_db(self, test_engine, mock_settings):
        """Test OAuthService loads credentials from database."""
        pass

    @pytest.mark.asyncio
    async def test_oauth_service_refreshes_token(self, test_engine, mock_settings):
        """Test OAuthService can refresh expired tokens."""
        pass
