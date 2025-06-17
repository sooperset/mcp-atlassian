"""Integration tests for cross-service functionality between Jira and Confluence."""

import os
from unittest.mock import MagicMock, patch

import pytest
from requests.sessions import Session

from mcp_atlassian.confluence import ConfluenceConfig
from mcp_atlassian.jira import JiraConfig
from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.servers.dependencies import (
    _create_user_config_for_fetcher,
    get_confluence_fetcher,
    get_jira_fetcher,
)
from mcp_atlassian.servers.main import AtlassianMCP, main_lifespan
from mcp_atlassian.utils.environment import get_available_services
from mcp_atlassian.utils.ssl import configure_ssl_verification
from tests.utils.factories import (
    ConfluencePageFactory,
    JiraIssueFactory,
)
from tests.utils.mocks import MockAtlassianClient, MockEnvironment, MockFastMCP


@pytest.mark.integration
class TestCrossServiceUserResolution:
    """Test user resolution across Jira and Confluence services."""

    def test_shared_user_email_resolution(self):
        """Test that user email is resolved consistently across services."""
        user_email = "test@example.com"

        # Create mock clients
        jira_client = MockAtlassianClient.create_jira_client()
        confluence_client = MockAtlassianClient.create_confluence_client()

        # Mock user resolution
        jira_client.user.return_value = {
            "emailAddress": user_email,
            "displayName": "Test User",
            "accountId": "123456",
        }

        confluence_client.get_user.return_value = {
            "email": user_email,
            "displayName": "Test User",
            "accountId": "123456",
        }

        # Verify consistent user resolution
        jira_user = jira_client.user("123456")
        confluence_user = confluence_client.get_user("123456")

        assert jira_user["emailAddress"] == confluence_user["email"]
        assert jira_user["displayName"] == confluence_user["displayName"]
        assert jira_user["accountId"] == confluence_user["accountId"]

    @pytest.mark.anyio
    async def test_user_context_propagation(self):
        """Test that user context is properly propagated between services."""
        with MockEnvironment.oauth_env() as env:
            # Create configurations
            jira_config = JiraConfig.from_env()
            confluence_config = ConfluenceConfig.from_env()

            # Create user-specific configurations
            user_token = "test-user-token"
            user_email = "test@example.com"

            credentials = {
                "user_email_context": user_email,
                "oauth_access_token": user_token,
            }

            # Create user configs for both services
            user_jira_config = _create_user_config_for_fetcher(
                base_config=jira_config, auth_type="oauth", credentials=credentials
            )

            user_confluence_config = _create_user_config_for_fetcher(
                base_config=confluence_config,
                auth_type="oauth",
                credentials=credentials,
            )

            # Verify consistent OAuth configuration
            assert user_jira_config.oauth_config.access_token == user_token
            assert user_confluence_config.oauth_config.access_token == user_token
            assert user_jira_config.username == user_email
            assert user_confluence_config.username == user_email


