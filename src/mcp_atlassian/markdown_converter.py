import markdown
import html

def markdown_to_confluence_storage(markdown_content):
    """
    Convert Markdown content to Confluence storage format (XHTML)
    
    Args:
        markdown_content: The markdown content to convert
        
    Returns:
        String in Confluence storage format
    """
    # Convert markdown to HTML
    html_content = markdown.markdown(markdown_content, extensions=['tables', 'fenced_code'])
    
    # Wrap the HTML content in CDATA to make it valid for Confluence storage format
    storage_format = f"<ac:structured-macro ac:name=\"html\"><ac:plain-text-body><![CDATA[{html_content}]]></ac:plain-text-body></ac:structured-macro>"
    
    return storage_format
