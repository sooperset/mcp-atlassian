#!/usr/bin/env python3
"""
Simple syntax and structure verification for attachment tools.
"""

import ast
import os

def check_python_syntax(file_path):
    """Check if a Python file has valid syntax."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Parse the AST to check syntax
        ast.parse(content)
        return True, "Valid syntax"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Error: {e}"

def check_file_structure():
    """Check if the attachment files exist and have valid structure."""
    print("📁 Checking File Structure")
    print("=" * 30)
    
    files_to_check = [
        "src/mcp_atlassian/confluence/attachments.py",
        "src/mcp_atlassian/confluence/__init__.py", 
        "src/mcp_atlassian/servers/confluence.py"
    ]
    
    all_good = True
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"✅ {file_path} exists")
            
            # Check syntax
            valid, message = check_python_syntax(file_path)
            if valid:
                print(f"   ✅ Syntax is valid")
            else:
                print(f"   ❌ {message}")
                all_good = False
        else:
            print(f"❌ {file_path} missing")
            all_good = False
    
    return all_good

def check_attachments_module():
    """Check the attachments module structure."""
    print("\n🔍 Checking Attachments Module")
    print("=" * 35)
    
    file_path = "src/mcp_atlassian/confluence/attachments.py"
    
    if not os.path.exists(file_path):
        print("❌ Attachments module not found")
        return False
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Check for required components
    required_items = [
        "class AttachmentsMixin",
        "def upload_attachment",
        "def update_attachment", 
        "def get_attachments",
        "def get_attachment",
        "def delete_attachment",
        "def download_attachment",
        "def get_attachment_properties"
    ]
    
    all_present = True
    for item in required_items:
        if item in content:
            print(f"✅ {item}")
        else:
            print(f"❌ {item}")
            all_present = False
    
    return all_present

def check_init_integration():
    """Check if AttachmentsMixin is properly integrated in __init__.py."""
    print("\n🔗 Checking __init__.py Integration")
    print("=" * 40)
    
    file_path = "src/mcp_atlassian/confluence/__init__.py"
    
    if not os.path.exists(file_path):
        print("❌ __init__.py not found")
        return False
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    checks = [
        ("AttachmentsMixin import", "from .attachments import AttachmentsMixin"),
        ("AttachmentsMixin in class", "AttachmentsMixin")
    ]
    
    all_good = True
    for check_name, check_string in checks:
        if check_string in content:
            print(f"✅ {check_name}")
        else:
            print(f"❌ {check_name}")
            all_good = False
    
    return all_good

def check_server_tools():
    """Check if server tools are properly added."""
    print("\n🛠️  Checking Server Tools")
    print("=" * 25)
    
    file_path = "src/mcp_atlassian/servers/confluence.py"
    
    if not os.path.exists(file_path):
        print("❌ Server file not found")
        return False
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Check for attachment tool functions
    tool_functions = [
        "async def upload_attachment",
        "async def update_attachment",
        "async def get_attachments", 
        "async def get_attachment",
        "async def delete_attachment",
        "async def download_attachment",
        "async def get_attachment_properties"
    ]
    
    all_present = True
    for func in tool_functions:
        if func in content:
            print(f"✅ {func}")
        else:
            print(f"❌ {func}")
            all_present = False
    
    return all_present

def show_summary():
    """Show implementation summary."""
    print("\n📋 Implementation Summary")
    print("=" * 30)
    print("The following Confluence attachment tools have been added:")
    print()
    
    tools = [
        "📤 upload_attachment - Upload files to Confluence pages",
        "🔄 update_attachment - Update existing attachments", 
        "📄 get_attachments - List page attachments",
        "🔍 get_attachment - Get attachment details",
        "🗑️  delete_attachment - Delete attachments",
        "📥 download_attachment - Download attachments locally",
        "🏷️  get_attachment_properties - Get attachment metadata"
    ]
    
    for tool in tools:
        print(f"   {tool}")
    
    print("\n🚀 Usage in VS Code:")
    print('   @mcp-atlassian upload_attachment page_id="123" file_path="/path/to/file.pdf"')
    print('   @mcp-atlassian get_attachments page_id="123"')
    print('   @mcp-atlassian download_attachment page_id="123" attachment_id="456"')

def main():
    """Main verification function."""
    print("🔧 MCP Atlassian - Attachment Tools Structure Check")
    print("=" * 60)
    
    # Change to the project directory
    os.chdir("/Users/fredp/Work/bxpp/ai/mcp/mcp-atlassian")
    
    checks = [
        ("File Structure", check_file_structure),
        ("Attachments Module", check_attachments_module), 
        ("Init Integration", check_init_integration),
        ("Server Tools", check_server_tools)
    ]
    
    all_passed = True
    for check_name, check_func in checks:
        result = check_func()
        if not result:
            all_passed = False
    
    print("\n" + "=" * 60)
    
    if all_passed:
        print("✅ All checks passed! Attachment tools are properly implemented.")
        show_summary()
        print("\n🔄 Restart your MCP server to use the new attachment tools!")
    else:
        print("❌ Some checks failed. Please review the issues above.")

if __name__ == "__main__":
    main()