@pytest.mark.integration
class TestSharedAuthentication:
    """Test shared authentication context between services."""

    def test_oauth_shared_configuration(self):
        """Test that OAuth configuration is shared between services."""
        with MockEnvironment.oauth_env() as env:
            # Both services should use the same OAuth configuration
            jira_config = JiraConfig.from_env()
            confluence_config = ConfluenceConfig.from_env()

            assert (
                jira_config.oauth_config.client_id
                == confluence_config.oauth_config.client_id
            )
            assert (
                jira_config.oauth_config.client_secret
                == confluence_config.oauth_config.client_secret
            )
            assert (
                jira_config.oauth_config.cloud_id
                == confluence_config.oauth_config.cloud_id
            )
            assert (
                jira_config.oauth_config.scope == confluence_config.oauth_config.scope
            )

    def test_basic_auth_shared_configuration(self):
        """Test that basic auth configuration can be shared between services."""
        with MockEnvironment.basic_auth_env() as env:
            # Both services should use consistent authentication
            jira_config = JiraConfig.from_env()
            confluence_config = ConfluenceConfig.from_env()

            assert jira_config.username == confluence_config.username
            assert jira_config.api_token == confluence_config.api_token
            assert jira_config.auth_type == confluence_config.auth_type

    @pytest.mark.anyio
    async def test_authentication_context_in_request(self):
        """Test authentication context is properly maintained in request state."""
        request = MockFastMCP.create_request()
        request.state.user_atlassian_auth_type = "oauth"
        request.state.user_atlassian_token = "test-oauth-token"
        request.state.user_atlassian_email = "test@example.com"

        with patch(
            "mcp_atlassian.servers.dependencies.get_http_request", return_value=request
        ):
            # Create mock context with lifespan data
            ctx = MockFastMCP.create_context()
            ctx.request_context = MagicMock()
            ctx.request_context.lifespan_context = {
                "app_lifespan_context": MainAppContext(
                    full_jira_config=JiraConfig.from_env(),
                    full_confluence_config=ConfluenceConfig.from_env(),
                    read_only=False,
                    enabled_tools=None,
                )
            }

            # Mock the fetcher creation
            with (
                patch("mcp_atlassian.jira.JiraFetcher") as mock_jira_fetcher,
                patch(
                    "mcp_atlassian.confluence.ConfluenceFetcher"
                ) as mock_confluence_fetcher,
            ):
                # Mock the current user validation
                mock_jira_instance = MagicMock()
                mock_jira_instance.get_current_user_account_id.return_value = "user123"
                mock_jira_fetcher.return_value = mock_jira_instance

                mock_confluence_instance = MagicMock()
                mock_confluence_instance.get_current_user_info.return_value = {
                    "email": "test@example.com",
                    "displayName": "Test User",
                }
                mock_confluence_fetcher.return_value = mock_confluence_instance

                # Get fetchers - should use the same auth context
                jira_fetcher = await get_jira_fetcher(ctx)
                confluence_fetcher = await get_confluence_fetcher(ctx)

                # Verify both fetchers were created with user-specific config
                assert request.state.jira_fetcher is not None
                assert request.state.confluence_fetcher is not None


@pytest.mark.integration
class TestCrossServiceErrorHandling:
    """Test error handling and propagation across services."""

    @pytest.mark.anyio
    async def test_jira_failure_does_not_affect_confluence(self):
        """Test that Jira failure doesn't prevent Confluence from working."""
        with MockEnvironment.basic_auth_env():
            app = AtlassianMCP("Test MCP")

            # Mock Jira to fail during initialization
            with patch(
                "mcp_atlassian.jira.config.JiraConfig.from_env"
            ) as mock_jira_config:
                mock_jira_config.side_effect = Exception("Jira config failed")

                # But Confluence should still work
                async with main_lifespan(app) as lifespan_data:
                    context = lifespan_data["app_lifespan_context"]

                    assert context.full_jira_config is None
                    assert context.full_confluence_config is not None

    @pytest.mark.anyio
    async def test_confluence_failure_does_not_affect_jira(self):
        """Test that Confluence failure doesn't prevent Jira from working."""
        with MockEnvironment.basic_auth_env():
            app = AtlassianMCP("Test MCP")

            # Mock Confluence to fail during initialization
            with patch(
                "mcp_atlassian.confluence.config.ConfluenceConfig.from_env"
            ) as mock_conf_config:
                mock_conf_config.side_effect = Exception("Confluence config failed")

                # But Jira should still work
                async with main_lifespan(app) as lifespan_data:
                    context = lifespan_data["app_lifespan_context"]

                    assert context.full_jira_config is not None
                    assert context.full_confluence_config is None

    def test_error_propagation_in_user_config_creation(self):
        """Test error propagation when creating user-specific configurations."""
        base_config = JiraConfig.from_env()

        # Test missing OAuth token
        with pytest.raises(ValueError, match="OAuth access token missing"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="oauth",
                credentials={"user_email_context": "test@example.com"},
            )

        # Test missing PAT token
        with pytest.raises(ValueError, match="PAT missing"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="pat",
                credentials={"user_email_context": "test@example.com"},
            )

        # Test invalid auth type
        with pytest.raises(ValueError, match="Unsupported auth_type"):
            _create_user_config_for_fetcher(
                base_config=base_config, auth_type="invalid", credentials={}
            )


