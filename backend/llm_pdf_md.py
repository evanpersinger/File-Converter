"""Convert PDFs in input/ to Markdown in output/ using an LLM. Slower than pdf_md.py, costs money.

OpenAI path needs OPENAI_API_KEY, Claude path needs ANTHROPIC_API_KEY (env or .env).
"""

import base64
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Define input and output directories relative to this script
script_dir = Path(__file__).resolve().parent
input_dir = script_dir / "input"   # Folder containing PDF files to convert
output_dir = script_dir / "output"  # Folder where converted markdown files will be saved

OPENAI_MODEL = "gpt-4o-mini"
ANTHROPIC_MODEL = "claude-sonnet-5"

_MARKDOWN_PROMPT = (
    "Convert this PDF to Markdown. Reproduce the text faithfully and completely, do not "
    "summarize or paraphrase. Keep headings, lists, and emphasis. Render tables as "
    "Markdown tables and equations as LaTeX. Separate pages with a blank line. Output "
    "only the Markdown, with no preamble or commentary."
)


# OpenAI (via vision-parse)
def convert_with_retry(parser, pdf_path, max_retries=3, retry_delay=5):
    """Convert PDF with retry logic for connection errors"""
    for attempt in range(max_retries):
        try:
            # Convert PDF to markdown (returns list of pages)
            pages = parser.convert_pdf(str(pdf_path))
            return pages
        except Exception as e:
            error_msg = str(e).lower()
            # Check if it's a connection error
            if "connection" in error_msg or "timeout" in error_msg or "network" in error_msg:
                if attempt < max_retries - 1:
                    print(f"Connection error (attempt {attempt + 1}/{max_retries}). Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    raise Exception(f"Connection failed after {max_retries} attempts: {e}")
            else:
                # Not a connection error, don't retry
                raise e
    return None


def _build_parser(api_key: str):
    """Build the VisionParser, falling back to URL mode if base64 is unavailable.

    vision_parse is imported here, not at module scope, because it calls
    nest_asyncio.apply() on import and that raises under uvloop. Keeping it inside this
    function means only the OpenAI path needs `--loop asyncio`, not the whole module.
    """
    from vision_parse import VisionParser

    # Try "base64" mode first as it's more reliable than "url" for local files
    try:
        return VisionParser(
            model_name=OPENAI_MODEL,            # OpenAI model for processing
            api_key=api_key,                    # API key from environment
            temperature=0,                      # Deterministic, faithful extraction (no paraphrasing)
            image_mode="base64",                # Process images as base64 (more reliable than URL)
            detailed_extraction=True,           # Capture tables, equations, and complex layouts
            enable_concurrency=False,           # Disable concurrency to avoid connection issues
        )
    except Exception as e:
        # Fallback to URL mode if base64 doesn't work
        print(f"Warning: Could not initialize with base64 mode, trying URL mode: {e}")
        return VisionParser(
            model_name=OPENAI_MODEL,
            api_key=api_key,
            temperature=0,
            image_mode="url",
            detailed_extraction=True,
            enable_concurrency=False,
        )


# Anthropic (Claude reads the PDF directly)
def _convert_pdf_anthropic(client: anthropic.Anthropic, pdf_path: Path) -> str:
    """Send one PDF to Claude as a document block and return the Markdown it writes back.

    Streams the response so long documents do not hit the HTTP timeout. The SDK already
    retries rate limits, server errors, and dropped connections, so there is no retry
    loop here.
    """
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode("ascii")

    with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=64000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {"type": "text", "text": _MARKDOWN_PROMPT},
            ],
        }],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError("Claude declined to process this PDF")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("output was cut off, the PDF is too long for a single request")

    return "".join(block.text for block in message.content if block.type == "text")


# Shared folder loop
def _convert_all(convert_one: Callable[[Path], str]) -> str:
    """Run convert_one over every PDF in input_dir and write each result to output_dir.

    convert_one takes a PDF path and returns the full Markdown text for that file.
    Returns a summary of what was converted, suitable for showing to a caller.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    entries = list(os.listdir(input_dir)) if input_dir.is_dir() else []
    pdf_names = [n for n in entries if n.lower().endswith(".pdf")]

    # If there are no PDFs but there are Markdown files, say so and stop
    if not pdf_names:
        if any(n.lower().endswith(".md") for n in entries):
            return "That file is already in md format"
        return "No PDF files found in input folder"

    converted = []
    errors = []

    for pdf_name in pdf_names:
        pdf_path = input_dir / pdf_name

        try:
            print(f"Processing {pdf_name}...")
            full_md = convert_one(pdf_path)

            if not full_md:
                print(f"Failed to convert {pdf_name}")
                errors.append(f"{pdf_name}: conversion returned no content")
                continue

            out_md = f"{pdf_path.stem}.md"
            (output_dir / out_md).write_text(full_md, encoding="utf-8")

            print(f"Converted {pdf_name} -> {out_md}")
            converted.append(out_md)

        except Exception as e:
            print(f"Error converting {pdf_name}: {e}")
            print("Tip: If this is an image-based PDF, try converting the original JPG/PNG instead")
            errors.append(f"{pdf_name}: {e}")
            continue

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary


# Public entry points
def convert_pdf_to_markdown_openai() -> str:
    """Convert all PDF files in the input folder to Markdown using OpenAI's Vision API.

    Higher quality than the local pdf_md.py converter, but slower and it costs money.
    Requires OPENAI_API_KEY to be set in the environment or a .env file.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """
    # Check the API key here rather than at import time, so importing this module
    # never kills the calling process.
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Error: OPENAI_API_KEY not found. Please add OPENAI_API_KEY to your .env file"

    parser = _build_parser(api_key)
    return _convert_all(lambda pdf_path: "\n\n".join(convert_with_retry(parser, pdf_path) or []))


def convert_pdf_to_markdown_anthropic() -> str:
    """Convert all PDF files in the input folder to Markdown using Anthropic's Claude.

    Higher quality than the local pdf_md.py converter, but slower and it costs money.
    Requires ANTHROPIC_API_KEY to be set in the environment or a .env file.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "Error: ANTHROPIC_API_KEY not found. Please add ANTHROPIC_API_KEY to your .env file"

    client = anthropic.Anthropic()
    return _convert_all(lambda pdf_path: _convert_pdf_anthropic(client, pdf_path))


if __name__ == "__main__":
    # Usage: python backend/llm_pdf_md.py [openai|anthropic]   (defaults to openai)
    provider = sys.argv[1] if len(sys.argv) > 1 else "openai"
    if provider == "anthropic":
        print(convert_pdf_to_markdown_anthropic())
    else:
        print(convert_pdf_to_markdown_openai())
