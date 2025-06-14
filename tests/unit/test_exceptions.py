"""
Tests for the exceptions module.
"""

import pickle

import pytest

from src.mcp_atlassian.exceptions import MCPAtlassianAuthenticationError


class TestMCPAtlassianAuthenticationError:
    """Tests for the MCPAtlassianAuthenticationError exception class."""

    def test_instantiation_without_message(self):
        """Test creating exception without a message."""
        error = MCPAtlassianAuthenticationError()

        assert isinstance(error, MCPAtlassianAuthenticationError)
        assert isinstance(error, Exception)
        assert str(error) == ""
        assert error.args == ()

    def test_instantiation_with_message(self):
        """Test creating exception with a message."""
        message = "Authentication failed"
        error = MCPAtlassianAuthenticationError(message)

        assert isinstance(error, MCPAtlassianAuthenticationError)
        assert isinstance(error, Exception)
        assert str(error) == message
        assert error.args == (message,)

    def test_instantiation_with_multiple_args(self):
        """Test creating exception with multiple arguments."""
        message = "Authentication failed"
        code = 401
        error = MCPAtlassianAuthenticationError(message, code)

        assert isinstance(error, MCPAtlassianAuthenticationError)
        assert isinstance(error, Exception)
        # When multiple args are present, str() returns tuple representation
        assert str(error) == "('Authentication failed', 401)"
        assert error.args == (message, code)

    def test_inheritance_hierarchy(self):
        """Test that the exception properly inherits from Exception."""
        error = MCPAtlassianAuthenticationError("test")

        assert isinstance(error, MCPAtlassianAuthenticationError)
        assert isinstance(error, Exception)
        assert isinstance(error, BaseException)
        assert issubclass(MCPAtlassianAuthenticationError, Exception)
        assert issubclass(MCPAtlassianAuthenticationError, BaseException)

    def test_string_representation(self):
        """Test string representation of the exception."""
        # Empty message
        error = MCPAtlassianAuthenticationError()
        assert str(error) == ""
        assert repr(error) == "MCPAtlassianAuthenticationError()"

        # With message
        message = "Invalid credentials provided"
        error = MCPAtlassianAuthenticationError(message)
        assert str(error) == message
        assert repr(error) == f"MCPAtlassianAuthenticationError('{message}')"

        # With multiple args
        error = MCPAtlassianAuthenticationError("Auth failed", 403)
        assert str(error) == "('Auth failed', 403)"
        assert repr(error) == "MCPAtlassianAuthenticationError('Auth failed', 403)"

    def test_exception_raising_and_catching(self):
        """Test raising and catching the exception."""
        message = "401 Unauthorized"

        with pytest.raises(MCPAtlassianAuthenticationError) as exc_info:
            raise MCPAtlassianAuthenticationError(message)

        assert str(exc_info.value) == message
        assert exc_info.value.args == (message,)

    def test_exception_catching_as_base_exception(self):
        """Test that the exception can be caught as base Exception."""
        message = "403 Forbidden"

        with pytest.raises(Exception) as exc_info:
            raise MCPAtlassianAuthenticationError(message)

        assert isinstance(exc_info.value, MCPAtlassianAuthenticationError)
        assert str(exc_info.value) == message

    def test_exception_chaining_with_cause(self):
        """Test exception chaining using 'raise from' syntax."""
        original_error = ValueError("Invalid token format")
        auth_message = "Authentication failed due to invalid token"

        with pytest.raises(MCPAtlassianAuthenticationError) as exc_info:
            try:
                raise original_error
            except ValueError as e:
                raise MCPAtlassianAuthenticationError(auth_message) from e

        assert str(exc_info.value) == auth_message
        assert exc_info.value.__cause__ is original_error
        # Context is still preserved even with explicit 'raise from'
        assert exc_info.value.__context__ is original_error

    def test_exception_chaining_with_context(self):
        """Test implicit exception chaining (context preservation)."""
        original_error = ConnectionError("Network timeout")
        auth_message = "Authentication failed"

        with pytest.raises(MCPAtlassianAuthenticationError) as exc_info:
            try:
                raise original_error
            except ConnectionError:
                raise MCPAtlassianAuthenticationError(auth_message) from None

        assert str(exc_info.value) == auth_message
        assert exc_info.value.__context__ is original_error
        assert exc_info.value.__cause__ is None

    def test_exception_suppressed_context(self):
        """Test exception with suppressed context."""
        original_error = RuntimeError("Some runtime error")
        auth_message = "Authentication failed"

        with pytest.raises(MCPAtlassianAuthenticationError) as exc_info:
            try:
                raise original_error
            except RuntimeError:
                error = MCPAtlassianAuthenticationError(auth_message)
                error.__suppress_context__ = True
                raise error from None

        assert str(exc_info.value) == auth_message
        assert exc_info.value.__suppress_context__ is True

    def test_serialization_with_pickle(self):
        """Test that the exception can be pickled and unpickled."""
        message = "Authentication error for serialization test"
        original_error = MCPAtlassianAuthenticationError(message)

        # Serialize
        pickled_data = pickle.dumps(original_error)

        # Deserialize
        unpickled_error = pickle.loads(pickled_data)

        assert isinstance(unpickled_error, MCPAtlassianAuthenticationError)
        assert str(unpickled_error) == message
        assert unpickled_error.args == original_error.args

    def test_exception_attributes_access(self):
        """Test accessing exception attributes."""
        message = "Test message"
        error = MCPAtlassianAuthenticationError(message)

        # Test standard exception attributes
        assert hasattr(error, "args")
        assert hasattr(error, "__traceback__")
        assert hasattr(error, "__cause__")
        assert hasattr(error, "__context__")
        assert hasattr(error, "__suppress_context__")

        # Test docstring access
        expected_doc = "Raised when Atlassian API authentication fails (401/403)."
        assert error.__doc__ == expected_doc

    def test_exception_equality(self):
        """Test exception equality comparison."""
        message = "Same message"
        error1 = MCPAtlassianAuthenticationError(message)
        error2 = MCPAtlassianAuthenticationError(message)
        error3 = MCPAtlassianAuthenticationError("Different message")

        # Exceptions with same args should have same args but different identity
        assert error1.args == error2.args
        assert error1 is not error2
        assert error1.args != error3.args

    def test_realistic_authentication_scenarios(self):
        """Test realistic authentication error scenarios."""
        # 401 Unauthorized
        msg_401 = "401 Unauthorized: Invalid API token"
        error_401 = MCPAtlassianAuthenticationError(msg_401)
        assert "401" in str(error_401)
        assert "Invalid API token" in str(error_401)

        # 403 Forbidden
        msg_403 = "403 Forbidden: Insufficient permissions"
        error_403 = MCPAtlassianAuthenticationError(msg_403)
        assert "403" in str(error_403)
        assert "Insufficient permissions" in str(error_403)

        # OAuth token expired
        oauth_error = MCPAtlassianAuthenticationError("OAuth token has expired")
        assert "OAuth" in str(oauth_error)
        assert "expired" in str(oauth_error)
