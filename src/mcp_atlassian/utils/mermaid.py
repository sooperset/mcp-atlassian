"""Mermaid diagram generation utility."""

import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MermaidError(Exception):
    """Exception raised when Mermaid diagram generation fails."""

    pass


def convert_mermaid_to_png(
    mermaid_text: str, output_filename: Optional[str] = None
) -> str:
    """Convert Mermaid text to PNG diagram.

    Args:
        mermaid_text: The Mermaid diagram syntax as text.
        output_filename: Optional filename for the output PNG (without extension).
                        If not provided, a UUID will be generated.

    Returns:
        The relative path of the generated PNG file (excluding /tmp prefix).

    Raises:
        MermaidError: If the conversion fails.
    """
    # Create the output directory
    output_dir = Path("/attachments/mermaid")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename if not provided
    if output_filename is None:
        output_filename = str(uuid.uuid4())

    # Ensure filename doesn't have extension
    if output_filename.endswith(".png"):
        output_filename = output_filename[:-4]

    # Create temporary input file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mmd", delete=False, encoding="utf-8"
    ) as tmp_file:
        tmp_file.write(mermaid_text)
        input_path = tmp_file.name

    try:
        # Define output path
        output_path = output_dir / f"{output_filename}.png"

        # Run mmdc command
        cmd = ["mmdc", "-p", "/app/puppeteer-config.json", "-i", input_path, "-o", str(output_path)]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=30
        )

        if result.returncode != 0:
            error_msg = f"Mermaid conversion failed: {result.stderr}"
            logger.error(error_msg)
            raise MermaidError(error_msg)

        # Verify the output file was created
        if not output_path.exists():
            error_msg = "Output PNG file was not created"
            logger.error(error_msg)
            raise MermaidError(error_msg)

        logger.info(f"Successfully generated Mermaid diagram: {output_path}")

        # Return relative path (excluding /attachments)
        return str(output_path.relative_to("/attachments"))

    except subprocess.TimeoutExpired:
        error_msg = "Mermaid conversion timed out"
        logger.error(error_msg)
        raise MermaidError(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error during Mermaid conversion: {str(e)}"
        logger.error(error_msg)
        raise MermaidError(error_msg)
    finally:
        # Clean up temporary input file
        try:
            os.unlink(input_path)
        except OSError:
            pass  # Ignore cleanup errors
