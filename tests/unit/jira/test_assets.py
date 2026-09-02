"""Tests for Jira Assets (Insight) operations on Server/Data Center."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.assets import DEFAULT_ASSETS_API_BASE
from mcp_atlassian.jira.config import JiraConfig


@pytest.fixture
def assets_fetcher(jira_fetcher: JiraFetcher) -> JiraFetcher:
    """Create a Jira fetcher configured for Server/DC Assets testing."""
    fetcher = jira_fetcher
    fetcher.config = MagicMock()
    fetcher.config.is_cloud = False
    fetcher.config.assets_api_base = DEFAULT_ASSETS_API_BASE
    return fetcher


# ----------------------------------------------------------------------
# Cloud guard and base path
# ----------------------------------------------------------------------


def test_assets_raise_on_cloud(assets_fetcher: JiraFetcher):
    """Assets operations should refuse to run against Jira Cloud."""
    assets_fetcher.config.is_cloud = True

    with pytest.raises(NotImplementedError, match="Server/Data Center"):
        assets_fetcher.list_asset_schemas()


def test_assets_default_base_path(assets_fetcher: JiraFetcher):
    """Requests should target rest/assets/1.0 by default."""
    assets_fetcher.jira.get = MagicMock(return_value={"objectschemas": []})

    assets_fetcher.list_asset_schemas()

    called_path = assets_fetcher.jira.get.call_args[0][0]
    assert called_path == f"{DEFAULT_ASSETS_API_BASE}/objectschema/list"


def test_assets_base_path_from_config(assets_fetcher: JiraFetcher):
    """JiraConfig.assets_api_base should drive the REST base path."""
    assets_fetcher.config.assets_api_base = "rest/insight/1.0"
    assets_fetcher.jira.get = MagicMock(return_value={"objectschemas": []})

    assets_fetcher.list_asset_schemas()

    called_path = assets_fetcher.jira.get.call_args[0][0]
    assert called_path == "rest/insight/1.0/objectschema/list"


def test_assets_base_path_falls_back_when_config_lacks_field(
    assets_fetcher: JiraFetcher,
):
    """Configs built without the field (e.g. header-based) use the default."""
    del assets_fetcher.config.assets_api_base
    assets_fetcher.jira.get = MagicMock(return_value={"objectschemas": []})

    assets_fetcher.list_asset_schemas()

    called_path = assets_fetcher.jira.get.call_args[0][0]
    assert called_path == f"{DEFAULT_ASSETS_API_BASE}/objectschema/list"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, DEFAULT_ASSETS_API_BASE),
        ("", DEFAULT_ASSETS_API_BASE),
        ("/", DEFAULT_ASSETS_API_BASE),
        ("rest/insight/1.0", "rest/insight/1.0"),
        ("/rest/insight/1.0/", "rest/insight/1.0"),
        ("  rest/insight/1.0  ", "rest/insight/1.0"),
    ],
)
def test_config_reads_assets_api_base_from_env(monkeypatch, raw, expected):
    """JIRA_ASSETS_API_BASE is normalized into JiraConfig.assets_api_base."""
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    monkeypatch.setenv("JIRA_PERSONAL_TOKEN", "token")
    if raw is None:
        monkeypatch.delenv("JIRA_ASSETS_API_BASE", raising=False)
    else:
        monkeypatch.setenv("JIRA_ASSETS_API_BASE", raw)

    config = JiraConfig.from_env()

    assert config.assets_api_base == expected


# ----------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------


def test_list_asset_schemas(assets_fetcher: JiraFetcher):
    """Schema list should be flattened to simplified dicts."""
    assets_fetcher.jira.get = MagicMock(
        return_value={
            "objectschemas": [
                {
                    "id": 1,
                    "name": "Hardware",
                    "objectSchemaKey": "HW",
                    "description": "Physical assets",
                    "objectCount": 120,
                    "objectTypeCount": 4,
                },
                {"id": 2, "name": "People", "objectSchemaKey": "PPL"},
            ]
        }
    )

    result = assets_fetcher.list_asset_schemas()

    assert len(result) == 2
    assert result[0] == {
        "id": "1",
        "name": "Hardware",
        "key": "HW",
        "description": "Physical assets",
        "object_count": 120,
        "object_type_count": 4,
    }
    assert result[1]["id"] == "2"
    assert result[1]["key"] == "PPL"


def test_list_asset_schemas_unexpected_payload(assets_fetcher: JiraFetcher):
    """A non-dict payload should degrade to an empty list."""
    assets_fetcher.jira.get = MagicMock(return_value="unexpected")

    assert assets_fetcher.list_asset_schemas() == []


def test_list_asset_object_types(assets_fetcher: JiraFetcher):
    """Object types should be returned flat with parent references."""
    assets_fetcher.jira.get = MagicMock(
        return_value=[
            {"id": 10, "name": "Laptop", "parentObjectTypeId": 5, "objectCount": 40},
            {"id": 5, "name": "Device", "objectCount": 0},
        ]
    )

    result = assets_fetcher.list_asset_object_types("1")

    called_path, called_kwargs = assets_fetcher.jira.get.call_args
    assert called_path[0].endswith("objectschema/1/objecttypes/flat")
    assert called_kwargs.get("params") is None
    assert result[0]["parent_object_type_id"] == "5"
    assert result[1]["parent_object_type_id"] is None


def test_list_asset_object_types_requires_schema_id(assets_fetcher: JiraFetcher):
    """An empty schema ID should be rejected before any request is made."""
    assets_fetcher.jira.get = MagicMock()

    with pytest.raises(ValueError, match="schema_id"):
        assets_fetcher.list_asset_object_types("  ")

    assets_fetcher.jira.get.assert_not_called()


def test_get_asset_object_type_attributes(assets_fetcher: JiraFetcher):
    """Attribute definitions should expose IDs, cardinality and references."""
    assets_fetcher.jira.get = MagicMock(
        return_value=[
            {
                "id": 100,
                "name": "Name",
                "type": 0,
                "defaultType": {"name": "Text"},
                "editable": True,
                "minimumCardinality": 1,
            },
            {
                "id": 101,
                "name": "Owner",
                "type": 1,
                "editable": True,
                "minimumCardinality": 0,
                "referenceObjectType": {"id": 7, "name": "Person"},
            },
        ]
    )

    result = assets_fetcher.get_asset_object_type_attributes("10")

    assert result[0]["id"] == "100"
    assert result[0]["required"] is True
    assert result[0]["default_type"] == "Text"
    assert result[1]["required"] is False
    assert result[1]["reference_object_type_id"] == "7"
    assert result[1]["reference_object_type_name"] == "Person"


# ----------------------------------------------------------------------
# Read
# ----------------------------------------------------------------------


def test_search_assets_aql(assets_fetcher: JiraFetcher):
    """AQL search should send correct params and resolve attribute names."""
    assets_fetcher.jira.get = MagicMock(
        return_value={
            "objectEntries": [
                {
                    "id": 501,
                    "objectKey": "HW-501",
                    "label": "Laptop 501",
                    "objectType": {"id": 10, "name": "Laptop"},
                    "created": "2024-01-01T00:00:00.000Z",
                    "updated": "2024-02-01T00:00:00.000Z",
                    "attributes": [
                        {
                            "objectTypeAttributeId": 100,
                            "objectAttributeValues": [
                                {"value": "Laptop 501", "displayValue": "Laptop 501"}
                            ],
                        },
                        {
                            "objectTypeAttributeId": 101,
                            "objectAttributeValues": [
                                {
                                    "referencedObject": {
                                        "id": 42,
                                        "label": "Example User",
                                        "objectKey": "PPL-42",
                                    }
                                }
                            ],
                        },
                        {
                            "objectTypeAttributeId": 102,
                            "objectAttributeValues": [
                                {"displayValue": "Red"},
                                {"displayValue": "Blue"},
                            ],
                        },
                    ],
                }
            ],
            "objectTypeAttributes": [
                {"id": 100, "name": "Name"},
                {"id": 101, "name": "Owner"},
                {"id": 102, "name": "Tags"},
            ],
            "totalFilterCount": 1,
            "pageNumber": 2,
            "pageSize": 1,
            "pageObjectSize": 1,
        }
    )

    result = assets_fetcher.search_assets_aql(
        'objectType = "Laptop"', page=2, results_per_page=50
    )

    called_path, called_kwargs = assets_fetcher.jira.get.call_args
    assert called_path[0] == f"{DEFAULT_ASSETS_API_BASE}/aql/objects"
    assert called_kwargs["params"] == {
        "qlQuery": 'objectType = "Laptop"',
        "page": 2,
        "resultPerPage": 50,
        "includeAttributes": "true",
        "includeTypeAttributes": "true",
    }

    assert result["total"] == 1
    assert result["page"] == 2
    assert result["page_size"] == 1
    assert result["total_pages"] == 1
    obj = result["objects"][0]
    assert obj["id"] == "501"
    assert obj["object_key"] == "HW-501"
    assert obj["object_type_name"] == "Laptop"
    assert obj["attributes"]["Name"] == "Laptop 501"
    assert obj["attributes"]["Owner"] == {
        "id": "42",
        "label": "Example User",
        "object_key": "PPL-42",
    }
    assert obj["attributes"]["Tags"] == ["Red", "Blue"]


def test_search_assets_aql_legacy_insight_endpoint(assets_fetcher: JiraFetcher):
    """A rest/insight base should search via iql/objects with the iql param."""
    assets_fetcher.config.assets_api_base = "rest/insight/1.0"
    assets_fetcher.jira.get = MagicMock(return_value={"objectEntries": []})

    assets_fetcher.search_assets_aql('objectType = "Laptop"')

    called_path, called_kwargs = assets_fetcher.jira.get.call_args
    assert called_path[0] == "rest/insight/1.0/iql/objects"
    assert called_kwargs["params"]["iql"] == 'objectType = "Laptop"'
    assert "qlQuery" not in called_kwargs["params"]
    assert called_kwargs["params"]["includeTypeAttributes"] == "true"


def test_search_assets_aql_clamps_page_size(assets_fetcher: JiraFetcher):
    """Page size should be clamped to the 1-100 range."""
    assets_fetcher.jira.get = MagicMock(return_value={"objectEntries": []})

    assets_fetcher.search_assets_aql("objectType = X", page=0, results_per_page=500)

    params = assets_fetcher.jira.get.call_args[1]["params"]
    assert params["page"] == 1
    assert params["resultPerPage"] == 100


def test_search_assets_aql_requires_query(assets_fetcher: JiraFetcher):
    """An empty AQL string should be rejected."""
    with pytest.raises(ValueError, match="aql"):
        assets_fetcher.search_assets_aql("   ")


def test_get_asset_object_resolves_attribute_names(assets_fetcher: JiraFetcher):
    """Single-object reads should resolve names via the object type definition."""
    assets_fetcher.jira.get = MagicMock(
        side_effect=[
            # object/501
            {
                "id": 501,
                "objectKey": "HW-501",
                "label": "Laptop 501",
                "objectType": {"id": 10, "name": "Laptop"},
                "attributes": [
                    {
                        "objectTypeAttributeId": 100,
                        "objectAttributeValues": [{"displayValue": "Laptop 501"}],
                    }
                ],
            },
            # objecttype/10/attributes
            [{"id": 100, "name": "Name", "minimumCardinality": 1}],
        ]
    )

    result = assets_fetcher.get_asset_object("501")

    assert assets_fetcher.jira.get.call_count == 2
    assert result["id"] == "501"
    assert result["attributes"] == {"Name": "Laptop 501"}


def test_get_asset_object_uses_embedded_attribute_names(assets_fetcher: JiraFetcher):
    """When the response embeds attribute definitions no lookup is needed."""
    assets_fetcher.jira.get = MagicMock(
        return_value={
            "id": 501,
            "objectKey": "HW-501",
            "objectType": {"id": 10, "name": "Laptop"},
            "attributes": [
                {
                    "objectTypeAttributeId": 100,
                    "objectTypeAttribute": {"id": 100, "name": "Name"},
                    "objectAttributeValues": [{"displayValue": "Laptop 501"}],
                }
            ],
        }
    )

    result = assets_fetcher.get_asset_object("501")

    assert assets_fetcher.jira.get.call_count == 1
    assert result["attributes"] == {"Name": "Laptop 501"}


def test_get_asset_object_resolves_object_key(assets_fetcher: JiraFetcher):
    """An object key is resolved to its numeric ID via an AQL lookup."""
    assets_fetcher.jira.get = MagicMock(
        side_effect=[
            # aql/objects?qlQuery=Key = "HW-501"
            {"objectEntries": [{"id": 501, "objectKey": "HW-501"}]},
            # object/501
            {"id": 501, "objectKey": "HW-501", "attributes": []},
        ]
    )

    result = assets_fetcher.get_asset_object("HW-501")

    lookup_path, lookup_kwargs = assets_fetcher.jira.get.call_args_list[0]
    assert lookup_path[0].endswith("aql/objects")
    assert lookup_kwargs["params"]["qlQuery"] == 'Key = "HW-501"'
    assert lookup_kwargs["params"]["includeAttributes"] == "false"
    assert assets_fetcher.jira.get.call_args_list[1][0][0].endswith("object/501")
    assert result["id"] == "501"


def test_get_asset_object_unknown_key(assets_fetcher: JiraFetcher):
    """An object key that matches nothing should raise."""
    assets_fetcher.jira.get = MagicMock(return_value={"objectEntries": []})

    with pytest.raises(ValueError, match="HW-999"):
        assets_fetcher.get_asset_object("HW-999")


def test_get_asset_object_rejects_quoted_object_key(
    assets_fetcher: JiraFetcher,
):
    """Keys that would break out of the AQL literal are rejected."""
    assets_fetcher.jira.get = MagicMock()

    with pytest.raises(ValueError, match="Invalid object key"):
        assets_fetcher.get_asset_object('HW-1" OR Key != "')

    assets_fetcher.jira.get.assert_not_called()


def test_get_asset_object_degrades_without_type_lookup(assets_fetcher: JiraFetcher):
    """If the attribute lookup fails, raw attribute IDs should be used as keys."""
    assets_fetcher.jira.get = MagicMock(
        side_effect=[
            {
                "id": 501,
                "objectType": {"id": 10, "name": "Laptop"},
                "attributes": [
                    {
                        "objectTypeAttributeId": 100,
                        "objectAttributeValues": [{"displayValue": "Laptop 501"}],
                    }
                ],
            },
            RuntimeError("permission denied"),
        ]
    )

    result = assets_fetcher.get_asset_object("501")

    assert result["attributes"] == {"100": "Laptop 501"}


def test_get_asset_object_history(assets_fetcher: JiraFetcher):
    """History entries should be flattened."""
    assets_fetcher.jira.get = MagicMock(
        return_value=[
            {
                "id": 1,
                "actor": {"displayName": "Example User"},
                "created": "2024-03-01T00:00:00.000Z",
                "type": 1,
                "affectedAttribute": "Owner",
                "oldValue": "A",
                "newValue": "B",
            }
        ]
    )

    result = assets_fetcher.get_asset_object_history("501")

    assert assets_fetcher.jira.get.call_args[0][0].endswith("object/501/history")
    assert result[0]["actor"] == "Example User"
    assert result[0]["old_value"] == "A"
    assert result[0]["new_value"] == "B"


def test_get_asset_object_connected_tickets(assets_fetcher: JiraFetcher):
    """Connected tickets should be returned as-is from the API."""
    payload = {"tickets": [{"key": "SUP-1"}]}
    assets_fetcher.jira.get = MagicMock(return_value=payload)

    result = assets_fetcher.get_asset_object_connected_tickets("501")

    assert assets_fetcher.jira.get.call_args[0][0].endswith(
        "objectconnectedtickets/501/tickets"
    )
    assert result == payload


# ----------------------------------------------------------------------
# Write
# ----------------------------------------------------------------------


def test_create_asset_object_payload(assets_fetcher: JiraFetcher):
    """Create should build the Insight attribute payload correctly."""
    assets_fetcher.jira.post = MagicMock(
        return_value={
            "id": 600,
            "objectKey": "HW-600",
            "label": "New Laptop",
            "objectType": {"id": 10, "name": "Laptop"},
            "attributes": [],
        }
    )

    result = assets_fetcher.create_asset_object(
        "10", {"100": "New Laptop", "102": ["Red", "Blue"], "103": None}
    )

    called_path, called_kwargs = assets_fetcher.jira.post.call_args
    assert called_path[0].endswith("object/create")
    assert called_kwargs["data"] == {
        "objectTypeId": "10",
        "attributes": [
            {
                "objectTypeAttributeId": "100",
                "objectAttributeValues": [{"value": "New Laptop"}],
            },
            {
                "objectTypeAttributeId": "102",
                "objectAttributeValues": [{"value": "Red"}, {"value": "Blue"}],
            },
            {
                "objectTypeAttributeId": "103",
                "objectAttributeValues": [{"value": ""}],
            },
        ],
    }
    assert result["id"] == "600"
    assert result["object_key"] == "HW-600"


def test_create_asset_object_requires_attributes(assets_fetcher: JiraFetcher):
    """Create should reject an empty attribute mapping."""
    assets_fetcher.jira.post = MagicMock()

    with pytest.raises(ValueError, match="attributes"):
        assets_fetcher.create_asset_object("10", {})

    assets_fetcher.jira.post.assert_not_called()


def test_update_asset_object(assets_fetcher: JiraFetcher):
    """Update should PUT the supplied attributes plus the resolved type ID."""
    assets_fetcher.jira.get = MagicMock(
        return_value={"id": 501, "objectType": {"id": 10, "name": "Laptop"}}
    )
    assets_fetcher.jira.put = MagicMock(
        return_value={
            "id": 501,
            "objectKey": "HW-501",
            "objectType": {"id": 10, "name": "Laptop"},
            "attributes": [],
        }
    )

    result = assets_fetcher.update_asset_object("501", {"101": "PPL-43"})

    # The type ID is read from the object before the update.
    assert assets_fetcher.jira.get.call_args[0][0].endswith("object/501")
    called_path, called_kwargs = assets_fetcher.jira.put.call_args
    assert called_path[0].endswith("object/501")
    assert called_kwargs["data"] == {
        "attributes": [
            {
                "objectTypeAttributeId": "101",
                "objectAttributeValues": [{"value": "PPL-43"}],
            }
        ],
        "objectTypeId": "10",
    }
    assert result["id"] == "501"


def test_update_asset_object_with_explicit_type_skips_lookup(
    assets_fetcher: JiraFetcher,
):
    """Passing object_type_id should avoid the extra GET."""
    assets_fetcher.jira.get = MagicMock()
    assets_fetcher.jira.put = MagicMock(return_value={"id": 501, "attributes": []})

    assets_fetcher.update_asset_object("501", {"101": "x"}, object_type_id="10")

    assets_fetcher.jira.get.assert_not_called()
    assert assets_fetcher.jira.put.call_args[1]["data"]["objectTypeId"] == "10"


def test_update_asset_object_without_resolvable_type(assets_fetcher: JiraFetcher):
    """If the type cannot be resolved the update is still attempted."""
    assets_fetcher.jira.get = MagicMock(return_value="unexpected")
    assets_fetcher.jira.put = MagicMock(return_value={"id": 501, "attributes": []})

    assets_fetcher.update_asset_object("501", {"101": "x"})

    assert "objectTypeId" not in assets_fetcher.jira.put.call_args[1]["data"]


def test_search_assets_aql_schema_filter(assets_fetcher: JiraFetcher):
    """schema_id should be passed through as objectSchemaId."""
    assets_fetcher.jira.get = MagicMock(return_value={"objectEntries": []})

    assets_fetcher.search_assets_aql("objectType = X", schema_id=" 3 ")

    params = assets_fetcher.jira.get.call_args[1]["params"]
    assert params["objectSchemaId"] == "3"


def test_search_assets_aql_omits_empty_schema_filter(assets_fetcher: JiraFetcher):
    """An empty schema_id should not add objectSchemaId."""
    assets_fetcher.jira.get = MagicMock(return_value={"objectEntries": []})

    assets_fetcher.search_assets_aql("objectType = X", schema_id="  ")

    assert "objectSchemaId" not in assets_fetcher.jira.get.call_args[1]["params"]
