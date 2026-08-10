"""Tests for AIO Tests test case operations."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.aio.cases import _build_step_payload, _date_criteria
from tests.fixtures.aio_mocks import (
    MOCK_AIO_FOLDER_TREE,
    MOCK_AIO_PROJECT_CONFIG,
    MOCK_AIO_SEARCH_RESPONSE,
    MOCK_AIO_TEST_CASE,
)


@pytest.fixture
def fetcher(aio_fetcher):
    """Provide a fetcher whose reads are routed to the right mock payload."""

    def fake_get(path, params=None):
        if path.endswith("/config"):
            return MOCK_AIO_PROJECT_CONFIG
        if path.endswith("/folder"):
            return MOCK_AIO_FOLDER_TREE
        if path.endswith("/tag"):
            return [{"ID": 2, "name": "Smoke"}]
        if path.endswith("/detail"):
            return MOCK_AIO_TEST_CASE
        return MOCK_AIO_SEARCH_RESPONSE

    aio_fetcher.get = MagicMock(side_effect=fake_get)
    aio_fetcher.post = MagicMock(return_value=MOCK_AIO_TEST_CASE)
    aio_fetcher.put = MagicMock(return_value=MOCK_AIO_TEST_CASE)
    return aio_fetcher


class TestBuildStepPayload:
    """Tests for step payload construction."""

    def test_classic_step_defaults_to_text(self):
        """A step without an explicit type is a Classic TEXT step."""
        payload = _build_step_payload(
            {"step": "Do it", "data": "x", "expected_result": "done"}, 0
        )

        assert payload == {
            "step": "Do it",
            "data": "x",
            "expectedResult": "done",
            "stepType": "TEXT",
        }

    def test_bdd_step_defaults_to_given(self):
        """A step with only BDD text defaults to a Given step."""
        payload = _build_step_payload({"bdd_step": "I am logged in"}, 0)

        assert payload == {"bddStep": "I am logged in", "stepType": "BDD_GIVEN"}

    def test_bdd_step_type_is_kept(self):
        """An explicit BDD keyword is preserved."""
        payload = _build_step_payload(
            {"bdd_step": "I click", "step_type": "BDD_WHEN"}, 0
        )

        assert payload["stepType"] == "BDD_WHEN"

    def test_reference_step(self):
        """A referenced case is nested under referencedCase."""
        payload = _build_step_payload(
            {"step_type": "REFERENCE", "referenced_case_key": "AT-TC-9"}, 0
        )

        assert payload == {
            "stepType": "REFERENCE",
            "referencedCase": {"key": "AT-TC-9"},
        }

    def test_camel_case_keys_are_accepted(self):
        """API-style keys work as well as snake_case ones."""
        payload = _build_step_payload(
            {"step": "a", "expectedResult": "b", "stepType": "TEXT"}, 0
        )

        assert payload["expectedResult"] == "b"

    def test_unknown_key_raises(self):
        """A typo in a step key is reported instead of silently dropped."""
        with pytest.raises(ValueError, match="Unknown key 'expect'"):
            _build_step_payload({"step": "a", "expect": "b"}, 0)

    def test_invalid_step_type_raises(self):
        """Only documented step types are accepted."""
        with pytest.raises(ValueError, match="Invalid step_type"):
            _build_step_payload({"step": "a", "step_type": "SCENARIO"}, 0)

    def test_text_step_without_text_raises(self):
        """A TEXT step needs step text."""
        with pytest.raises(ValueError, match="no step text"):
            _build_step_payload({"data": "x"}, 0)

    def test_bdd_step_without_text_raises(self):
        """A BDD step needs BDD text."""
        with pytest.raises(ValueError, match="no bdd_step text"):
            _build_step_payload({"step_type": "BDD_THEN"}, 2)

    def test_reference_step_without_key_raises(self):
        """A REFERENCE step needs the referenced case key."""
        with pytest.raises(ValueError, match="no referenced_case_key"):
            _build_step_payload({"step_type": "REFERENCE"}, 0)

    def test_non_object_step_raises(self):
        """Steps must be objects."""
        with pytest.raises(ValueError, match="must be an object"):
            _build_step_payload("just text", 0)  # type: ignore[arg-type]


class TestDateCriteria:
    """Tests for date search criteria."""

    def test_between(self):
        """Two bounds produce a BETWEEN criteria."""
        assert _date_criteria("a", "b") == {
            "comparisonType": "BETWEEN",
            "value1": "a",
            "value2": "b",
        }

    def test_after_only(self):
        """A lower bound alone produces AFTER."""
        assert _date_criteria("a", None) == {"comparisonType": "AFTER", "value1": "a"}

    def test_before_only(self):
        """An upper bound alone produces BEFORE."""
        assert _date_criteria(None, "b") == {"comparisonType": "BEFORE", "value1": "b"}

    def test_no_bounds(self):
        """No bounds produce no criteria."""
        assert _date_criteria(None, None) is None


class TestGetTestCase:
    """Tests for get_test_case."""

    def test_returns_parsed_case(self, fetcher):
        """The case payload is parsed into the model."""
        case = fetcher.get_test_case("PROJ", "AT-TC-17")

        assert case.key == "AT-TC-17"
        assert case.priority.name == "Critical"
        assert case.folder.name == "Checkout"
        assert [step.step for step in case.steps] == [
            "Search for an item",
            "Click quick add to cart",
        ]
        assert [tag.name for tag in case.tags] == ["Smoke"]

    def test_sends_optional_parameters(self, fetcher):
        """Optional flags reach the API as query parameters."""
        fetcher.get_test_case(
            "PROJ", "AT-TC-17", version=1, include_rtf=True, include_attachments=True
        )

        args, kwargs = fetcher.get.call_args
        assert args[0] == "/project/PROJ/testcase/AT-TC-17/detail"
        assert kwargs["params"] == {
            "needDataInRTF": True,
            "needAttachments": True,
            "version": 1,
        }

    def test_unset_flags_are_not_sent(self, fetcher):
        """Defaults leave the query parameters unset."""
        fetcher.get_test_case("PROJ", "AT-TC-17")

        _, kwargs = fetcher.get.call_args
        assert kwargs["params"] == {
            "needDataInRTF": None,
            "needAttachments": None,
            "version": None,
        }

    def test_simplified_dict_shape(self, fetcher):
        """The simplified dict keeps the useful case fields."""
        result = fetcher.get_test_case("PROJ", "AT-TC-17").to_simplified_dict()

        assert result["key"] == "AT-TC-17"
        assert result["status"] == {"id": 21, "name": "Published"}
        assert result["jira_requirement_ids"] == ["10221"]
        assert result["custom_fields"] == [
            {"ID": 10113, "name": "Environment", "value": "Staging"}
        ]


class TestGetTestCaseVersions:
    """Tests for get_test_case_versions."""

    def test_marks_the_current_version(self, fetcher):
        """The case's own version is flagged as current."""
        case = fetcher.get_test_case_versions("PROJ", "AT-TC-17")

        assert [version.to_simplified_dict() for version in case.versions] == [
            {"is_current": True, "version": 2, "id": 16557},
            {"is_current": False, "version": 1, "id": 16556},
        ]


