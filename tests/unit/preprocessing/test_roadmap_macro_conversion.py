"""Tests for Confluence Roadmap Planner macro to Markdown table conversion."""

import json
import urllib.parse

from mcp_atlassian.preprocessing.base import BasePreprocessor


def _make_roadmap_macro(data: dict) -> str:
    encoded = urllib.parse.quote(json.dumps(data))
    return (
        '<ac:structured-macro ac:name="roadmap">'
        f'<ac:parameter ac:name="source">{encoded}</ac:parameter>'
        "</ac:structured-macro>"
    )


ROADMAP_DATA = {
    "title": "Q3 Plan",
    "timeline": {
        "startDate": "2024-07-01",
        "endDate": "2024-09-30",
        "displayOption": "Month",
    },
    "lanes": [
        {
            "title": "Backend",
            "bars": [
                {
                    "title": "API v2",
                    "startDate": "2024-07-01",
                    "duration": 2,
                    "description": "REST rewrite",
                },
                {
                    "title": "Auth service",
                    "startDate": "2024-07-15",
                    "duration": 1,
                    "description": "",
                },
            ],
        },
        {
            "title": "Frontend",
            "bars": [
                {
                    "title": "Dashboard",
                    "startDate": "2024-08-01",
                    "duration": 3,
                    "description": "New UI",
                }
            ],
        },
    ],
    "markers": [
        {"markerDate": "2024-09-01", "title": "Beta release"},
    ],
}


ROADMAP_MACRO = _make_roadmap_macro(ROADMAP_DATA)


def test_roadmap_macro_title_and_dates():
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(ROADMAP_MACRO)
    assert "Q3 Plan" in markdown
    assert "2024-07-01" in markdown
    assert "2024-09-30" in markdown


def test_roadmap_macro_table_header():
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(ROADMAP_MACRO)
    assert "| Lane | Item | Start | Duration (months) | Description |" in markdown


def test_roadmap_macro_lanes_and_bars():
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(ROADMAP_MACRO)
    assert "Backend" in markdown
    assert "API v2" in markdown
    assert "REST rewrite" in markdown
    assert "Auth service" in markdown
    assert "Frontend" in markdown
    assert "Dashboard" in markdown
    assert "New UI" in markdown


def test_roadmap_macro_markers():
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(ROADMAP_MACRO)
    assert "Markers:" in markdown
    assert "2024-09-01" in markdown
    assert "Beta release" in markdown


def test_roadmap_macro_no_encoded_json_in_output():
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(ROADMAP_MACRO)
    assert "%7B" not in markdown
    assert "%22" not in markdown


def test_roadmap_macro_fallback_on_bad_source():
    bad_macro = (
        '<ac:structured-macro ac:name="roadmap">'
        '<ac:parameter ac:name="source">not-valid-json-or-encoded</ac:parameter>'
        "</ac:structured-macro>"
    )
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(bad_macro)
    assert "[roadmap macro]" in markdown


def test_roadmap_macro_fallback_on_missing_source():
    no_source = '<ac:structured-macro ac:name="roadmap"></ac:structured-macro>'
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(no_source)
    assert "[roadmap macro]" in markdown


def test_roadmap_macro_pipe_escaping():
    data = {
        "title": "Plan",
        "timeline": {
            "startDate": "2024-01-01",
            "endDate": "2024-12-31",
            "displayOption": "Month",
        },
        "lanes": [
            {
                "title": "Lane|A",
                "bars": [
                    {
                        "title": "Bar|B",
                        "startDate": "2024-01-01",
                        "duration": 1,
                        "description": "desc|C",
                    }
                ],
            }
        ],
    }
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(_make_roadmap_macro(data))
    # Pipes inside cell values must be escaped so the table stays valid
    assert "Lane\\|A" in markdown
    assert "Bar\\|B" in markdown
    assert "desc\\|C" in markdown


def test_roadmap_macro_html_output_unmodified():
    """HTML output keeps the original storage-format macro intact."""
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    html, _ = preprocessor.process_html_content(ROADMAP_MACRO)
    assert 'ac:name="roadmap"' in html


def test_roadmap_macro_surrounding_content_preserved():
    content = f"<p>Before</p>{ROADMAP_MACRO}<p>After</p>"
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(content)
    assert "Before" in markdown
    assert "After" in markdown
    assert "Q3 Plan" in markdown
