"""Tests for the AIOConfig class."""

import os
from unittest.mock import patch

import pytest

from mcp_atlassian.aio.config import AIOConfig, is_aio_enabled
from mcp_atlassian.aio.constants import AIO_CLOUD_API_BASE


class TestAIOConfigFromEnv:
    """Tests for AIOConfig.from_env."""

    def test_cloud_token_without_jira_url(self):
        """An AIO token alone is enough to reach AIO Tests Cloud."""
        with patch.dict(os.environ, {"AIO_API_TOKEN": "tok"}, clear=True):
            config = AIOConfig.from_env()

        assert config.url == AIO_CLOUD_API_BASE
        assert config.auth_type == "token"
        assert config.api_token == "tok"
        assert config.is_cloud is True
        assert config.is_auth_configured() is True

    def test_cloud_jira_url_uses_cloud_api_base(self):
        """A Jira Cloud URL still routes to the AIO Tests Cloud API host."""
        env = {
            "JIRA_URL": "https://example.atlassian.net",
            "AIO_API_TOKEN": "tok",
        }
        with patch.dict(os.environ, env, clear=True):
            config = AIOConfig.from_env()

        assert config.url == AIO_CLOUD_API_BASE
        assert config.is_cloud is True

    def test_cloud_without_token_raises(self):
        """AIO Tests Cloud cannot authenticate with Jira credentials."""
        env = {
            "JIRA_URL": "https://example.atlassian.net",
            "JIRA_USERNAME": "user@example.com",
            "JIRA_API_TOKEN": "jira-token",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="requires an access token"):
                AIOConfig.from_env()

    def test_server_derives_url_and_reuses_jira_pat(self):
        """Server/DC serves the AIO API from Jira and reuses its PAT."""
        env = {
            "JIRA_URL": "https://jira.internal.example.com",
            "JIRA_PERSONAL_TOKEN": "pat-token",
        }
        with patch.dict(os.environ, env, clear=True):
            config = AIOConfig.from_env()

        assert config.url == ("https://jira.internal.example.com/rest/aio-tcms-api/1.0")
        assert config.auth_type == "pat"
        assert config.personal_token == "pat-token"
        assert config.is_cloud is False

    def test_server_basic_auth(self):
        """Server/DC falls back to basic auth when no PAT is configured."""
        env = {
            "JIRA_URL": "https://jira.internal.example.com",
            "JIRA_USERNAME": "user",
            "JIRA_API_TOKEN": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            config = AIOConfig.from_env()

        assert config.auth_type == "basic"
        assert config.username == "user"
        assert config.password == "secret"
        assert config.is_auth_configured() is True

    def test_server_without_credentials_raises(self):
        """A Server/DC URL without credentials is an error."""
        with patch.dict(
            os.environ, {"JIRA_URL": "https://jira.internal.example.com"}, clear=True
        ):
            with pytest.raises(ValueError, match="Server/Data Center authentication"):
                AIOConfig.from_env()

    def test_missing_url_raises(self):
        """Without any URL hint the configuration cannot be built."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Cannot determine the AIO Tests"):
                AIOConfig.from_env()

    def test_explicit_url_overrides_and_strips_slash(self):
        """AIO_URL wins over the derived URL and loses its trailing slash."""
        env = {
            "AIO_URL": "https://aio.internal.example.com/api/v1/",
            "AIO_PERSONAL_TOKEN": "pat",
            "JIRA_URL": "https://example.atlassian.net",
        }
        with patch.dict(os.environ, env, clear=True):
            config = AIOConfig.from_env()

        assert config.url == "https://aio.internal.example.com/api/v1"
        assert config.auth_type == "pat"
        assert config.is_cloud is False

    def test_aio_credentials_take_precedence_over_jira(self):
        """AIO-specific credentials win over the Jira fallbacks."""
        env = {
            "JIRA_URL": "https://jira.internal.example.com",
            "JIRA_PERSONAL_TOKEN": "jira-pat",
            "AIO_PERSONAL_TOKEN": "aio-pat",
        }
        with patch.dict(os.environ, env, clear=True):
            config = AIOConfig.from_env()

        assert config.personal_token == "aio-pat"

    def test_proxy_and_ssl_settings(self):
        """Proxy and SSL settings are read from the environment."""
        env = {
            "AIO_API_TOKEN": "tok",
            "AIO_SSL_VERIFY": "false",
            "AIO_HTTP_PROXY": "http://proxy:8080",
            "AIO_CUSTOM_HEADERS": "X-Trace=1,X-Env=test",
        }
        with patch.dict(os.environ, env, clear=True):
            config = AIOConfig.from_env()

        assert config.ssl_verify is False
        assert config.http_proxy == "http://proxy:8080"
        assert config.custom_headers == {"X-Trace": "1", "X-Env": "test"}


class TestAIOConfigAuth:
    """Tests for AIOConfig.is_auth_configured."""

    @pytest.mark.parametrize(
        "kwargs,expected",
        [
            ({"auth_type": "token", "api_token": "t"}, True),
            ({"auth_type": "token"}, False),
            ({"auth_type": "pat", "personal_token": "t"}, True),
            ({"auth_type": "pat"}, False),
            ({"auth_type": "basic", "username": "u", "password": "p"}, True),
            ({"auth_type": "basic", "username": "u"}, False),
        ],
    )
    def test_is_auth_configured(self, kwargs, expected):
        """Each auth type requires its own credentials."""
        config = AIOConfig(url="https://example.com", **kwargs)
        assert config.is_auth_configured() is expected

    def test_unknown_auth_type_is_not_configured(self):
        """An unexpected auth type is reported as unconfigured."""
        config = AIOConfig(url="https://example.com", auth_type="basic")
        config.auth_type = "unknown"  # type: ignore[assignment]
        assert config.is_auth_configured() is False


class TestIsAIOEnabled:
    """Tests for the is_aio_enabled opt-in helper."""

    def test_token_enables_implicitly(self):
        """A Cloud token is itself the opt-in."""
        with patch.dict(os.environ, {"AIO_API_TOKEN": "tok"}, clear=True):
            assert is_aio_enabled() is True

    def test_jira_alone_does_not_enable(self):
        """A Jira deployment without the app must not expose AIO tools."""
        env = {
            "JIRA_URL": "https://jira.internal.example.com",
            "JIRA_PERSONAL_TOKEN": "pat",
        }
        with patch.dict(os.environ, env, clear=True):
            assert is_aio_enabled() is False

    def test_explicit_flag_enables_server(self):
        """AIO_ENABLED opts a Server/DC deployment in."""
        env = {
            "JIRA_URL": "https://jira.internal.example.com",
            "JIRA_PERSONAL_TOKEN": "pat",
            "AIO_ENABLED": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            assert is_aio_enabled() is True

    def test_flag_without_url_does_not_enable(self):
        """The flag alone is not enough without a URL to call."""
        with patch.dict(os.environ, {"AIO_ENABLED": "true"}, clear=True):
            assert is_aio_enabled() is False