class TestSearchTestCases:
    """Tests for search_test_cases."""

    def test_without_filters_lists_cases(self, fetcher):
        """With no criteria the plain listing endpoint is used."""
        result = fetcher.search_test_cases("PROJ")

        fetcher.post.assert_not_called()
        args, kwargs = fetcher.get.call_args
        assert args[0] == "/project/PROJ/testcase"
        assert kwargs["params"]["startAt"] == 0
        assert len(result.cases) == 1

    def test_title_criteria(self, fetcher):
        """A title filter posts a CONTAINS criteria."""
        fetcher.search_test_cases("PROJ", title="cart")

        args, kwargs = fetcher.post.call_args
        assert args[0] == "/project/PROJ/testcase/search"
        assert kwargs["json"] == {
            "title": {"comparisonType": "CONTAINS", "value": "cart"}
        }

    def test_invalid_title_match_raises(self, fetcher):
        """Only the two documented comparisons are allowed."""
        with pytest.raises(ValueError, match="Invalid title_match"):
            fetcher.search_test_cases("PROJ", title="x", title_match="STARTS_WITH")

    def test_lookup_names_are_resolved(self, fetcher):
        """Status, priority and type names resolve to IDs."""
        fetcher.search_test_cases(
            "PROJ",
            statuses=["Published"],
            priorities=["Critical"],
            types=["Functional"],
            automation_statuses=["Automated"],
        )

        _, kwargs = fetcher.post.call_args
        assert kwargs["json"]["statusID"] == {"comparisonType": "IN", "list": [21]}
        assert kwargs["json"]["priorityID"] == {"comparisonType": "IN", "list": [10]}
        assert kwargs["json"]["typeID"] == {"comparisonType": "IN", "list": [1]}
        assert kwargs["json"]["automationStatusID"] == {
            "comparisonType": "IN",
            "list": [31],
        }

    def test_folder_paths_are_resolved(self, fetcher):
        """Folder names and paths resolve to folder IDs."""
        fetcher.search_test_cases("PROJ", folders=["/Regression/Checkout", 200])

        _, kwargs = fetcher.post.call_args
        assert kwargs["json"]["folderID"] == {
            "comparisonType": "IN",
            "list": [101, 200],
        }

    def test_text_and_list_criteria(self, fetcher):
        """Keys, tags, owners and requirements map to list criteria."""
        fetcher.search_test_cases(
            "PROJ",
            keys=["AT-TC-1"],
            tags=["Smoke"],
            owner_ids=["acc-1"],
            requirement_ids=["PROJ-42"],
            automation_key="com.example.Test",
        )

        payload = fetcher.post.call_args[1]["json"]
        assert payload["key"] == {"comparisonType": "IN", "list": ["AT-TC-1"]}
        assert payload["tag"] == {"comparisonType": "IN", "list": ["Smoke"]}
        assert payload["ownedByID"] == {"comparisonType": "IN", "list": ["acc-1"]}
        assert payload["requirementID"] == {"comparisonType": "IN", "list": ["PROJ-42"]}
        assert payload["automationKey"] == {
            "comparisonType": "CONTAINS",
            "value": "com.example.Test",
        }

    def test_date_and_archived_criteria(self, fetcher):
        """Date ranges and the archived flag map to their criteria."""
        fetcher.search_test_cases(
            "PROJ",
            created_after="2026-01-01T00:00:00Z",
            updated_before="2026-02-01T00:00:00Z",
            include_archived=False,
        )

        payload = fetcher.post.call_args[1]["json"]
        assert payload["createdDate"]["comparisonType"] == "AFTER"
        assert payload["updatedDate"]["comparisonType"] == "BEFORE"
        assert payload["isArchived"] == {"value": False}

    def test_page_size_is_clamped_to_api_minimum(self, fetcher):
        """The API rejects pages below 10, so a small ask is padded then trimmed."""
        result = fetcher.search_test_cases("PROJ", max_results=1)

        _, kwargs = fetcher.get.call_args
        assert kwargs["params"]["maxResults"] == 10
        assert result.max_results == 1

    def test_extra_results_are_trimmed(self, aio_fetcher):
        """Results beyond the requested count are dropped and flagged."""
        aio_fetcher.get = MagicMock(
            return_value={
                "items": [MOCK_AIO_TEST_CASE] * 10,
                "startAt": 0,
                "maxResults": 10,
                "isLast": True,
            }
        )

        result = aio_fetcher.search_test_cases("PROJ", max_results=3)

        assert len(result.cases) == 3
        assert result.is_last is False

    def test_simplified_dict_shape(self, fetcher):
        """The search result exposes pagination metadata."""
        result = fetcher.search_test_cases("PROJ").to_simplified_dict()

        assert result["count"] == 1
        assert result["start_at"] == 0
        assert result["is_last"] is True
        assert result["test_cases"][0]["key"] == "AT-TC-17"


