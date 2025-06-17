import inspect
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

import requests
from fastmcp import Context
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

logger = logging.getLogger(__name__)


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
        # Use bind (not bind_partial) to ensure all arguments are mapped by name
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

        processed_arguments = bound_args.arguments.copy()

        for param_name, param_obj in sig.parameters.items():
            actual_value = processed_arguments.get(param_name)

            # String: convert empty string to None if default is ""
            if (
                param_obj.annotation is str
                and param_obj.default == ""
                and actual_value == ""
            ):
                processed_arguments[param_name] = None
            # Dict: convert empty dict to None if default is {} or default_factory=dict
            elif (
                isinstance(param_obj.default, dict)
                and not param_obj.default
                and isinstance(actual_value, dict)
                and not actual_value
            ):
                processed_arguments[param_name] = None
            elif (
                (
                    hasattr(param_obj.annotation, "__origin__")
                    and param_obj.annotation.__origin__ is dict
                )
                and param_obj.default == inspect.Parameter.empty
                and isinstance(actual_value, dict)
                and not actual_value
            ):
                processed_arguments[param_name] = None
            # List: convert empty list to None if default is [] or default_factory=list
            elif (
                isinstance(param_obj.default, list)
                and not param_obj.default
                and isinstance(actual_value, list)
                and not actual_value
            ):
                processed_arguments[param_name] = None
            elif (
                (
                    hasattr(param_obj.annotation, "__origin__")
                    and param_obj.annotation.__origin__ is list
                )
                and param_obj.default == inspect.Parameter.empty
                and isinstance(actual_value, list)
                and not actual_value
            ):
                processed_arguments[param_name] = None
            # else: leave as is

        # Reconstruct args and kwargs for calling the next function
        final_call_args = list(bound_args.args)
        final_call_kwargs = bound_args.kwargs.copy()

        idx = 0
        for param_name, param_obj in sig.parameters.items():
            if (
                param_obj.kind == inspect.Parameter.POSITIONAL_ONLY
                or param_obj.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
            ):
                if idx < len(final_call_args):
                    final_call_args[idx] = processed_arguments[param_name]
                    idx += 1
                elif param_name in final_call_kwargs:
                    final_call_kwargs[param_name] = processed_arguments[param_name]
            elif param_obj.kind == inspect.Parameter.KEYWORD_ONLY:
                if param_name in final_call_kwargs:
                    final_call_kwargs[param_name] = processed_arguments[param_name]
            elif param_obj.kind == inspect.Parameter.VAR_KEYWORD:
                if param_name in processed_arguments:
                    final_call_kwargs.update(processed_arguments[param_name])

        return await func(*final_call_args, **final_call_kwargs)

    return wrapper


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def check_write_access(func: F) -> F:
    """
    Decorator for FastMCP tools to check if the application is in read-only mode.
    If in read-only mode, it raises a ValueError.
    Assumes the decorated function is async and has `ctx: Context` as its first argument.
    """

    @wraps(func)
    async def wrapper(ctx: Context, *args: Any, **kwargs: Any) -> Any:
        lifespan_ctx_dict = ctx.request_context.lifespan_context
        app_lifespan_ctx = (
            lifespan_ctx_dict.get("app_lifespan_context")
            if isinstance(lifespan_ctx_dict, dict)
            else None
        )  # type: ignore

        if app_lifespan_ctx is not None and app_lifespan_ctx.read_only:
            tool_name = func.__name__
            action_description = tool_name.replace(
                "_", " "
            )  # e.g., "create_issue" -> "create issue"
            logger.warning(f"Attempted to call tool '{tool_name}' in read-only mode.")
            raise ValueError(f"Cannot {action_description} in read-only mode.")

        return await func(ctx, *args, **kwargs)

    return wrapper  # type: ignore


def handle_atlassian_api_errors(service_name: str = "Atlassian API") -> Callable:
    """
    Decorator to handle common Atlassian API exceptions (Jira, Confluence, etc.).

    Args:
        service_name: Name of the service for error logging (e.g., "Jira API").
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return func(self, *args, **kwargs)
            except HTTPError as http_err:
                if http_err.response is not None and http_err.response.status_code in [
                    401,
                    403,
                ]:
                    error_msg = (
                        f"Authentication failed for {service_name} "
                        f"({http_err.response.status_code}). "
                        "Token may be expired or invalid. Please verify credentials."
                    )
                    logger.error(error_msg)
                    raise MCPAtlassianAuthenticationError(error_msg) from http_err
                else:
                    operation_name = getattr(func, "__name__", "API operation")
                    logger.error(
                        f"HTTP error during {operation_name}: {http_err}",
                        exc_info=False,
                    )
                    raise http_err
            except KeyError as e:
                operation_name = getattr(func, "__name__", "API operation")
                logger.error(f"Missing key in {operation_name} results: {str(e)}")
                return []
            except requests.RequestException as e:
                operation_name = getattr(func, "__name__", "API operation")
                logger.error(f"Network error during {operation_name}: {str(e)}")
                return []
            except (ValueError, TypeError) as e:
                operation_name = getattr(func, "__name__", "API operation")
                logger.error(f"Error processing {operation_name} results: {str(e)}")
                return []
            except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
                operation_name = getattr(func, "__name__", "API operation")
                logger.error(f"Unexpected error during {operation_name}: {str(e)}")
                logger.debug(
                    f"Full exception details for {operation_name}:", exc_info=True
                )
                return []

        return wrapper

    return decorator
