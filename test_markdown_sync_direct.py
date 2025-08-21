#!/usr/bin/env python3
"""
Direct test of markdown sync functionality to diagnose issues
without MCP server registration problems.
"""

import logging
import os
import sys
import traceback
from pathlib import Path

# Add the source directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_imports():
    """Test all the critical imports."""
    print("=== Testing Imports ===")
    
    try:
        from mcp_atlassian.confluence.markdown_sync.converter import MarkdownConverter, ParsedMarkdownFile
        print("✓ MarkdownConverter imported successfully")
    except Exception as e:
        print(f"✗ MarkdownConverter import failed: {e}")
        traceback.print_exc()
        return False
    
    try:
        from mcp_atlassian.confluence.markdown_sync.matcher import PageMatcher
        print("✓ PageMatcher imported successfully")
    except Exception as e:
        print(f"✗ PageMatcher import failed: {e}")
        traceback.print_exc()
        return False
    
    try:
        from mcp_atlassian.confluence.markdown_sync.sync import MarkdownSyncEngine, SyncMode, ConflictStrategy
        print("✓ MarkdownSyncEngine imported successfully")
    except Exception as e:
        print(f"✗ MarkdownSyncEngine import failed: {e}")
        traceback.print_exc()
        return False
    
    try:
        from mcp_atlassian.confluence.pages import PagesMixin
        print("✓ PagesMixin imported successfully")
    except Exception as e:
        print(f"✗ PagesMixin import failed: {e}")
        traceback.print_exc()
        return False
    
    try:
        from mcp_atlassian.confluence.config import ConfluenceConfig
        print("✓ ConfluenceConfig imported successfully")
    except Exception as e:
        print(f"✗ ConfluenceConfig import failed: {e}")
        traceback.print_exc()
        return False
    
    try:
        from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor
        print("✓ ConfluencePreprocessor imported successfully")
    except Exception as e:
        print(f"✗ ConfluencePreprocessor import failed: {e}")
        traceback.print_exc()
        return False
    
    return True

def test_converter():
    """Test the markdown converter functionality."""
    print("\n=== Testing MarkdownConverter ===")
    
    try:
        from mcp_atlassian.confluence.markdown_sync.converter import MarkdownConverter
        
        # Test converter initialization
        converter = MarkdownConverter()
        print("✓ MarkdownConverter initialized successfully")
        
        # Test preprocessing dependency
        try:
            # Check if the method exists
            method = getattr(converter.preprocessor, 'markdown_to_confluence_storage', None)
            if method:
                print("✓ ConfluencePreprocessor.markdown_to_confluence_storage method exists")
            else:
                print("✗ ConfluencePreprocessor.markdown_to_confluence_storage method missing")
                # List available methods
                methods = [m for m in dir(converter.preprocessor) if not m.startswith('_')]
                print(f"  Available methods: {methods}")
                return False
        except Exception as e:
            print(f"✗ Error checking preprocessor method: {e}")
            return False
        
        # Test parsing test file
        test_file_path = "../async_iris/test_confluence_sync.md"
        if os.path.exists(test_file_path):
            try:
                parsed = converter.parse_markdown_file(test_file_path)
                print(f"✓ Successfully parsed test file: {parsed.title}")
                print(f"  Content hash: {parsed.content_hash}")
                print(f"  Frontmatter: {parsed.frontmatter}")
            except Exception as e:
                print(f"✗ Failed to parse test file: {e}")
                traceback.print_exc()
                return False
        else:
            print(f"ℹ Test file not found at {test_file_path}, skipping parse test")
        
        return True
        
    except Exception as e:
        print(f"✗ MarkdownConverter test failed: {e}")
        traceback.print_exc()
        return False