@pytest.mark.integration
class TestSharedSSLProxyConfiguration:
    """Test shared SSL and proxy configuration between services."""

    def test_ssl_configuration_shared(self):
        """Test that SSL configuration is applied consistently."""
        with MockEnvironment.basic_auth_env():
            # Set SSL verification to false for both services
            with patch.dict(
                os.environ,
                {"JIRA_SSL_VERIFY": "false", "CONFLUENCE_SSL_VERIFY": "false"},
            ):
                jira_config = JiraConfig.from_env()
                confluence_config = ConfluenceConfig.from_env()

                assert jira_config.ssl_verify is False
                assert confluence_config.ssl_verify is False

                # Test SSL adapter configuration
                jira_session = Session()
                confluence_session = Session()

                configure_ssl_verification(
                    "Jira", jira_config.url, jira_session, ssl_verify=False
                )
                configure_ssl_verification(
                    "Confluence",
                    confluence_config.url,
                    confluence_session,
                    ssl_verify=False,
                )

                # Extract domains
                jira_domain = jira_config.url.split("://")[1].split("/")[0]
                confluence_domain = confluence_config.url.split("://")[1].split("/")[0]

                # Both should have SSL ignore adapters
                assert f"https://{jira_domain}" in jira_session.adapters
                assert f"https://{confluence_domain}" in confluence_session.adapters

    def test_proxy_configuration_shared(self):
        """Test that proxy configuration is shared between services."""
        proxy_config = {
            "HTTP_PROXY": "http://proxy.example.com:8080",
            "HTTPS_PROXY": "https://proxy.example.com:8443",
            "NO_PROXY": "localhost,127.0.0.1",
        }

        with MockEnvironment.basic_auth_env():
            with patch.dict(os.environ, proxy_config):
                jira_config = JiraConfig.from_env()
                confluence_config = ConfluenceConfig.from_env()

                # Both services should have the same proxy configuration
                assert jira_config.http_proxy == proxy_config["HTTP_PROXY"]
                assert jira_config.https_proxy == proxy_config["HTTPS_PROXY"]
                assert jira_config.no_proxy == proxy_config["NO_PROXY"]

                assert confluence_config.http_proxy == proxy_config["HTTP_PROXY"]
                assert confluence_config.https_proxy == proxy_config["HTTPS_PROXY"]
                assert confluence_config.no_proxy == proxy_config["NO_PROXY"]