class TestCreateTestCase:
    """Tests for create_test_case."""

    def test_minimal_case(self, fetcher):
        """A title alone is enough to create a case."""
        fetcher.create_test_case("PROJ", "New case")

        args, kwargs = fetcher.post.call_args
        assert args[0] == "/project/PROJ/testcase"
        assert kwargs["json"] == {"title": "New case"}

    @pytest.mark.parametrize("title", ["", "   "])
    def test_empty_title_raises(self, fetcher, title):
        """An empty title is rejected before any call."""
        with pytest.raises(ValueError, match="title is required"):
            fetcher.create_test_case("PROJ", title)
        fetcher.post.assert_not_called()

    def test_resolves_lookups_and_folder(self, fetcher):
        """Field names are resolved to the IDs the API expects."""
        fetcher.create_test_case(
            "PROJ",
            "New case",
            priority="Critical",
            status="Published",
            type="Functional",
            script_type="BDD",
            automation_status="Automated",
            folder="/Regression/Checkout",
        )

        payload = fetcher.post.call_args[1]["json"]
        assert payload["priority"] == {"ID": 10}
        assert payload["status"] == {"ID": 21}
        assert payload["type"] == {"ID": 1}
        assert payload["scriptType"] == {"ID": 41}
        assert payload["automationStatus"] == {"ID": 31}
        assert payload["folder"] == {"ID": 101}

    def test_builds_steps(self, fetcher):
        """Steps are translated into the API shape."""
        fetcher.create_test_case(
            "PROJ",
            "New case",
            steps=[{"step": "Login", "expected_result": "Home page"}],
        )

        payload = fetcher.post.call_args[1]["json"]
        assert payload["steps"] == [
            {"step": "Login", "expectedResult": "Home page", "stepType": "TEXT"}
        ]

    def test_resolves_tags(self, fetcher):
        """Tag names resolve to existing tag IDs."""
        fetcher.create_test_case("PROJ", "New case", tags=["Smoke"])

        payload = fetcher.post.call_args[1]["json"]
        assert payload["tags"] == [{"tag": {"ID": 2, "name": "Smoke"}}]

    def test_custom_fields_from_mapping(self, fetcher):
        """A name/value mapping resolves to custom field IDs."""
        fetcher.create_test_case(
            "PROJ", "New case", custom_fields={"Environment": "Staging"}
        )

        payload = fetcher.post.call_args[1]["json"]
        assert payload["customFields"] == [
            {"ID": 10113, "name": "Environment", "value": "Staging"}
        ]

    def test_custom_fields_from_list(self, fetcher):
        """A list of entries works too, including explicit IDs."""
        fetcher.create_test_case(
            "PROJ",
            "New case",
            custom_fields=[{"id": 10114, "value": "acc-1"}],
        )

        payload = fetcher.post.call_args[1]["json"]
        assert payload["customFields"] == [
            {"ID": 10114, "name": None, "value": "acc-1"}
        ]

    def test_unknown_custom_field_raises(self, fetcher):
        """An undefined custom field name is reported with the alternatives."""
        with pytest.raises(ValueError, match="is not defined for project"):
            fetcher.create_test_case("PROJ", "New case", custom_fields={"Nope": 1})

    def test_jira_associations(self, fetcher):
        """Requirement, component and release IDs are forwarded."""
        fetcher.create_test_case(
            "PROJ",
            "New case",
            requirement_ids=["PROJ-42"],
            component_ids=[10000],
            release_ids=["10500"],
        )

        payload = fetcher.post.call_args[1]["json"]
        assert payload["jiraRequirementIDs"] == ["PROJ-42"]
        assert payload["jiraComponentIDs"] == [10000]
        assert payload["jiraReleaseIDs"] == [10500]

    def test_unknown_field_raises(self, fetcher):
        """A misspelled field name is reported instead of dropped."""
        with pytest.raises(ValueError, match="Unknown test case field"):
            fetcher.create_test_case("PROJ", "New case", priorty="Critical")

    def test_include_rtf_flag(self, fetcher):
        """The RTF flag reaches the API as a query parameter."""
        fetcher.create_test_case("PROJ", "New case", include_rtf=True)

        assert fetcher.post.call_args[1]["params"] == {"needDataInRTF": True}

    def test_missing_folder_is_created(self, fetcher):
        """A folder that does not exist yet is created on demand."""
        fetcher.create_test_case("PROJ", "New case", folder="/Brand/New")

        fetcher.put.assert_called_once()
        assert fetcher.put.call_args[1]["json"] == {"folderHierarchy": ["Brand", "New"]}

    def test_missing_folder_can_be_rejected(self, fetcher):
        """Folder creation can be turned off."""
        with pytest.raises(ValueError, match="was not found"):
            fetcher.create_test_case(
                "PROJ",
                "New case",
                folder="/Brand/New",
                create_folder_if_missing=False,
            )


