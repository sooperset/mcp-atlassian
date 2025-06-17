"""Tests for the servers dependencies module, focusing on multi-tenant auth flow."""

import pytest
from unittest.mock import MagicMock

from mcp_atlassian.servers.dependencies import _create_user_config_for_fetcher
from mcp_atlassian.utils.oauth import OAuthConfig
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.confluence.config import ConfluenceConfig


class TestCreateUserConfigForFetcher:
    """Tests for the _create_user_config_for_fetcher function."""

    def test_oauth_auth_type_success_with_cloud_id_param(self):
        """Test OAuth auth type with cloud_id parameter provided."""
        # Setup base config with OAuth
        base_oauth_config = OAuthConfig(
            client_id="base-client-id",
            client_secret="base-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:jira-work",
            cloud_id="base-cloud-id"
        )
        base_config = JiraConfig(
            url="https://base.atlassian.net",
            auth_type="oauth",
            oauth_config=base_oauth_config
        )
        
        credentials = {"oauth_access_token": "user-access-token"}
        result_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=credentials,
        )
        
        # Verify the result
        assert isinstance(result_config, JiraConfig)
        assert result_config.auth_type == "oauth"
        assert result_config.oauth_config is not None
        assert result_config.oauth_config.access_token == "user-access-token"
        assert result_config.oauth_config.cloud_id == "base-cloud-id"
        assert result_config.oauth_config.client_id == "base-client-id"
        assert result_config.oauth_config.client_secret == "base-client-secret"


    def test_oauth_auth_type_minimal_config_success(self):
        """Test OAuth auth type with minimal base config (user-provided tokens mode)."""
        # Setup minimal base config (empty credentials)
        base_oauth_config = OAuthConfig(
            client_id="",  # Empty client_id (minimal config)
            client_secret="",  # Empty client_secret (minimal config)
            redirect_uri="",
            scope="",
            cloud_id=""
        )
        base_config = JiraConfig(
            url="https://base.atlassian.net",
            auth_type="oauth",
            oauth_config=base_oauth_config
        )
        
        # Test with user-provided cloud_id
        credentials = {"oauth_access_token": "user-access-token"}
        result_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=credentials,
            cloud_id="user-cloud-id"
        )
        
        # Verify the result
        assert isinstance(result_config, JiraConfig)
        assert result_config.auth_type == "oauth"
        assert result_config.oauth_config is not None
        assert result_config.oauth_config.access_token == "user-access-token"
        assert result_config.oauth_config.cloud_id == "user-cloud-id"
        assert result_config.oauth_config.client_id == ""  # Should preserve minimal config
        assert result_config.oauth_config.client_secret == ""  # Should preserve minimal config

    def test_oauth_auth_type_confluence_config(self):
        """Test OAuth auth type with Confluence config."""
        # Setup base config with OAuth for Confluence
        base_oauth_config = OAuthConfig(
            client_id="confluence-client-id",
            client_secret="confluence-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:confluence-space.summary",
            cloud_id="confluence-cloud-id"
        )
        base_config = ConfluenceConfig(
            url="https://confluence.atlassian.net/wiki",
            auth_type="oauth",
            oauth_config=base_oauth_config
        )
        
        # Test with user-provided credentials
        credentials = {"oauth_access_token": "confluence-user-token"}
        result_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=credentials,
        )
        
        # Verify the result
        assert isinstance(result_config, ConfluenceConfig)
        assert result_config.auth_type == "oauth"
        assert result_config.oauth_config is not None
        assert result_config.oauth_config.access_token == "confluence-user-token"
        assert result_config.oauth_config.cloud_id == "confluence-cloud-id"

    def test_oauth_auth_type_missing_access_token(self):
        """Test OAuth auth type with missing access token."""
        # Setup base config with OAuth
        base_oauth_config = OAuthConfig(
            client_id="base-client-id",
            client_secret="base-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:jira-work",
            cloud_id="base-cloud-id"
        )
        base_config = JiraConfig(
            url="https://base.atlassian.net",
            auth_type="oauth",
            oauth_config=base_oauth_config
        )
        
        # Test without access token
        credentials = {}  # Missing oauth_access_token
        
        with pytest.raises(ValueError, match="OAuth access token missing in credentials"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="oauth",
                credentials=credentials,
                cloud_id="user-cloud-id"
            )

    def test_oauth_auth_type_missing_global_oauth_config(self):
        """Test OAuth auth type with missing global OAuth config."""
        # Setup base config without OAuth
        base_config = JiraConfig(
            url="https://base.atlassian.net",
            auth_type="token",  # Not OAuth
            personal_token="base-token"
        )
        
        # Test OAuth auth_type but base config doesn't have OAuth
        credentials = {"oauth_access_token": "user-access-token"}
        
        with pytest.raises(ValueError, match="Global OAuth config.*is missing"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="oauth",
                credentials=credentials,
                cloud_id="user-cloud-id"
            )

    def test_oauth_auth_type_missing_cloud_id(self):
        """Test OAuth auth type with missing cloud_id (both parameter and base config)."""
        # Setup base config with OAuth but no cloud_id
        base_oauth_config = OAuthConfig(
            client_id="base-client-id",
            client_secret="base-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:jira-work",
            cloud_id=""  # Empty cloud_id
        )
        base_config = JiraConfig(
            url="https://base.atlassian.net",
            auth_type="oauth",
            oauth_config=base_oauth_config
        )
        
        # Test without cloud_id parameter
        credentials = {"oauth_access_token": "user-access-token"}
        
        with pytest.raises(ValueError, match="Cloud ID is required for OAuth authentication"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="oauth",
                credentials=credentials,
                cloud_id=None  # No cloud_id provided
            )

    def test_pat_auth_type_jira(self):
        """Test pat auth type for Jira."""
        # Setup base config with pat auth
        base_config = JiraConfig(
            url="https://base.atlassian.net",
            auth_type="pat",
            personal_token="base-token"
        )
        
        # Test with user-provided token
        credentials = {"personal_access_token": "user-personal-token"}
        result_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="pat",
            credentials=credentials
        )
        
        # Verify the result
        assert isinstance(result_config, JiraConfig)
        assert result_config.auth_type == "pat"
        assert result_config.personal_token == "user-personal-token"
        assert result_config.url == "https://base.atlassian.net"

    def test_multi_tenant_minimal_config_different_cloud_ids(self):
        """Test multi-tenant scenario with minimal OAuth config and different cloud IDs."""
        # Setup minimal base config (empty credentials - user-provided tokens mode)
        base_oauth_config = OAuthConfig(
            client_id="",  # Empty client_id (minimal config)
            client_secret="",  # Empty client_secret (minimal config)
            redirect_uri="",
            scope="",
            cloud_id=""  # No global cloud_id
        )
        base_config = JiraConfig(
            url="https://base.atlassian.net",
            auth_type="oauth",
            oauth_config=base_oauth_config
        )
        
        # Test tenant A with their own cloud_id and token
        tenant_a_credentials = {"oauth_access_token": "tenant-a-access-token"}
        tenant_a_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=tenant_a_credentials,
            cloud_id="tenant-a-cloud-id"
        )
        
        # Test tenant B with different cloud_id and token
        tenant_b_credentials = {"oauth_access_token": "tenant-b-access-token"}
        tenant_b_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=tenant_b_credentials,
            cloud_id="tenant-b-cloud-id"
        )
        
        # Test tenant C with different cloud_id and token
        tenant_c_credentials = {"oauth_access_token": "tenant-c-access-token"}
        tenant_c_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=tenant_c_credentials,
            cloud_id="tenant-c-cloud-id"
        )
        
        # Verify each tenant gets their own isolated config
        assert tenant_a_config.oauth_config.cloud_id == "tenant-a-cloud-id"
        assert tenant_a_config.oauth_config.access_token == "tenant-a-access-token"
        
        assert tenant_b_config.oauth_config.cloud_id == "tenant-b-cloud-id"
        assert tenant_b_config.oauth_config.access_token == "tenant-b-access-token"
        
        assert tenant_c_config.oauth_config.cloud_id == "tenant-c-cloud-id"
        assert tenant_c_config.oauth_config.access_token == "tenant-c-access-token"
        
        # Verify they all share the same minimal base configuration
        for config in [tenant_a_config, tenant_b_config, tenant_c_config]:
            assert config.oauth_config.client_id == ""  # Minimal config
            assert config.oauth_config.client_secret == ""  # Minimal config
            assert config.oauth_config.redirect_uri == ""
            assert config.oauth_config.scope == ""
            assert config.url == "https://base.atlassian.net"  # Same base URL
            assert config.auth_type == "oauth"

    def test_multi_tenant_config_isolation(self):
        """Test that user configs are completely isolated from each other."""
        # Setup minimal base config
        base_oauth_config = OAuthConfig(
            client_id="",
            client_secret="",
            redirect_uri="",
            scope="",
            cloud_id=""
        )
        base_config = JiraConfig(
            url="https://base.atlassian.net",
            auth_type="oauth",
            oauth_config=base_oauth_config
        )
        
        # Create user config for tenant 1
        tenant1_credentials = {"oauth_access_token": "tenant1-token"}
        tenant1_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=tenant1_credentials,
            cloud_id="tenant1-cloud-id"
        )
        
        # Create user config for tenant 2
        tenant2_credentials = {"oauth_access_token": "tenant2-token"}
        tenant2_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=tenant2_credentials,
            cloud_id="tenant2-cloud-id"
        )
        
        # Modify tenant1 config
        tenant1_config.oauth_config.access_token = "modified-tenant1-token"
        tenant1_config.oauth_config.cloud_id = "modified-tenant1-cloud-id"
        
        # Verify tenant2 config remains unchanged
        assert tenant2_config.oauth_config.access_token == "tenant2-token"
        assert tenant2_config.oauth_config.cloud_id == "tenant2-cloud-id"
        
        # Verify base config remains unchanged
        assert base_oauth_config.access_token is None
        assert base_oauth_config.cloud_id == ""
        
        # Verify tenant1 config has the modifications
        assert tenant1_config.oauth_config.access_token == "modified-tenant1-token"
        assert tenant1_config.oauth_config.cloud_id == "modified-tenant1-cloud-id"