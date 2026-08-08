"""
agent.py
This agent is designed to convert files from one format to another.
"""

# Import from agents (openai-agents package installs as 'agents')
from agents import Agent, Runner, SQLiteSession, WebSearchTool, function_tool, ModelSettings
from agents.stream_events import RawResponsesStreamEvent
from agents.tracing import set_tracing_disabled
from openai.types.responses import ResponseTextDeltaEvent

# Import conversion functions directly from scripts.
#
# Two shapes show up here:
#   - Batch converters take no arguments. They process every matching file in
#     input/ and return a summary string.
#   - Single-file converters take a filename (relative to input/) and return a bool.
from combine_files import combine_files
from csv_md import convert_csv_to_markdown
from csv_xlsx import convert_csv_to_xlsx
from docx_pdf import convert_docx_to_pdf
from heic_jpg import convert_heic_to_jpg
from heic_md import convert_heic_to_markdown
from heic_png import convert_heic_to_png
from html_pdf import convert_html_to_pdf
from ipynb_pdf import convert_notebook_to_pdf
from jpg_md import convert_jpg_to_markdown
from jpg_ocr import convert_jpg_to_ocr
from jpg_pdf import convert_jpg_to_pdf
from jpg_png import convert_jpg_to_png
from md_pdf import convert_md_to_pdf
from openai_pdf_md import convert_pdf_to_markdown_openai
from pdf_md import convert_pdf_to_markdown
from pdf_png import convert_pdf_to_png
from png_pdf import convert_png_to_pdf
from pptx_md import convert_pptx_to_markdown
from pptx_pdf import convert_pptx_to_pdf
from R_Rmd import convert_r_to_rmd
from Rmd_pdf import convert_rmd_to_pdf
from sql_pdf import convert_sql_files
from ss_txt import convert_screenshots_to_text
from txt_pdf import convert_txt_to_pdf
from xlsx_csv import convert_xlsx_to_csv

from pathlib import Path
import os
import asyncio

# File reading tool
@function_tool
def read_file(file_path: str) -> str:
    """
    Read the contents of a file from the input folder or absolute path.

    Args:
        file_path: The path to the file. Can be relative to the project directory or an absolute path.

    Returns:
        File content or error message
    """
    script_dir = Path(__file__).parent

    # Handle both relative and absolute paths
    if os.path.isabs(file_path):
        full_path = Path(file_path)
    else:
        full_path = script_dir / file_path

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return f"File content from {file_path}:\n\n{content}"
    except FileNotFoundError:
        return f"Error: File not found at {full_path}"
    except PermissionError:
        return f"Error: Permission denied reading {full_path}"
    except UnicodeDecodeError:
        return f"Error: Could not decode file {full_path} as text. It may be a binary file."
    except Exception as e:
        return f"Error reading {full_path}: {str(e)}"


# Folder listing tool, so the agent can see what it has to work with
@function_tool
def list_files(folder: str = "input") -> str:
    """
    List the files in the input or output folder.

    Args:
        folder: Which folder to list, either "input" or "output". Defaults to "input".

    Returns:
        A newline-separated listing of filenames, or a message if the folder is empty.
    """
    if folder not in ("input", "output"):
        return "Error: folder must be either 'input' or 'output'"

    folder_path = Path(__file__).parent / folder

    if not folder_path.is_dir():
        return f"The {folder} folder does not exist yet"

    # Skip hidden files like .DS_Store
    names = sorted(f.name for f in folder_path.iterdir()
                   if f.is_file() and not f.name.startswith('.'))

    if not names:
        return f"The {folder} folder is empty"

    return f"Files in {folder}/:\n" + "\n".join(names)


# Disable tracing to avoid SSL errors
set_tracing_disabled(True)