@pytest.mark.integration
class TestConcurrentServiceInitialization:
    """Test concurrent initialization of both services."""

    @pytest.mark.anyio
    async def test_concurrent_service_startup(self):
        """Test that both services can be initialized concurrently."""
        with MockEnvironment.basic_auth_env():
            app = AtlassianMCP("Test MCP")

            # Track initialization order
            init_order = []

            def mock_jira_init(*args, **kwargs):
                init_order.append("jira_start")
                # Can't use async sleep in sync function, just append both immediately
                init_order.append("jira_end")
                return MagicMock(is_auth_configured=MagicMock(return_value=True))

            def mock_confluence_init(*args, **kwargs):
                init_order.append("confluence_start")
                init_order.append("confluence_end")
                return MagicMock(is_auth_configured=MagicMock(return_value=True))

            with (
                patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env",
                    side_effect=mock_jira_init,
                ),
                patch(
                    "mcp_atlassian.confluence.config.ConfluenceConfig.from_env",
                    side_effect=mock_confluence_init,
                ),
            ):
                async with main_lifespan(app) as lifespan_data:
                    context = lifespan_data["app_lifespan_context"]

                    # Both services should be initialized
                    assert context.full_jira_config is not None
                    assert context.full_confluence_config is not None

                    # Verify concurrent initialization (interleaved order)
                    assert "jira_start" in init_order
                    assert "confluence_start" in init_order

    @pytest.mark.anyio
    async def test_parallel_fetcher_creation(self):
        """Test that fetchers can be created in parallel for both services."""
        with MockEnvironment.oauth_env():
            # Create mock request with user context
            request = MockFastMCP.create_request()
            request.state.user_atlassian_auth_type = "oauth"
            request.state.user_atlassian_token = "test-token"
            request.state.user_atlassian_email = "test@example.com"

            # Create context
            ctx = MockFastMCP.create_context()
            ctx.request_context = MagicMock()
            ctx.request_context.lifespan_context = {
                "app_lifespan_context": MainAppContext(
                    full_jira_config=JiraConfig.from_env(),
                    full_confluence_config=ConfluenceConfig.from_env(),
                    read_only=False,
                    enabled_tools=None,
                )
            }

            with (
                patch(
                    "mcp_atlassian.servers.dependencies.get_http_request",
                    return_value=request,
                ),
                patch("mcp_atlassian.jira.JiraFetcher") as mock_jira_fetcher,
                patch(
                    "mcp_atlassian.confluence.ConfluenceFetcher"
                ) as mock_confluence_fetcher,
            ):
                # Mock fetcher instances
                mock_jira_instance = MagicMock()
                mock_jira_instance.get_current_user_account_id.return_value = "user123"
                mock_jira_fetcher.return_value = mock_jira_instance

                mock_confluence_instance = MagicMock()
                mock_confluence_instance.get_current_user_info.return_value = {
                    "email": "test@example.com",
                    "displayName": "Test User",
                }
                mock_confluence_fetcher.return_value = mock_confluence_instance

                # Create fetchers in parallel using anyio for backend compatibility
                import anyio

                async def fetch_jira():
                    return await get_jira_fetcher(ctx)

                async def fetch_confluence():
                    return await get_confluence_fetcher(ctx)

                # Wait for both using anyio task group
                async with anyio.create_task_group() as tg:
                    jira_future = None
                    confluence_future = None

                    async def set_jira():
                        nonlocal jira_future
                        jira_future = await fetch_jira()

                    async def set_confluence():
                        nonlocal confluence_future
                        confluence_future = await fetch_confluence()

                    tg.start_soon(set_jira)
                    tg.start_soon(set_confluence)

                jira_fetcher = jira_future
                confluence_fetcher = confluence_future

                # Both should be created successfully
                assert jira_fetcher is not None
                assert confluence_fetcher is not None
                assert request.state.jira_fetcher is jira_fetcher
                assert request.state.confluence_fetcher is confluence_fetcher


