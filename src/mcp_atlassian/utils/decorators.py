import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any


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
            ):  # If default={} is specified in the function signature
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
