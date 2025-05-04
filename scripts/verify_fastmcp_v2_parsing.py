# scripts/verify_fastmcp_v2_parsing.py
import asyncio
import json
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

import fastmcp
from fastmcp import Client, FastMCP

# --- Helper Functions ---

def ensure_dict_from_json(v: Any) -> dict[str, Any]:
    """Pydantic BeforeValidator to ensure input is parsed from JSON string to dict."""
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            if isinstance(parsed, dict):
                print(f"Validator: Successfully parsed JSON string to dict: {parsed}")
                return parsed
            else:
                # Parsed but not a dict, raise error to use original string
                raise ValueError("Parsed JSON is not a dictionary")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Validator: Failed to parse as JSON dict ({e}), keeping original string: '{v}'")
            raise ValueError("Input is not a valid JSON dictionary string") from e # Raise to keep original
    elif isinstance(v, dict):
        print(f"Validator: Input is already a dict: {v}")
        return v # Already a dict, pass through
    else:
         raise ValueError(f"Input must be a dict or a valid JSON string representing a dict, got {type(v)}")


# --- Pydantic Models for Testing ---

class SimpleData(BaseModel):
    key: str
    value: int

# --- FastMCP Server Setup ---

mcp = FastMCP("ParsingTestServer")

# --- Tool Definitions ---

@mcp.tool()
def process_raw_string(data_str: str) -> dict:
    """Accepts a raw string, attempts manual JSON parsing inside."""
    print(f"\n--- Testing: process_raw_string ---")
    print(f"Received data_str type: {type(data_str)}")
    print(f"Received data_str value: {data_str!r}")
    try:
        parsed = json.loads(data_str)
        print("Manual parsing inside tool successful.")
        return {"input_type": str(type(data_str)), "parsed": True, "value": parsed}
    except json.JSONDecodeError:
        print("Manual parsing inside tool failed.")
        return {"input_type": str(type(data_str)), "parsed": False, "value": data_str}

@mcp.tool()
def process_dict_direct(data_dict: dict) -> dict:
    """Accepts a dictionary directly."""
    print(f"\n--- Testing: process_dict_direct ---")
    print(f"Received data_dict type: {type(data_dict)}")
    print(f"Received data_dict value: {data_dict!r}")
    return {"input_type": str(type(data_dict)), "value": data_dict}

@mcp.tool()
def process_pydantic_model(data_model: SimpleData) -> dict:
    """Accepts a Pydantic model."""
    print(f"\n--- Testing: process_pydantic_model ---")
    print(f"Received data_model type: {type(data_model)}")
    print(f"Received data_model value: {data_model!r}")
    return {"input_type": str(type(data_model)), "value": data_model.model_dump()}

# --- Tool using Annotated with BeforeValidator ---
# This is the key test for automatic JSON string parsing prevention/handling

JsonDict = Annotated[dict, BeforeValidator(ensure_dict_from_json)]

@mcp.tool()
def process_validated_dict(
    # data: JsonDict # Using the type alias
    data: Annotated[dict, BeforeValidator(ensure_dict_from_json)]
) -> dict:
    """
    Accepts a dictionary, potentially parsed from a JSON string
    by the BeforeValidator.
    """
    print(f"\n--- Testing: process_validated_dict ---")
    print(f"Received data type after validation: {type(data)}")
    print(f"Received data value after validation: {data!r}")
    # The validator ensures `data` is always a dict here if validation passes
    return {"input_type_after_validation": str(type(data)), "value": data}


@mcp.tool()
def process_list_direct(data_list: list[int]) -> dict:
    """Accepts a list of integers directly."""
    print(f"\n--- Testing: process_list_direct ---")
    print(f"Received data_list type: {type(data_list)}")
    print(f"Received data_list value: {data_list!r}")
    return {"input_type": str(type(data_list)), "value": data_list}


@mcp.tool()
def process_annotated_list(
    data_list: Annotated[list[int], Field(description="A list of integers")]
) -> dict:
    """Accepts a list of integers using Annotated."""
    print(f"\n--- Testing: process_annotated_list ---")
    print(f"Received data_list type: {type(data_list)}")
    print(f"Received data_list value: {data_list!r}")
    return {"input_type": str(type(data_list)), "value": data_list}

# --- Test Execution Logic ---