agent = Agent(

    # name of the agent, you can name it whatever you want
    name="Converter Agent",

    # model the agent uses, you can use any model you want
    model="gpt-5-nano",

    # tools the agent can use, you can add more tools here, some tools have
    # any tools defined here, also needs to be imported from the agents package
    tools=[

        # regular web search tool, no parameters needed
        WebSearchTool(),

        # File operations
        read_file,   # Already decorated with @function_tool
        list_files,  # Already decorated with @function_tool

        # Batch converters: no arguments, they process everything in input/
        function_tool(convert_csv_to_markdown),
        function_tool(convert_csv_to_xlsx),
        function_tool(convert_xlsx_to_csv),
        function_tool(convert_pdf_to_markdown),
        function_tool(convert_pdf_to_markdown_openai),
        function_tool(convert_pptx_to_markdown),
        function_tool(convert_pptx_to_pdf),
        function_tool(convert_heic_to_jpg),
        function_tool(convert_heic_to_markdown),
        function_tool(convert_heic_to_png),
        function_tool(convert_jpg_to_markdown),
        function_tool(convert_jpg_to_pdf),
        function_tool(convert_jpg_to_ocr),
        function_tool(convert_jpg_to_png),
        function_tool(convert_pdf_to_png),
        function_tool(convert_png_to_pdf),
        function_tool(convert_sql_files),
        function_tool(convert_screenshots_to_text),

        # Single-file converters: take a filename from input/
        function_tool(convert_md_to_pdf),
        function_tool(convert_docx_to_pdf),
        function_tool(convert_txt_to_pdf),
        function_tool(convert_html_to_pdf),
        function_tool(convert_notebook_to_pdf),
        function_tool(convert_r_to_rmd),
        function_tool(convert_rmd_to_pdf),

        # Combines several files into one
        function_tool(combine_files),
        ],



    # controls how the model behaves
    # Note: gpt-5-nano doesn't support temperature parameter
    model_settings=ModelSettings(
        # max_tokens caps the tokens in a single response, used to prevent runaway output.
        # gpt-5-nano is a reasoning model, so its reasoning tokens count against this cap too.
        # Set it high: too low and reasoning eats the whole budget, leaving an empty response.
        max_tokens=16000,

        # tool choice allows you to demand that the agent uses a specific tool
        # "read_file" means the agent will use the read_file tool
        # tool_choice="read_file",

        # tool use behavior controls how tool output is handled
        # "stop_on_first_tool" means the agent will stop after the first tool call
        # tool_use_behavior="stop_on_first_tool",

    ),


    # instructions for the agent, you can change this to whatever you want
    instructions=
    """
    You are an AI Agent that can convert files from one format to another.

    Files live in the 'input' folder and conversions are saved to the 'output' folder.

    File tools:
    - list_files: List what is in the input or output folder
    - read_file: Read the contents of a file
    - web_search: Search the web for information

    Batch converters take NO arguments. Each one converts every matching file in the
    input folder and returns a summary of what it did:
    - convert_csv_to_markdown: CSV -> Markdown tables
    - convert_csv_to_xlsx: CSV -> Excel
    - convert_xlsx_to_csv: Excel -> CSV
    - convert_pdf_to_markdown: PDF -> Markdown (local, free, uses OCR for scanned pages)
    - convert_pdf_to_markdown_openai: PDF -> Markdown via OpenAI Vision (higher quality,
      slower, costs money, needs OPENAI_API_KEY). Only use when asked for the AI version.
    - convert_pptx_to_markdown: PowerPoint -> Markdown
    - convert_pptx_to_pdf: PowerPoint -> PDF (needs LibreOffice)
    - convert_heic_to_jpg: HEIC -> JPG
    - convert_heic_to_markdown: HEIC -> Markdown via OCR
    - convert_jpg_to_markdown: JPG -> Markdown via OCR
    - convert_jpg_to_pdf: JPG -> PDF
    - convert_jpg_to_ocr: JPG -> plain text via OCR
    - convert_png_to_pdf: PNG -> PDF
    - convert_sql_files: SQL -> PDF with syntax highlighting
    - convert_screenshots_to_text: screenshots/images -> one combined text file.
      Pass structured=True for tables or complex layouts.

    Single-file converters take a filename from the input folder, plus an optional
    output filename:
    - convert_md_to_pdf: Markdown -> PDF
    - convert_docx_to_pdf: Word -> PDF
    - convert_txt_to_pdf: Text -> PDF
    - convert_html_to_pdf: HTML -> PDF
    - convert_notebook_to_pdf: Jupyter Notebook -> PDF
    - convert_r_to_rmd: R script -> R Markdown
    - convert_rmd_to_pdf: R Markdown -> PDF
    - combine_files: combine several images, PDFs, or text files into one file

    How to work:
    1. If you are not sure what the user has, call list_files first.
    2. Pick the converter that goes directly from the source format to the target
       format. Do not chain conversions when a direct converter exists.
    3. Report back what the converter returned, including any failures.

    Avoid these chains, they produce bad output:
    - JPG -> PDF -> Markdown. Use convert_jpg_to_markdown instead.
    - Combining images into one image before converting to PDF then Markdown.
      Convert each image to PDF first, then combine the PDFs.
    """,

)




# main function
# this is the main function that will be called to run the agent
async def main():
    # Sessions store conversation history so the agent remembers previous messages
    session = SQLiteSession(session_id="example_session")

    print("Type 'quit' or 'exit' to stop.\n")

    # Interactive loop to ask questions
    while True:
        try:
            # Get user input
            user_input = input(f"{agent.name}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye")
            break

        # Check if user wants to quit
        # if the user inputs 'quit', 'exit', or 'q', the session will end
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Session ended")
            break

        # Skip empty inputs
        if not user_input:
            continue

        # Run the agent with streaming (shows response as it's generated)
        print("\nAgent: ", end="", flush=True)
        result = Runner.run_streamed(agent, user_input, session=session)

        # Stream the response in real-time
        async for event in result.stream_events():
            if isinstance(event, RawResponsesStreamEvent):
                if isinstance(event.data, ResponseTextDeltaEvent):
                    print(event.data.delta, end="", flush=True)

        print("\n")  # Add newline after response



# run the agent
def run_agent():
    """Entry point for console script."""
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print("\nSession ended")


if __name__ == "__main__":
    run_agent()


