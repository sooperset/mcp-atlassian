# Changelog

## [Unreleased]

### Added
- Dynamic Jira field discovery for Epic-related fields
- Enhanced Epic linking with support for different Jira configurations
- Improved Epic issue retrieval using discovered field IDs
- Added specialized Epic field handling when creating Epic issues
- Added proper Jira status transition support with workflow validation
- New tools: jira_get_transitions and jira_transition_issue
- Comprehensive Markdown to Jira markup conversion with support for:
  - Headers (# h1, ## h2, etc.)
  - Formatting (bold with ** or __, italic with * or _)
  - Code blocks with language support (```language)
  - Inline code with backticks
  - Ordered and unordered lists
  - Links, blockquotes, and horizontal rules

### Fixed
- Jira comments now properly convert Markdown syntax to Jira markup format
- This ensures that formatted text (headers, lists, bold, italic, code blocks, etc.) appears correctly in Jira
- Fixed status updates in Jira to respect workflow rules by using transitions
- Added Markdown to Jira markup conversion for issue descriptions in create_issue and update_issue methods
- Fixed literal display of formatting characters (e.g., asterisks) in issue descriptions
- Improved error handling in transition_issue with detailed logging and better error messages
- Implemented direct HTTP approach for issue transitions to ensure compatibility with various Jira configurations
- Enhanced numbered list handling to properly render consecutive items (1., 2., 3., etc.)

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