async def run_tests():
    """Runs the parsing tests using an in-memory client."""
    async with Client(mcp) as client:
        print("="*20 + " Testing JSON String Input " + "="*20)
        json_string_input = '{"key": "string_test", "value": 123}'
        print(f"Input: {json_string_input!r} (type: {type(json_string_input)})")

        # 1. Raw String Argument
        try:
            result_raw = await client.call_tool("process_raw_string", {"data_str": json_string_input})
            print(f"Result (process_raw_string): {result_raw[0].text}")
        except Exception as e:
            print(f"Error (process_raw_string): {e}")

        # 2. Dict Argument (FastMCP might auto-parse JSON string here)
        try:
            result_dict = await client.call_tool("process_dict_direct", {"data_dict": json_string_input})
            print(f"Result (process_dict_direct): {result_dict[0].text}")
        except Exception as e:
            print(f"Error (process_dict_direct): {e}") # Expecting potential error if auto-parsing fails

        # 3. Pydantic Model Argument (FastMCP might auto-parse JSON string here)
        try:
            result_model = await client.call_tool("process_pydantic_model", {"data_model": json_string_input})
            print(f"Result (process_pydantic_model): {result_model[0].text}")
        except Exception as e:
            print(f"Error (process_pydantic_model): {e}") # Expecting potential error if auto-parsing fails

        # 4. Annotated Dict with Validator
        try:
            result_validated = await client.call_tool("process_validated_dict", {"data": json_string_input})
            print(f"Result (process_validated_dict): {result_validated[0].text}")
        except Exception as e:
            print(f"Error (process_validated_dict): {e}") # Should succeed if validator works

        print("\n" + "="*20 + " Testing Dictionary Input " + "="*20)
        dict_input = {"key": "dict_test", "value": 456}
        print(f"Input: {dict_input!r} (type: {type(dict_input)})")

        # 1. Raw String Argument (Expect error or wrong type inside tool)
        try:
            result_raw_dict = await client.call_tool("process_raw_string", {"data_str": dict_input})
            print(f"Result (process_raw_string with dict): {result_raw_dict[0].text}")
        except Exception as e:
            print(f"Error (process_raw_string with dict): {e}") # Expecting error

        # 2. Dict Argument (Should succeed)
        try:
            result_dict_dict = await client.call_tool("process_dict_direct", {"data_dict": dict_input})
            print(f"Result (process_dict_direct with dict): {result_dict_dict[0].text}")
        except Exception as e:
            print(f"Error (process_dict_direct with dict): {e}")

        # 3. Pydantic Model Argument (Should succeed)
        try:
            result_model_dict = await client.call_tool("process_pydantic_model", {"data_model": dict_input})
            print(f"Result (process_pydantic_model with dict): {result_model_dict[0].text}")
        except Exception as e:
            print(f"Error (process_pydantic_model with dict): {e}")

        # 4. Annotated Dict with Validator (Should succeed)
        try:
            result_validated_dict = await client.call_tool("process_validated_dict", {"data": dict_input})
            print(f"Result (process_validated_dict with dict): {result_validated_dict[0].text}")
        except Exception as e:
            print(f"Error (process_validated_dict with dict): {e}")


        print("\n" + "="*20 + " Testing List Input " + "="*20)
        list_input_ok = [1, 2, 3]
        list_input_json_str_ok = "[1, 2, 3]"
        list_input_json_str_bad = "[1, 2, 'a']" # Type mismatch for list[int]

        # 5. List Argument (Direct Python list)
        try:
            result_list_direct = await client.call_tool("process_list_direct", {"data_list": list_input_ok})
            print(f"Result (process_list_direct with list): {result_list_direct[0].text}")
        except Exception as e:
            print(f"Error (process_list_direct with list): {e}")

        # 6. List Argument (JSON String list) - FastMCP should auto-parse
        try:
            result_list_json = await client.call_tool("process_list_direct", {"data_list": list_input_json_str_ok})
            print(f"Result (process_list_direct with JSON string): {result_list_json[0].text}")
        except Exception as e:
            print(f"Error (process_list_direct with JSON string): {e}")

        # 7. List Argument (Bad JSON String list) - Expect validation error
        try:
            result_list_json_bad = await client.call_tool("process_list_direct", {"data_list": list_input_json_str_bad})
            print(f"Result (process_list_direct with bad JSON string): {result_list_json_bad[0].text}")
        except Exception as e:
            print(f"Error (process_list_direct with bad JSON string): {e}") # Expect error

        # 8. Annotated List Argument (Direct Python list)
        try:
            result_annotated_list = await client.call_tool("process_annotated_list", {"data_list": list_input_ok})
            print(f"Result (process_annotated_list with list): {result_annotated_list[0].text}")
        except Exception as e:
            print(f"Error (process_annotated_list with list): {e}")

        # 9. Annotated List Argument (JSON String list) - FastMCP should auto-parse
        try:
            result_annotated_json = await client.call_tool("process_annotated_list", {"data_list": list_input_json_str_ok})
            print(f"Result (process_annotated_list with JSON string): {result_annotated_json[0].text}")
        except Exception as e:
            print(f"Error (process_annotated_list with JSON string): {e}")


if __name__ == "__main__":
    print(f"Running FastMCP v2 ({fastmcp.__version__}) parsing verification script...") # type: ignore
    asyncio.run(run_tests())