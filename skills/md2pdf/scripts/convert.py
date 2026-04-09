#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["markdown", "pygments", "websocket-client"]
# ///
"""
Markdown to PDF converter using Chrome headless rendering.

Usage:
    convert.py input.md                    # Output to input.pdf
    convert.py input.md -o output.pdf      # Specify output path
    convert.py input.md --theme minimal    # Use minimal theme
    convert.py --list-themes               # List available themes
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter

# Chrome path on macOS
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Available themes
THEMES = {
    "default": "default",
    "minimal": "minimal",
    "academic": "academic",
}


def get_syntax_highlighting_css() -> str:
    """Get Pygments CSS for syntax highlighting (GitHub-like light theme)."""
    formatter = HtmlFormatter(style="github-dark")
    base_css = formatter.get_style_defs(".codehilite")

    # Override with GitHub light colors for print
    github_light_overrides = """
/* GitHub Light Syntax Highlighting */
.codehilite {
    background: #f6f8fa;
    border-radius: 6px;
    padding: 16px;
    overflow-x: auto;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', 'Monaco', monospace;
    font-size: 13px;
    line-height: 1.45;
    margin: 1em 0;
}
.codehilite pre {
    margin: 0;
    padding: 0;
    background: transparent;
}
.codehilite .hll { background-color: #ffffcc }
.codehilite .c { color: #6a737d; font-style: italic } /* Comment */
.codehilite .err { color: #a61717; background-color: #e3d2d2 } /* Error */
.codehilite .k { color: #d73a49; font-weight: bold } /* Keyword */
.codehilite .o { color: #d73a49 } /* Operator */
.codehilite .ch { color: #6a737d; font-style: italic } /* Comment.Hashbang */
.codehilite .cm { color: #6a737d; font-style: italic } /* Comment.Multiline */
.codehilite .cp { color: #6a737d; font-weight: bold } /* Comment.Preproc */
.codehilite .cpf { color: #6a737d; font-style: italic } /* Comment.PreprocFile */
.codehilite .c1 { color: #6a737d; font-style: italic } /* Comment.Single */
.codehilite .cs { color: #6a737d; font-weight: bold; font-style: italic } /* Comment.Special */
.codehilite .gd { color: #b31d28; background-color: #ffeef0 } /* Generic.Deleted */
.codehilite .ge { font-style: italic } /* Generic.Emph */
.codehilite .gr { color: #b31d28 } /* Generic.Error */
.codehilite .gh { color: #005cc5; font-weight: bold } /* Generic.Heading */
.codehilite .gi { color: #22863a; background-color: #f0fff4 } /* Generic.Inserted */
.codehilite .go { color: #24292e } /* Generic.Output */
.codehilite .gp { color: #6a737d; font-weight: bold } /* Generic.Prompt */
.codehilite .gs { font-weight: bold } /* Generic.Strong */
.codehilite .gu { color: #6a737d; font-weight: bold } /* Generic.Subheading */
.codehilite .gt { color: #b31d28 } /* Generic.Traceback */
.codehilite .kc { color: #d73a49; font-weight: bold } /* Keyword.Constant */
.codehilite .kd { color: #d73a49; font-weight: bold } /* Keyword.Declaration */
.codehilite .kn { color: #d73a49; font-weight: bold } /* Keyword.Namespace */
.codehilite .kp { color: #d73a49 } /* Keyword.Pseudo */
.codehilite .kr { color: #d73a49; font-weight: bold } /* Keyword.Reserved */
.codehilite .kt { color: #d73a49 } /* Keyword.Type */
.codehilite .m { color: #005cc5 } /* Literal.Number */
.codehilite .s { color: #032f62 } /* Literal.String */
.codehilite .na { color: #6f42c1 } /* Name.Attribute */
.codehilite .nb { color: #005cc5 } /* Name.Builtin */
.codehilite .nc { color: #6f42c1; font-weight: bold } /* Name.Class */
.codehilite .no { color: #005cc5 } /* Name.Constant */
.codehilite .nd { color: #6f42c1 } /* Name.Decorator */
.codehilite .ni { color: #24292e } /* Name.Entity */
.codehilite .ne { color: #d73a49; font-weight: bold } /* Name.Exception */
.codehilite .nf { color: #6f42c1; font-weight: bold } /* Name.Function */
.codehilite .nl { color: #6f42c1 } /* Name.Label */
.codehilite .nn { color: #6f42c1 } /* Name.Namespace */
.codehilite .nt { color: #22863a } /* Name.Tag */
.codehilite .nv { color: #e36209 } /* Name.Variable */
.codehilite .ow { color: #d73a49; font-weight: bold } /* Operator.Word */
.codehilite .w { color: #bbbbbb } /* Text.Whitespace */
.codehilite .mb { color: #005cc5 } /* Literal.Number.Bin */
.codehilite .mf { color: #005cc5 } /* Literal.Number.Float */
.codehilite .mh { color: #005cc5 } /* Literal.Number.Hex */
.codehilite .mi { color: #005cc5 } /* Literal.Number.Integer */
.codehilite .mo { color: #005cc5 } /* Literal.Number.Oct */
.codehilite .sa { color: #032f62 } /* Literal.String.Affix */
.codehilite .sb { color: #032f62 } /* Literal.String.Backtick */
.codehilite .sc { color: #032f62 } /* Literal.String.Char */
.codehilite .dl { color: #032f62 } /* Literal.String.Delimiter */
.codehilite .sd { color: #6a737d; font-style: italic } /* Literal.String.Doc */
.codehilite .s2 { color: #032f62 } /* Literal.String.Double */
.codehilite .se { color: #032f62 } /* Literal.String.Escape */
.codehilite .sh { color: #032f62 } /* Literal.String.Heredoc */
.codehilite .si { color: #005cc5 } /* Literal.String.Interpol */
.codehilite .sx { color: #032f62 } /* Literal.String.Other */
.codehilite .sr { color: #032f62 } /* Literal.String.Regex */
.codehilite .s1 { color: #032f62 } /* Literal.String.Single */
.codehilite .ss { color: #005cc5 } /* Literal.String.Symbol */
.codehilite .bp { color: #005cc5 } /* Name.Builtin.Pseudo */
.codehilite .fm { color: #6f42c1; font-weight: bold } /* Name.Function.Magic */
.codehilite .il { color: #005cc5 } /* Literal.Number.Integer.Long */
.codehilite .vc { color: #e36209 } /* Name.Variable.Class */
.codehilite .vg { color: #e36209 } /* Name.Variable.Global */
.codehilite .vi { color: #e36209 } /* Name.Variable.Instance */
.codehilite .vm { color: #e36209 } /* Name.Variable.Magic */
"""
    return github_light_overrides


def get_base_css(theme: str = "default") -> str:
    """Get base CSS for the HTML document."""

    if theme == "minimal":
        return """
/* Minimal Theme */
* {
    box-sizing: border-box;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.6;
    color: #333;
    max-width: 800px;
    margin: 0 auto;
    padding: 40px;
}
h1, h2, h3, h4, h5, h6 {
    margin-top: 24px;
    margin-bottom: 16px;
    font-weight: 600;
    line-height: 1.25;
}
h1 { font-size: 2em; }
h2 { font-size: 1.5em; }
h3 { font-size: 1.25em; }
p { margin: 0 0 16px; }
a { color: #0366d6; text-decoration: none; }
a:hover { text-decoration: underline; }
code {
    font-family: 'SF Mono', Consolas, monospace;
    font-size: 85%;
    background: #f6f8fa;
    padding: 0.2em 0.4em;
    border-radius: 3px;
}
pre { margin: 16px 0; }
pre code { padding: 0; background: transparent; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
}
th, td {
    border: 1px solid #dfe2e5;
    padding: 8px 12px;
    text-align: left;
}
th { background: #f6f8fa; }
blockquote {
    margin: 16px 0;
    padding: 0 16px;
    border-left: 4px solid #dfe2e5;
    color: #6a737d;
}
img { max-width: 100%; }
hr { border: none; border-top: 1px solid #dfe2e5; margin: 24px 0; }
ul, ol { padding-left: 2em; margin: 0 0 16px; }
li { margin: 4px 0; }
.page-break { page-break-after: always; }
@media print {
    body { padding: 0; }
    pre, blockquote, table, img { page-break-inside: avoid; }
}
"""

    elif theme == "academic":
        return """
/* Academic Theme */
* {
    box-sizing: border-box;
}
body {
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 12pt;
    line-height: 1.8;
    color: #1a1a1a;
    max-width: 700px;
    margin: 0 auto;
    padding: 60px 40px;
}
h1, h2, h3, h4, h5, h6 {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    margin-top: 32px;
    margin-bottom: 16px;
    font-weight: 600;
    line-height: 1.3;
}
h1 {
    font-size: 24pt;
    text-align: center;
    margin-bottom: 24px;
}
h2 {
    font-size: 16pt;
    border-bottom: 1px solid #ccc;
    padding-bottom: 8px;
}
h3 { font-size: 14pt; }
p {
    margin: 0 0 16px;
    text-align: justify;
    hyphens: auto;
}
a { color: #1a1a1a; text-decoration: underline; }
code {
    font-family: 'SF Mono', Consolas, monospace;
    font-size: 10pt;
    background: #f5f5f5;
    padding: 0.2em 0.4em;
    border-radius: 2px;
}
pre { margin: 16px 0; }
pre code { padding: 0; background: transparent; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 20px 0;
    font-size: 11pt;
}
th, td {
    border: 1px solid #333;
    padding: 10px 14px;
    text-align: left;
}
th {
    background: #f5f5f5;
    font-weight: 600;
}
blockquote {
    margin: 20px 40px;
    padding: 0;
    font-style: italic;
    color: #444;
}
img { max-width: 100%; display: block; margin: 20px auto; }
hr { border: none; border-top: 1px solid #333; margin: 32px 0; }
ul, ol { padding-left: 2em; margin: 0 0 16px; }
li { margin: 6px 0; }
.page-break { page-break-after: always; }
@media print {
    body { padding: 0; }
    pre, blockquote, table, img { page-break-inside: avoid; }
    a { color: #1a1a1a; }
}
"""

    else:  # default theme
        return """
/* Default Theme - Clean & Professional */
* {
    box-sizing: border-box;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.6;
    color: #24292f;
    max-width: 900px;
    margin: 0 auto;
    padding: 45px;
    background: #fff;
}

/* Headings */
h1, h2, h3, h4, h5, h6 {
    margin-top: 24px;
    margin-bottom: 16px;
    font-weight: 600;
    line-height: 1.25;
    color: #1f2328;
}
h1 {
    font-size: 2em;
    padding-bottom: 0.3em;
    border-bottom: 1px solid #d0d7de;
}
h2 {
    font-size: 1.5em;
    padding-bottom: 0.3em;
    border-bottom: 1px solid #d0d7de;
}
h3 { font-size: 1.25em; }
h4 { font-size: 1em; }
h5 { font-size: 0.875em; }
h6 { font-size: 0.85em; color: #656d76; }

/* Paragraphs and text */
p {
    margin: 0 0 16px;
}
a {
    color: #0969da;
    text-decoration: none;
}
a:hover {
    text-decoration: underline;
}
strong { font-weight: 600; }

/* Inline code */
code {
    font-family: 'SF Mono', 'Fira Code', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 85%;
    background: rgba(175, 184, 193, 0.2);
    padding: 0.2em 0.4em;
    border-radius: 6px;
}
pre code {
    padding: 0;
    background: transparent;
    font-size: 100%;
}

/* Block code - styled by codehilite */
pre {
    margin: 16px 0;
    overflow: auto;
}

/* Tables */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    overflow: auto;
}
th, td {
    border: 1px solid #d0d7de;
    padding: 10px 14px;
    text-align: left;
}
th {
    background: #f6f8fa;
    font-weight: 600;
}
tr:nth-child(even) {
    background: #f6f8fa;
}

/* Blockquotes */
blockquote {
    margin: 16px 0;
    padding: 0 16px;
    border-left: 4px solid #d0d7de;
    color: #656d76;
}
blockquote > :first-child { margin-top: 0; }
blockquote > :last-child { margin-bottom: 0; }

/* Lists */
ul, ol {
    padding-left: 2em;
    margin: 0 0 16px;
}
li {
    margin: 4px 0;
}
li + li {
    margin-top: 4px;
}
li > p {
    margin-top: 16px;
}
li > ul, li > ol {
    margin-top: 0;
    margin-bottom: 0;
}

/* Task lists */
ul.task-list {
    list-style: none;
    padding-left: 0;
}
.task-list-item {
    padding-left: 1.5em;
    position: relative;
}
.task-list-item input[type="checkbox"] {
    position: absolute;
    left: 0;
    top: 0.3em;
}

/* Images */
img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 16px 0;
}

/* Horizontal rules */
hr {
    border: none;
    border-top: 1px solid #d0d7de;
    margin: 24px 0;
    height: 0;
}

/* Page breaks for PDF */
.page-break {
    page-break-after: always;
}

/* Print styles */
@page {
    margin: 0.75in;
}
@media print {
    body {
        padding: 0;
        font-size: 12pt;
    }
    pre, blockquote, table, img {
        page-break-inside: avoid;
    }
    h1, h2, h3, h4, h5, h6 {
        page-break-after: avoid;
    }
    a {
        color: #0969da;
    }
    /* Ensure syntax highlighting is visible in print */
    .codehilite {
        background: #f6f8fa !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }
}
"""


def convert_markdown_to_html(md_content: str, theme: str = "default") -> str:
    """Convert markdown content to styled HTML."""

    # Configure markdown with extensions
    md = markdown.Markdown(
        extensions=[
            "extra",           # tables, fenced_code, footnotes, etc.
            "codehilite",      # syntax highlighting
            "toc",             # table of contents
            "sane_lists",      # better list handling
            "smarty",          # smart quotes
        ],
        extension_configs={
            "codehilite": {
                "css_class": "codehilite",
                "guess_lang": True,
                "linenums": False,
            }
        }
    )

    # Convert markdown to HTML
    html_body = md.convert(md_content)

    # Get CSS
    base_css = get_base_css(theme)
    syntax_css = get_syntax_highlighting_css()

    # Build full HTML document
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
{base_css}
{syntax_css}
    </style>
</head>
<body>
{html_body}
</body>
</html>
"""
    return html


def html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Convert HTML file to PDF using Chrome headless with CDP via HTTP."""
    import json
    import base64
    import socket
    import time
    import http.client
    import urllib.request

    # Find a free port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()

    # Launch Chrome with remote debugging (no initial URL - use about:blank)
    cmd = [
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-software-rasterizer",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-allow-origins=*",
        "about:blank",
    ]

    chrome_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    try:
        # Wait for Chrome to start
        page_ws_url = None
        for _ in range(30):
            time.sleep(0.5)
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                conn.request("GET", "/json/list")
                resp = conn.getresponse()
                tabs = json.loads(resp.read().decode())
                conn.close()
                for tab in tabs:
                    if tab.get("type") == "page":
                        page_ws_url = tab.get("webSocketDebuggerUrl")
                        break
                if page_ws_url:
                    break
            except Exception:
                continue

        if not page_ws_url:
            print("Error: Could not find Chrome page target", file=sys.stderr)
            # Fall back to CLI
            chrome_proc.terminate()
            chrome_proc.wait()
            return _fallback_pdf(html_path, pdf_path)

        import websocket
        ws = websocket.create_connection(page_ws_url, timeout=30)

        # Navigate to the HTML file
        ws.send(json.dumps({
            "id": 1,
            "method": "Page.navigate",
            "params": {"url": f"file://{html_path}"}
        }))
        # Wait for navigation response
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                break

        # Wait for page to load
        time.sleep(2)

        # Print to PDF with no headers/footers
        ws.send(json.dumps({
            "id": 2,
            "method": "Page.printToPDF",
            "params": {
                "displayHeaderFooter": False,
                "printBackground": True,
                "marginTop": 0.75,
                "marginBottom": 0.75,
                "marginLeft": 0.75,
                "marginRight": 0.75,
                "paperWidth": 8.5,
                "paperHeight": 11,
            }
        }))

        # Read response for printToPDF (skip events)
        while True:
            result = json.loads(ws.recv())
            if result.get("id") == 2:
                break

        ws.close()

        if "result" in result and "data" in result["result"]:
            pdf_data = base64.b64decode(result["result"]["data"])
            pdf_path.write_bytes(pdf_data)
            return True
        else:
            print(f"Error: PDF generation failed: {result}", file=sys.stderr)
            return False

    except ImportError:
        chrome_proc.terminate()
        chrome_proc.wait()
        return _fallback_pdf(html_path, pdf_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False
    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            chrome_proc.kill()


def _fallback_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Fallback PDF generation using CLI flags."""
    cmd = [
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-software-rasterizer",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        f"file://{html_path}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0 or pdf_path.exists()
    except Exception as e:
        print(f"Error running Chrome: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Convert markdown files to beautifully styled PDFs"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Input markdown file"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output PDF file (default: same name as input with .pdf extension)"
    )
    parser.add_argument(
        "--theme",
        choices=list(THEMES.keys()),
        default="default",
        help="CSS theme to use (default: default)"
    )
    parser.add_argument(
        "--list-themes",
        action="store_true",
        help="List available themes and exit"
    )
    parser.add_argument(
        "--keep-html",
        action="store_true",
        help="Keep the intermediate HTML file"
    )

    args = parser.parse_args()

    # List themes
    if args.list_themes:
        print("Available themes:")
        print("  default  - Clean, professional look with GitHub-style code highlighting")
        print("  minimal  - Ultra-clean with minimal styling")
        print("  academic - Serif fonts, suitable for academic papers")
        return 0

    # Validate input
    if not args.input:
        parser.error("Input file is required")

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    # Determine output path
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = input_path.with_suffix(".pdf")

    # Read markdown content
    md_content = input_path.read_text(encoding="utf-8")

    # Convert to HTML
    html_content = convert_markdown_to_html(md_content, args.theme)

    # Write HTML to temp file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".html",
        delete=not args.keep_html,
        encoding="utf-8"
    ) as tmp:
        tmp.write(html_content)
        tmp.flush()
        html_path = Path(tmp.name)

        if args.keep_html:
            html_output = input_path.with_suffix(".html")
            html_path.rename(html_output)
            html_path = html_output
            print(f"HTML saved: {html_path}")

        # Convert HTML to PDF
        if not html_to_pdf(html_path, output_path):
            print("Error: Failed to convert to PDF", file=sys.stderr)
            return 1

    print(f"PDF created: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