class TestUpdateTestCase:
    """Tests for update_test_case."""

    def test_merges_with_current_case(self, fetcher):
        """Unspecified fields keep their current values."""
        fetcher.update_test_case("PROJ", "AT-TC-17", priority="Medium")

        args, kwargs = fetcher.put.call_args
        assert args[0] == "/project/PROJ/testcase/AT-TC-17/detail"
        payload = kwargs["json"]
        assert payload["priority"] == {"ID": 11}
        assert payload["title"] == MOCK_AIO_TEST_CASE["title"]
        assert payload["steps"] == MOCK_AIO_TEST_CASE["steps"]

    def test_strips_read_only_fields(self, fetcher):
        """Read-only attributes are never sent back."""
        fetcher.update_test_case("PROJ", "AT-TC-17", priority="Medium")

        payload = fetcher.put.call_args[1]["json"]
        for field in ("key", "version", "createdDate", "isArchived", "versions"):
            assert field not in payload

    def test_replaces_steps(self, fetcher):
        """Supplying steps replaces the whole list."""
        fetcher.update_test_case("PROJ", "AT-TC-17", steps=[{"bdd_step": "I log in"}])

        payload = fetcher.put.call_args[1]["json"]
        assert payload["steps"] == [{"bddStep": "I log in", "stepType": "BDD_GIVEN"}]

    def test_updates_title(self, fetcher):
        """The title can be changed like any other field."""
        fetcher.update_test_case("PROJ", "AT-TC-17", title="Renamed")

        assert fetcher.put.call_args[1]["json"]["title"] == "Renamed"

    def test_empty_title_raises(self, fetcher):
        """Clearing the title is rejected."""
        with pytest.raises(ValueError, match="title cannot be empty"):
            fetcher.update_test_case("PROJ", "AT-TC-17", title="  ")

    def test_no_changes_raises(self, fetcher):
        """An update with nothing to change is rejected."""
        with pytest.raises(ValueError, match="No fields to update"):
            fetcher.update_test_case("PROJ", "AT-TC-17")
        fetcher.put.assert_not_called()

    def test_does_not_create_a_version_by_default(self, fetcher):
        """In-place update is the default behaviour."""
        fetcher.update_test_case("PROJ", "AT-TC-17", priority="Medium")

        assert fetcher.put.call_args[1]["params"]["createNewVersion"] is None

    def test_can_create_a_new_version(self, fetcher):
        """A new version is created only when asked for."""
        fetcher.update_test_case(
            "PROJ", "AT-TC-17", priority="Medium", create_new_version=True
        )

        assert fetcher.put.call_args[1]["params"]["createNewVersion"] is True

    def test_targets_a_specific_version(self, fetcher):
        """The version parameter is forwarded to both the read and the write."""
        fetcher.update_test_case("PROJ", "AT-TC-17", priority="Medium", version=1)

        assert fetcher.get.call_args[1]["params"]["version"] == 1
        assert fetcher.put.call_args[1]["params"]["version"] == 1

    def test_round_trips_rich_text_markup(self, fetcher):
        """Both sides of the round trip keep HTML so formatting is not flattened."""
        fetcher.update_test_case("PROJ", "AT-TC-17", priority="Medium")

        assert fetcher.get.call_args[1]["params"]["needDataInRTF"] is True
        assert fetcher.put.call_args[1]["params"]["needDataInRTF"] is True

    def test_escapes_plain_text_values(self, fetcher):
        """Plain-text input is escaped so it is stored as written."""
        fetcher.update_test_case(
            "PROJ",
            "AT-TC-17",
            description="a < b & c\nsecond line",
            precondition="x > y",
        )

        payload = fetcher.put.call_args[1]["json"]
        assert payload["description"] == "a &lt; b &amp; c<br/>second line"
        assert payload["precondition"] == "x &gt; y"

    def test_escapes_plain_text_steps(self, fetcher):
        """Step text is escaped along with the other rich-text fields."""
        fetcher.update_test_case(
            "PROJ", "AT-TC-17", steps=[{"step": "click <ok>", "data": "a & b"}]
        )

        step = fetcher.put.call_args[1]["json"]["steps"][0]
        assert step["step"] == "click &lt;ok&gt;"
        assert step["data"] == "a &amp; b"

    def test_escapes_multi_line_custom_fields_only(self, fetcher):
        """Only multi-line text custom fields are escaped."""
        fetcher.update_test_case(
            "PROJ",
            "AT-TC-17",
            custom_fields={"Notes": "a < b", "Environment": "a < b"},
        )

        by_name = {
            field["name"]: field["value"]
            for field in fetcher.put.call_args[1]["json"]["customFields"]
        }
        assert by_name["Notes"] == "a &lt; b"
        assert by_name["Environment"] == "a < b"

    def test_html_input_is_passed_through(self, fetcher):
        """With include_rtf the caller's HTML reaches the API untouched."""
        fetcher.update_test_case(
            "PROJ",
            "AT-TC-17",
            description="<p>Rich <b>text</b></p>",
            include_rtf=True,
        )

        payload = fetcher.put.call_args[1]["json"]
        assert payload["description"] == "<p>Rich <b>text</b></p>"

    def test_create_does_not_escape_plain_text(self, fetcher):
        """Creation has nothing to round-trip, so values are sent verbatim."""
        fetcher.create_test_case("PROJ", "New case", description="a < b")

        assert fetcher.post.call_args[1]["json"]["description"] == "a < b"

    def test_missing_case_raises(self, aio_fetcher):
        """A case that cannot be read is reported clearly."""
        aio_fetcher.get = MagicMock(
            side_effect=lambda path, params=None: (
                MOCK_AIO_PROJECT_CONFIG if path.endswith("/config") else None
            )
        )
        aio_fetcher.put = MagicMock()

        with pytest.raises(ValueError, match="was not found"):
            aio_fetcher.update_test_case("PROJ", "AT-TC-99", priority="Medium")
