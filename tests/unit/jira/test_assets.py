"""Tests for Jira Assets (Insight) discovery on Server/Data Center."""

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


def test_list_asset_schemas(assets_fetcher: JiraFetcher):
    """Schema discovery should return simplified dictionaries."""
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
                }
            ]
        }
    )

    assert assets_fetcher.list_asset_schemas() == [
        {
            "id": "1",
            "name": "Hardware",
            "key": "HW",
            "description": "Physical assets",
            "object_count": 120,
            "object_type_count": 4,
        }
    ]


def test_list_asset_object_types(assets_fetcher: JiraFetcher):
    """Object-type discovery should return a flat simplified list."""
    assets_fetcher.jira.get = MagicMock(
        return_value=[
            {"id": 10, "name": "Laptop", "parentObjectTypeId": 5, "objectCount": 40}
        ]
    )

    result = assets_fetcher.list_asset_object_types("1")

    assert assets_fetcher.jira.get.call_args[0][0].endswith(
        "objectschema/1/objecttypes/flat"
    )
    assert result[0]["parent_object_type_id"] == "5"


def test_list_asset_object_types_rejects_non_numeric_id(
    assets_fetcher: JiraFetcher,
):
    """Schema IDs must not be able to alter the REST path."""
    assets_fetcher.jira.get = MagicMock()

    with pytest.raises(ValueError, match="schema_id must be a numeric ID"):
        assets_fetcher.list_asset_object_types("1/attributes")

    assets_fetcher.jira.get.assert_not_called()


def test_get_asset_object_type_attributes(assets_fetcher: JiraFetcher):
    """Attribute discovery should expose IDs, cardinality, and references."""
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

    assert result[0]["required"] is True
    assert result[0]["default_type"] == "Text"
    assert result[1]["reference_object_type_id"] == "7"
    assert result[1]["reference_object_type_name"] == "Person"


def test_search_assets_aql_for_issue_include(assets_fetcher: JiraFetcher):
    """The internal Assets search should resolve names and pagination."""
    assets_fetcher.jira.get = MagicMock(
        return_value={
            "objectEntries": [
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
                }
            ],
            "objectTypeAttributes": [{"id": 100, "name": "Name"}],
            "totalFilterCount": 1,
            "pageNumber": 1,
            "pageSize": 1,
            "pageObjectSize": 100,
        }
    )

    result = assets_fetcher.search_assets_aql(
        'object HAVING connectedTickets(key = "TEST-123")', results_per_page=100
    )

    assert assets_fetcher.jira.get.call_args[1]["params"]["qlQuery"] == (
        'object HAVING connectedTickets(key = "TEST-123")'
    )
    assert result["objects"][0]["attributes"] == {"Name": "Laptop 501"}
    assert result["total"] == 1


def test_search_assets_aql_uses_legacy_insight_endpoint(
    assets_fetcher: JiraFetcher,
):
    """The legacy Insight base should use iql/objects and its iql parameter."""
    assets_fetcher.config.assets_api_base = "rest/insight/1.0"
    assets_fetcher.jira.get = MagicMock(return_value={"objectEntries": []})

    assets_fetcher.search_assets_aql("objectType = Laptop")

    called_path, called_kwargs = assets_fetcher.jira.get.call_args
    assert called_path[0] == "rest/insight/1.0/iql/objects"
    assert called_kwargs["params"]["iql"] == "objectType = Laptop"
