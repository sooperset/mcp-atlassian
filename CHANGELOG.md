# Changelog

## [Unreleased]

## [0.6.0] - 2025-04-05

### Added
- Add pagination support to Jira list tools with new `startAt` parameter for `jira_search`, `jira_get_project_issues`, and `jira_get_epic_issues` (#198)
- Add pytest workflow for automated testing across multiple Python versions (3.10, 3.11, 3.12) (#200)
- Add Smithery deployment and installation support (#194)

### Changed
- Unify pagination parameter names to 'startAt' across Jira tools for better consistency and developer experience (#201)
- Improve configuration documentation and readability in .env.example with clear sections and alternative options (#192)

### Fixed
- Fix model property access in JiraIssue to prevent custom fields from overriding model properties (#199)
- Fix read_resource signature to properly take in an AnyUrl and return str (#195)
- Correct command invocation instructions in README.md to use the `mcp-atlassian` script instead of incorrect `python -m` commands (#197)
- Update server tests for read_resource signature change (#199)

## [0.5.0] - 2025-04-03

### Added
- Add tools to retrieve Jira Agile boards (`jira_get_agile_boards`), sprints (`jira_get_sprints_from_board`), board issues (`jira_get_board_issues`), and sprint issues (`jira_get_sprint_issues`) (#166)
- Implement Jira attachment upload functionality via `jira_update_issue` tool using the `attachments` parameter (#168, #7ad3485)
- Add tool to attach content to Confluence pages (`confluence_attach_content`) (#178)
- Add explicit `MCPAtlassianAuthenticationError` for handling 401/403 authentication errors, providing clearer feedback for expired tokens or permission issues (#190, #183)

### Changed
- Improve custom field handling in `JiraIssue` model to automatically include all fields not explicitly processed under `custom_fields`, making more data accessible (#182)
- Enable basic authentication support (username/API token) for on-premise/Data Center Confluence instances, previously only token auth was explicitly checked (#173)
- General updates and refinements to Jira issue handling logic (#187)

### Fixed
- Parse `fixVersions` field correctly in Jira issues, previously missed (#162)
- Fix JQL error in `list_resources` when user identifier (e.g., email) contains special characters like '@' by properly quoting and escaping the identifier (#180, #172)
- Fix Confluence search (`confluence_search`) and resource reading (`read_resource` for space URIs) when using space keys that require quotes (e.g., personal spaces '~...', reserved CQL words, numeric keys) by adding conditional CQL identifier quoting (#185, #184)
- Fix Python C-level timestamp conversion error ("timestamp too large") when fetching user data from Jira Data Center 9.x instances by using a direct API request bypassing the problematic library parsing (#189, #171)

## [0.4.0] - 2025-03-28

### Added
- Added support for retrieving Jira custom fields via MCP API (#157)
- Added ability to download attachments from JIRA issues (#160)
- Added development environment with devcontainer support (#159)
- Added JiraBoards and get_all_agile_boards tool (#158)

## [0.3.1] - 2025-03-27

### Added
- Added support for Jira and Confluence search filtering (#133)

### Changed
- Refactored utils module into specialized sub-modules for better organization (#154)
- Updated documentation with new MCP setting guidance for Cursor IDE 0.47+ (#153)
- Reduced default logging level to WARNING for better client compatibility (#155)

### Fixed
- Fixed SSLError when using SSL verification bypass option (#150)
- Enabled legacy SSL renegotiation in Python 3.11+ environments

## [0.3.0] - 2025-03-25

### Added
- Added read-only mode to disable write operations
- Added CONTRIBUTING.md with development setup and workflow guidelines

### Enhanced
- Simplified README structure for better clarity
- Improved field parameter handling in jira_search function
- Enhanced documentation with focus on CLI arguments as primary configuration method

### Fixed
- Fixed fields parameter in jira_search function to properly filter returned fields

## [0.2.6] - 2025-03-22

### Added
- Added support for getting Confluence pages in raw format without converting to markdown

### Enhanced
- Enhanced Jira Epic creation with a two-step approach for better field handling
- Enhanced Epic field discovery with improved fallback mechanisms
- Enhanced test script to support test filtering and added new tests for Jira Epic creation

### Fixed
- Fixed SSL verification bypass for self-signed certificates
- Implemented proper SSL verification handling for Confluence and Jira servers

## [0.2.5] - 2025-03-18

### Added
- Added dynamic custom field retrieval in JiraIssue with pattern matching support

### Fixed
- Fixed to allow parent field for all issue types, not just subtasks
- Fixed user identification for Jira Data Center/Server instances with fallback mechanisms
- Fixed pre-commit errors and updated unit tests

## [0.2.4] - 2025-03-17

### Added
- Added support for Jira subtask creation with proper parent relationship handling
- Added method to prepare parent fields for subtasks
- Updated API documentation to include subtask creation guidance

## [0.2.3] - 2025-03-16

### Added
- Added user details retrieval by account ID in ConfluenceClient to support proper user mention handling
- Added Confluence page ancestors functionality for more reliable parent-child relationship tracking
- Added SSE transport support for improved performance and reliability

### Changed
- Refactored markdown conversion to ConfluencePreprocessor class
- Moved markdown_to_confluence_storage function from utils to ConfluencePreprocessor
- Updated documentation with SSE configuration guidance

## [0.2.2] - 2025-03-13

### Added
- Added Confluence get-children-page tool (#98)

### Changed
- Separated Jira and Confluence preprocessing logic for better maintainability (#99)
- Updated README.md with Composer and Agent mode screencaptures (#95, #101)
- Updated README.md with new demo GIF (#93)

### Fixed
- Fixed Confluence update page textcontent issue (#100)

## [0.2.1] - 2025-03-13

### Added
- Added Confluence Server/Data Center support with Personal Access Token authentication
- Added Confluence page delete tool

### Fixed
- Fixed error with confluence_delete_page function
- Fixed handling of 'fields' attribute error in Jira fetcher
- Removed duplicate content field in Confluence page metadata
- Improved Confluence search functionality
- Added Docker installation instructions

## [0.2.0] - 2025-03-12

### Changed
- Major refactoring of Atlassian integration components into modular mixin classes
- Added Pydantic models for type-safe API responses
- Enhanced unit tests with better mocks and fixtures
- Added support for testing with real API data

### Fixed
- Fixed Jira transition API type handling errors
- Improved handling of different status formats in update methods
- Added robust handling for missing fields in Jira search responses
- Enhanced field parsing and automatic field expansion

## [0.1.16] - 2025-03-09

### Fixed
- Fixed authentication for Jira Server/Data Center deployments
- Modified environment variable check to properly support Server/Data Center

## [0.1.15] - 2025-03-08

### Added
- Added Jira Server/Data Center support with Personal Access Token authentication
- Added new Jira worklog tools for time tracking and estimate management
- Added tools for Jira status transitions: `jira_get_transitions` and `jira_transition_issue`
- Added comprehensive Epic linking support with `jira_link_to_epic` and `jira_get_epic_issues` tools
- Implemented dynamic Jira field discovery for Epic-related fields
- Added SSL verification option for on-premise Jira installations
- Added support for bidirectional Markdown-Jira markup conversion

### Changed
- Enhanced Epic linking with support for different Jira configurations
- Improved JSON serialization and result formatting in Atlassian tool methods
- Simplified Markdown to Jira conversion using TextPreprocessor
- Standardized result formatting across different tool methods

### Fixed
- Fixed Jira status updates to respect workflow rules by using transitions
- Fixed Epic creation with dynamic field discovery across different Jira instances
- Fixed Jira comments and issue descriptions to properly convert Markdown syntax
- Improved error handling in transition_issue with detailed logging
- Enhanced numbered list handling for proper rendering in Jira
- Implemented direct HTTP approach for issue transitions for better compatibility

## [0.1.14] - 2025-03-05

### Fixed
- Changed `md2conf` dependency to `markdown-to-confluence`

## [0.1.13] - 2025-03-05

### Fixed
- Added missing `md2conf` dependency to fix ModuleNotFoundError

## [0.1.12] - 2025-03-04

### Added
- Added Confluence page creation and update capabilities with markdown-to-confluence support
- Enhanced resource and tool descriptions with more context and examples

## [0.1.11] - 2025-03-03

### Added
- Added support for setting and updating assignee in Jira issues
- Added Jira comment functionality and enhanced get_issue with comment support
- Enhanced resource filtering to focus on user-contributed content

## [0.1.10] - 2025-02-22

### Added
- Added CLI support with click for configurable server initialization
- Support environment variable loading from .env file
- Implement flexible configuration via command-line options

## [0.1.9] - 2025-02-21

### Added
- Added GitHub Actions workflow for linting
- Added comprehensive test coverage for Confluence and Jira services
- Added new Jira tools: create_issue, update_issue, delete_issue
- Added Cursor IDE configuration documentation

### Changed
- Enhanced Jira issue management methods with improved error handling
- Updated installation instructions with detailed configuration examples

### Fixed
- Fixed URL generation in Confluence methods by removing '/wiki' prefix
- Improved environment variable handling in configuration

## [0.1.8] - 2025-02-16

### Added
- Added Docker support with multi-stage build
- Added Smithery configuration for deployment

### Fixed
- Fixed Jira date parsing for various timezone formats
- Fixed document types import error
- Updated logging configuration

## [0.1.7] - 2024-12-20

### Changed
- Optimized Confluence search performance by removing individual page fetching
- Updated search results format to use pre-generated excerpts

## [0.1.6] - 2025-12-19

### Changed
- Lowered minimum Python version requirement from 3.13 to 3.10 for broader compatibility

## [0.1.5] - 2024-12-19

### Fixed
- Aligned comment metadata keys in Confluence comments endpoint
- Fixed handling of nested structure in Confluence spaces response
- Updated README.md with improved documentation

## [0.1.0] - 2024-12-04