def test_client_methods():
    """Test if required client methods exist."""
    print("\n=== Testing Client Methods ===")
    
    try:
        from mcp_atlassian.confluence.pages import PagesMixin
        from mcp_atlassian.confluence.config import ConfluenceConfig
        
        # Try to create a config (this should work even without real credentials)
        try:
            config = ConfluenceConfig(
                url="https://example.atlassian.net/wiki",
                pat_token="dummy_token"
            )
            print("✓ ConfluenceConfig created successfully")
        except Exception as e:
            print(f"✗ ConfluenceConfig creation failed: {e}")
            return False
        
        # Create client instance
        try:
            client = PagesMixin(config)
            print("✓ PagesMixin client created successfully")
        except Exception as e:
            print(f"✗ PagesMixin client creation failed: {e}")
            traceback.print_exc()
            return False
        
        # Check required methods exist
        required_methods = [
            'get_space_pages',
            'get_page_content', 
            'create_page',
            'update_page'
        ]
        
        for method_name in required_methods:
            if hasattr(client, method_name):
                print(f"✓ Method {method_name} exists")
            else:
                print(f"✗ Method {method_name} missing")
                # List available methods
                methods = [m for m in dir(client) if not m.startswith('_') and callable(getattr(client, m))]
                print(f"  Available methods: {methods}")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ Client methods test failed: {e}")
        traceback.print_exc()
        return False

def test_sync_engine():
    """Test sync engine initialization."""
    print("\n=== Testing MarkdownSyncEngine ===")
    
    try:
        from mcp_atlassian.confluence.markdown_sync.sync import MarkdownSyncEngine, SyncMode, ConflictStrategy
        from mcp_atlassian.confluence.pages import PagesMixin
        from mcp_atlassian.confluence.config import ConfluenceConfig
        
        # Create mock client
        config = ConfluenceConfig(
            url="https://example.atlassian.net/wiki",
            pat_token="dummy_token"
        )
        client = PagesMixin(config)
        
        # Test sync engine initialization
        try:
            sync_engine = MarkdownSyncEngine(client)
            print("✓ MarkdownSyncEngine initialized successfully")
        except Exception as e:
            print(f"✗ MarkdownSyncEngine initialization failed: {e}")
            traceback.print_exc()
            return False
        
        # Test enum values
        try:
            sync_mode = SyncMode("auto")
            conflict_strategy = ConflictStrategy("prompt")
            print("✓ Enum conversions work correctly")
        except Exception as e:
            print(f"✗ Enum conversion failed: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ MarkdownSyncEngine test failed: {e}")
        traceback.print_exc()
        return False

def test_path_issues():
    """Test for hardcoded path issues."""
    print("\n=== Testing Path Issues ===")
    
    try:
        # Read the tools.py file and check for hardcoded paths
        tools_file = "src/mcp_atlassian/confluence/markdown_sync/tools.py"
        if os.path.exists(tools_file):
            with open(tools_file, 'r') as f:
                content = f.read()
            
            # Check for hardcoded async_iris paths
            if '/Users/tdyar/ws/async_iris' in content:
                print("✗ Found hardcoded async_iris paths in tools.py")
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if '/Users/tdyar/ws/async_iris' in line:
                        print(f"  Line {i}: {line.strip()}")
                return False
            else:
                print("✓ No hardcoded async_iris paths found in tools.py")
        
        # Test current working directory
        current_dir = os.getcwd()
        expected_dir = "/Users/tdyar/ws/mcp-atlassian"
        if current_dir == expected_dir:
            print(f"✓ Working directory is correct: {current_dir}")
        else:
            print(f"ℹ Working directory: {current_dir} (expected: {expected_dir})")
        
        # Test test file accessibility
        test_file_paths = [
            "../async_iris/test_confluence_sync.md",
            "/Users/tdyar/ws/async_iris/test_confluence_sync.md"
        ]
        
        for path in test_file_paths:
            if os.path.exists(path):
                print(f"✓ Test file accessible at: {path}")
                return True
        
        print("ℹ Test file not found at any expected location")
        return True
        
    except Exception as e:
        print(f"✗ Path issues test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("Starting comprehensive markdown sync diagnosis...\n")
    
    tests = [
        ("Imports", test_imports),
        ("Converter", test_converter),
        ("Client Methods", test_client_methods),
        ("Sync Engine", test_sync_engine),
        ("Path Issues", test_path_issues)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"✗ {test_name} test crashed: {e}")
            traceback.print_exc()
            results.append((test_name, False))
    
    print("\n=== SUMMARY ===")
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed - markdown sync should work correctly!")
    else:
        print("🚨 Issues found - markdown sync operations will likely fail")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)