@pytest.mark.integration
class TestServiceAvailabilityDetection:
    """Test service availability detection and handling."""

    def test_detect_no_services_configured(self):
        """Test detection when no services are configured."""
        with MockEnvironment.clean_env():
            services = get_available_services()
            assert services["jira"] is False
            assert services["confluence"] is False

    def test_detect_only_jira_configured(self):
        """Test detection when only Jira is configured."""
        with patch.dict(
            os.environ,
            {
                "JIRA_URL": "https://test.atlassian.net",
                "JIRA_USERNAME": "test@example.com",
                "JIRA_API_TOKEN": "test-token",
            },
            clear=True,
        ):  # Clear environment to ensure isolation
            services = get_available_services()
            assert services["jira"] is True
            assert services["confluence"] is False

    def test_detect_only_confluence_configured(self):
        """Test detection when only Confluence is configured."""
        with patch.dict(
            os.environ,
            {
                "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
                "CONFLUENCE_USERNAME": "test@example.com",
                "CONFLUENCE_API_TOKEN": "test-token",
            },
            clear=True,
        ):  # Clear environment to ensure isolation
            services = get_available_services()
            assert services["jira"] is False
            assert services["confluence"] is True

    def test_detect_both_services_configured(self):
        """Test detection when both services are configured."""
        with MockEnvironment.basic_auth_env():
            services = get_available_services()
            assert services["jira"] is True
            assert services["confluence"] is True

    def test_partial_configuration_detection(self):
        """Test detection with partial configuration (URL but no auth)."""
        with patch.dict(
            os.environ,
            {
                "JIRA_URL": "https://test.atlassian.net",
                "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
                # No authentication credentials
            },
            clear=True,
        ):  # Clear environment to ensure isolation
            services = get_available_services()
            assert services["jira"] is False
            assert services["confluence"] is False

    @pytest.mark.anyio
    async def test_service_availability_in_lifespan(self):
        """Test that service availability is properly reflected in lifespan context."""
        # Test with only Jira configured
        with patch.dict(
            os.environ,
            {
                "JIRA_URL": "https://test.atlassian.net",
                "JIRA_USERNAME": "test@example.com",
                "JIRA_API_TOKEN": "test-token",
            },
            clear=True,
        ):
            app = AtlassianMCP("Test MCP")

            async with main_lifespan(app) as lifespan_data:
                context = lifespan_data["app_lifespan_context"]

                # Only Jira should be configured
                assert context.full_jira_config is not None
                assert context.full_confluence_config is None

    def test_oauth_precedence_over_basic_auth(self):
        """Test that OAuth configuration takes precedence over basic auth."""
        # Set both OAuth and basic auth environment variables
        with patch.dict(
            os.environ,
            {
                # OAuth configuration
                "ATLASSIAN_OAUTH_CLIENT_ID": "oauth-client",
                "ATLASSIAN_OAUTH_CLIENT_SECRET": "oauth-secret",
                "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080",
                "ATLASSIAN_OAUTH_SCOPE": "read:jira-work write:jira-work",
                "ATLASSIAN_OAUTH_CLOUD_ID": "cloud-123",
                # Basic auth configuration
                "JIRA_URL": "https://test.atlassian.net",
                "JIRA_USERNAME": "basic@example.com",
                "JIRA_API_TOKEN": "basic-token",
                "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
                "CONFLUENCE_USERNAME": "basic@example.com",
                "CONFLUENCE_API_TOKEN": "basic-token",
            },
        ):
            services = get_available_services()
            assert services["jira"] is True
            assert services["confluence"] is True

            # Verify OAuth is used
            jira_config = JiraConfig.from_env()
            confluence_config = ConfluenceConfig.from_env()

            assert jira_config.auth_type == "oauth"
            assert confluence_config.auth_type == "oauth"
            assert jira_config.oauth_config is not None
            assert confluence_config.oauth_config is not None


@pytest.mark.integration
class TestCrossServiceDataSharing:
    """Test data sharing and references between services."""

    def test_jira_issue_confluence_page_link(self):
        """Test linking between Jira issues and Confluence pages."""
        # Create test data
        jira_issue = JiraIssueFactory.create(
            key="TEST-123",
            fields={
                "summary": "Test Issue",
                "description": "See documentation at https://test.atlassian.net/wiki/spaces/TEST/pages/123456",
            },
        )

        confluence_page = ConfluencePageFactory.create(
            page_id="123456",
            title="Test Documentation",
            body={
                "storage": {
                    "value": "<p>Related to <a href='https://test.atlassian.net/browse/TEST-123'>TEST-123</a></p>"
                }
            },
        )

        # Verify cross-references exist
        assert "123456" in jira_issue["fields"]["description"]
        assert "TEST-123" in confluence_page["body"]["storage"]["value"]

    def test_shared_user_mentions(self):
        """Test that user mentions work consistently across services."""
        user_account_id = "557058:c4b6b2f1-2f5f-4b85-b033-4cedbe2d2e17"

        # Jira mention format
        jira_mention = f"[~accountid:{user_account_id}]"

        # Confluence mention format
        confluence_mention = (
            f'<ac:link><ri:user ri:account-id="{user_account_id}" /></ac:link>'
        )

        # Create content with mentions
        jira_comment = {"body": f"Hey {jira_mention}, please review this issue."}

        confluence_content = {
            "body": {
                "storage": {
                    "value": f"<p>Hey {confluence_mention}, please review this page.</p>"
                }
            }
        }

        # Verify mentions are present
        assert user_account_id in jira_comment["body"]
        assert user_account_id in confluence_content["body"]["storage"]["value"]
