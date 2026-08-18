"""
Generates OptiView_Standalone.py: the entire app -- every Python module,
every Jinja2 template, and the CSS/JS -- bundled into ONE self-contained
file that runs with `python OptiView_Standalone.py` and needs nothing
alongside it (no app/ folder, no templates/ or static/ directories).
Only the pip-installed dependencies are still required.

Run this whenever anything under app/ changes, to regenerate the
standalone build. Never hand-edit OptiView_Standalone.py directly --
edit the real source under app/ and re-run this script instead.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
OUTPUT = ROOT / "OptiView_Standalone.py"

# Dependency order: each module only ever references names defined in a
# module earlier in this list (verified by hand against the real imports).
MODULE_ORDER = [
    "models.py", "utils.py", "excel_processor.py", "mapping_engine.py",
    "analysis_engine.py", "export_engine.py", "assistant_engine.py", "main.py",
]

# These local aliases/module names are used as `prefix.name(...)` call
# sites in the original package; once flattened into one namespace, the
# prefix must go and the bare name resolves directly.
QUALIFIED_PREFIXES = ["ae", "mapping_engine", "excel_processor", "assistant_engine", "export_engine"]

FUTURE_IMPORT_RE = re.compile(r"^from __future__ import annotations\n?", re.MULTILINE)
APP_IMPORT_RE = re.compile(r"^from app(?:\.\w+)?\s+import\b.*\n?", re.MULTILINE)


def strip_common(src: str) -> str:
    src = FUTURE_IMPORT_RE.sub("", src)
    src = APP_IMPORT_RE.sub("", src)
    return src


def strip_module_prefixes(src: str) -> str:
    for prefix in QUALIFIED_PREFIXES:
        src = re.sub(rf"\b{re.escape(prefix)}\.(?=[A-Za-z_])", "", src)
    return src


def load_module(name: str) -> str:
    src = (APP_DIR / name).read_text(encoding="utf-8")
    src = strip_common(src)

    if name == "excel_processor.py":
        # main.py also defines a module-level `logger` -- rename this
        # one so the two don't collide once concatenated.
        src = re.sub(r"\blogger\b", "excel_logger", src)

    if name in ("main.py", "export_engine.py", "assistant_engine.py"):
        src = strip_module_prefixes(src)

    if name == "main.py":
        src = src.replace('from fastapi.staticfiles import StaticFiles\n', '')
        src = src.replace('from fastapi.templating import Jinja2Templates\n', '')
        src = src.replace(
            'from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse',
            'from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse, Response',
        )
        src = src.replace(
            'BASE_DIR = Path(__file__).resolve().parent\n'
            'UPLOAD_DIR = BASE_DIR.parent / "uploads"\n'
            'UPLOAD_DIR.mkdir(exist_ok=True)\n',
            'import tempfile\n'
            'BASE_DIR = Path(__file__).resolve().parent\n'
            'UPLOAD_DIR = Path(tempfile.gettempdir()) / "optiview_uploads"\n'
            'UPLOAD_DIR.mkdir(exist_ok=True)\n',
        )
        src = src.replace(
            'app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")\n',
            '',
        )
        src = src.replace(
            'templates = Jinja2Templates(directory=BASE_DIR / "templates")',
            'templates = SimpleTemplates(TEMPLATES)',
        )

    return src.strip("\n")


def load_templates() -> dict:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted((APP_DIR / "templates").glob("*.html"))}


SIMPLE_TEMPLATES_CLASS = '''class SimpleTemplates:
    """Minimal stand-in for Starlette's Jinja2Templates, backed by an
    in-memory DictLoader so no templates/ directory is needed on disk."""

    def __init__(self, templates: dict):
        self.env = Environment(loader=DictLoader(templates), autoescape=True)
        self.env.filters["tojson"] = lambda obj, **kw: json.dumps(obj)

    def TemplateResponse(self, name, context, status_code: int = 200):
        html = self.env.get_template(name).render(**context)
        return HTMLResponse(html, status_code=status_code)
'''

STATIC_ROUTES_AND_ENTRYPOINT = '''

@app.get("/static/css/style.css")
async def _static_style_css():
    return Response(content=STYLE_CSS, media_type="text/css")


@app.get("/static/js/app.js")
async def _static_app_js():
    return Response(content=APP_JS, media_type="application/javascript")


if __name__ == "__main__":
    import threading
    import webbrowser
    import uvicorn

    URL = "http://127.0.0.1:8000"

    def _open_browser():
        try:
            webbrowser.open(URL)
        except Exception:
            pass  # headless machine or no default browser -- user can open the URL manually

    threading.Timer(1.25, _open_browser).start()
    print(f"OptiView starting -- opening {URL} in your browser...")
    print("(If it doesn't open automatically, copy that URL into your browser.)")
    print("Press CTRL+C to stop.")
    uvicorn.run(app, host="127.0.0.1", port=8000)
'''


def build() -> str:
    modules = {name: load_module(name) for name in MODULE_ORDER}
    templates = load_templates()
    style_css = (APP_DIR / "static" / "css" / "style.css").read_text(encoding="utf-8")
    app_js = (APP_DIR / "static" / "js" / "app.js").read_text(encoding="utf-8")

    parts = []
    parts.append(
        '"""\n'
        'OptiView -- FTE Location & Workforce Planning Tool (standalone build)\n\n'
        'Self-contained: the entire app -- every route, every HTML template, and\n'
        'the CSS/JS -- is baked into this one file, so it runs with nothing else\n'
        'alongside it, just the pip-installed dependencies below.\n\n'
        'GENERATED FILE -- do not hand-edit. Edit the source under app/ and run\n'
        'build_standalone.py again instead; it regenerates this file from scratch.\n\n'
        'Setup:\n'
        '    pip install fastapi "uvicorn[standard]" pandas openpyxl python-multipart jinja2 xlrd numpy\n'
        'Run:\n'
        '    python OptiView_Standalone.py\n'
        'Then open:\n'
        '    http://127.0.0.1:8000\n'
        '"""\n'
    )
    parts.append("from __future__ import annotations\n")
    parts.append("import json\n")
    parts.append("from jinja2 import Environment, DictLoader\n")
    parts.append(f"TEMPLATES = {templates!r}\n")
    parts.append(f"STYLE_CSS = {style_css!r}\n")
    parts.append(f"APP_JS = {app_js!r}\n")
    parts.append(SIMPLE_TEMPLATES_CLASS)

    for name in MODULE_ORDER:
        parts.append(f"\n# {'=' * 76}\n# --- from app/{name} ---\n# {'=' * 76}\n")
        parts.append(modules[name])
        parts.append("\n")

    parts.append(STATIC_ROUTES_AND_ENTRYPOINT)
    return "".join(parts)


def main():
    content = build()
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
