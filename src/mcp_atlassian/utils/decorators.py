import functools
import inspect
import logging
from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar, cast

from fastmcp import Context
from fastmcp.server.dependencies import get_http_request
from starlette.requests import Request

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.servers.context import MainAppContext

logger = logging.getLogger(__name__)

ConfigType = TypeVar("ConfigType", JiraConfig, ConfluenceConfig)


# TODO: [CursorIDE Compatibility] Remove this decorator and revert parameter signatures
# in tool definitions (str -> str | None, default="" -> default=None, etc.)
# once Cursor IDE properly handle optional parameters with Union types
# and None defaults without sending them as empty strings/dicts.
# Refs: https://github.com/jlowin/fastmcp/issues/224
def convert_empty_defaults_to_none(func: Callable) -> Callable:
    """
    Decorator to convert empty string, dict, or list default values to None for function parameters.

    This is a workaround for environments (like some IDEs) that send empty strings, dicts, or lists
    instead of None for optional parameters. It ensures that downstream logic receives None
    instead of empty values when appropriate.

    Args:
        func: The function to wrap.

    Returns:
        The wrapped function with empty defaults converted to None.
    """
    sig = inspect.signature(func)

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Awaitable[Any]:
        bound_args = sig.bind_partial(*args, **kwargs)
        bound_args.apply_defaults()

        processed_kwargs = {}
        # Gather all arguments, including positional ones, as kwargs
        all_passed_args = bound_args.arguments.copy()

        for name, param_obj in sig.parameters.items():
            actual_value = all_passed_args.get(
                name
            )  # The actual value passed (after applying defaults)

            # String handling: If param.default is "" and the actual value passed is also "", convert to None
            if (
                param_obj.annotation is str
                and param_obj.default == ""
                and actual_value == ""
            ):
                processed_kwargs[name] = None
            # Dictionary handling:
            #   - Type hint is dict (or Dict, Dict[str, Any], etc.)
            #   - The function definition's default is an empty dict {}
            #   - If Pydantic Field's default_factory is dict (hard to detect directly with inspect)
            #   - And the actual value passed is an empty dict {}, convert to None
            elif (
                (
                    isinstance(param_obj.annotation, type)
                    and issubclass(param_obj.annotation, dict)
                )
                or (
                    hasattr(param_obj.annotation, "__origin__")
                    and param_obj.annotation.__origin__ in (dict, dict)
                )
                and param_obj.default == inspect.Parameter.empty
                and isinstance(actual_value, dict)
                and not actual_value
            ):  # If the actual value is an empty dict
                # When using Pydantic Field(default_factory=dict),
                # the function signature's param.default is inspect.Parameter.empty.
                # Therefore, it's important to check if the actual value passed is an empty dict.
                processed_kwargs[name] = None
            elif (
                isinstance(param_obj.default, dict)
                and not param_obj.default
                and isinstance(actual_value, dict)
                and not actual_value
            ):
                processed_kwargs[name] = None
            # List handling (Pydantic Field(default_factory=list) or default=[]):
            elif (
                (
                    (
                        isinstance(param_obj.annotation, type)
                        and issubclass(param_obj.annotation, list)
                    )
                    or (
                        hasattr(param_obj.annotation, "__origin__")
                        and param_obj.annotation.__origin__ in (list, list)
                    )
                )
                and param_obj.default == inspect.Parameter.empty
                and isinstance(actual_value, list)
                and not actual_value
            ):
                processed_kwargs[name] = None
            elif (
                isinstance(param_obj.default, list)
                and not param_obj.default
                and isinstance(actual_value, list)
                and not actual_value
            ):
                processed_kwargs[name] = None
            else:
                processed_kwargs[name] = actual_value

        return await func(**processed_kwargs)

    return wrapper


def _create_user_specific_config(
    base_config: ConfigType,
    user_token: str,
    user_email: str | None,
) -> ConfigType:
    """Create a user-specific config for Jira or Confluence based on the base config and user credentials."""
    if base_config is None:
        raise ValueError("Base configuration cannot be None.")

    updated_data: dict[str, Any] = {"oauth_config": None}

    if base_config.is_cloud:
        updated_data.update(
            {
                "auth_type": "basic",
                "username": user_email,
                "api_token": user_token,
                "personal_token": cast(str | None, None),
            }
        )
    else:
        updated_data.update(
            {
                "auth_type": "token",
                "username": cast(str | None, None),
                "api_token": cast(str | None, None),
                "personal_token": user_token,
            }
        )

    if hasattr(base_config, "model_copy"):
        return base_config.model_copy(update=updated_data)
    else:
        raise TypeError(f"Unsupported base_config type: {type(base_config)}")


def with_jira_fetcher(
    func: Callable[..., Coroutine[Any, Any, str]],
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Decorator to inject a user-specific JiraFetcher into a tool function.

    The decorated function must accept a 'jira' parameter of type JiraFetcher.

    Args:
        func: The tool function to decorate.

    Returns:
        The decorated function with JiraFetcher injection.

    Raises:
        ValueError: If user token or base config is missing.
    """

    @functools.wraps(func)
    async def wrapper(ctx: Context, *args: Any, **kwargs: Any) -> str:
        request: Request = get_http_request()
        user_token = getattr(request.state, "user_atlassian_token", None)
        user_email = getattr(request.state, "user_atlassian_email", None)

        if not user_token:
            logger.error(f"Jira tool ({func.__name__}) missing user token.")
            raise ValueError("Missing Atlassian authentication token.")

        lifespan_ctx: MainAppContext = cast(
            MainAppContext, ctx.request_context.lifespan_context
        )
        base_config: JiraConfig | None = lifespan_ctx.jira_base_config
        if not base_config:
            raise ValueError("Jira base configuration is not available.")

        user_config = _create_user_specific_config(base_config, user_token, user_email)
        jira_fetcher = JiraFetcher(config=user_config)
        kwargs["jira"] = jira_fetcher
        return await func(ctx, *args, **kwargs)

    return wrapper


def with_confluence_fetcher(
    func: Callable[..., Coroutine[Any, Any, str]],
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Decorator to inject a user-specific ConfluenceFetcher into a tool function.

    The decorated function must accept a 'confluence' parameter of type ConfluenceFetcher.

    Args:
        func: The tool function to decorate.

    Returns:
        The decorated function with ConfluenceFetcher injection.

    Raises:
        ValueError: If user token or base config is missing.
    """

    @functools.wraps(func)
    async def wrapper(ctx: Context, *args: Any, **kwargs: Any) -> str:
        request: Request = get_http_request()
        user_token = getattr(request.state, "user_atlassian_token", None)
        user_email = getattr(request.state, "user_atlassian_email", None)

        if not user_token:
            logger.error(f"Confluence tool ({func.__name__}) missing user token.")
            raise ValueError("Missing Atlassian authentication token.")

        lifespan_ctx: MainAppContext = cast(
            MainAppContext, ctx.request_context.lifespan_context
        )
        base_config: ConfluenceConfig | None = lifespan_ctx.confluence_base_config
        if not base_config:
            raise ValueError("Confluence base configuration is not available.")

        user_config = _create_user_specific_config(base_config, user_token, user_email)
        confluence_fetcher = ConfluenceFetcher(config=user_config)
        kwargs["confluence"] = confluence_fetcher
        return await func(ctx, *args, **kwargs)

    return wrapper
