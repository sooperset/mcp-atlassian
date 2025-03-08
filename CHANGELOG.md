# Changelog

## [Unreleased]

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
