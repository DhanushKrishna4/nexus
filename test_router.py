"""
Unit tests for the Auto (Smart Routing) heuristics.

The routing decisions and the codegen denylist are pure functions, so they can
be tested without a GPU, Ollama, or Open WebUI. Run either way:

    python3 test_router.py        # standalone: prints PASS/FAIL summary
    pytest test_router.py         # if you have pytest

These guard against the heuristics silently drifting (a misroute sends work to
the wrong model; a denylist gap runs unsafe code).
"""
import importlib.util
import os
import sys
import types


def _load_module():
    """Import the pipe module, stubbing httpx/pydantic if they're not present."""
    if "httpx" not in sys.modules:
        try:
            import httpx  # noqa: F401
        except Exception:
            sys.modules["httpx"] = types.ModuleType("httpx")
    if "pydantic" not in sys.modules:
        try:
            import pydantic  # noqa: F401
        except Exception:
            pm = types.ModuleType("pydantic")
            pm.BaseModel = type("BaseModel", (), {})
            pm.Field = lambda default=None, **k: default
            sys.modules["pydantic"] = pm
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "openwebui_autorouter_function.py")
    spec = importlib.util.spec_from_file_location("autorouter", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load_module()

# --- (text, has_image) -> expected route ----------------------------------- #
ROUTING = [
    ("write a python function to parse a csv",            False, "coding"),
    ("debug this traceback for me",                       False, "coding"),
    ("```\nprint(1)\n```  why does this fail",            False, "coding"),
    ("do a risk analysis of this control loop",           False, "reasoning"),
    ("assess the IEC 62443 gap here",                     False, "reasoning"),
    ("why would a pressure transmitter fail?",            False, "reasoning"),
    ("what's the capital of France",                      False, "fast"),
    ("hello there",                                       False, "fast"),
    ("summarize this in one line",                        False, "fast"),
    ("read this diagram",                                 True,  "vision"),
    # image wins even when the text looks like analysis or code:
    ("analyze this P&ID",                                 True,  "vision"),
    ("write code from this screenshot",                   True,  "vision"),
]

# --- export-format detection ----------------------------------------------- #
EXPORT = [
    ("convert this to excel",            "excel"),
    ("make a powerpoint deck",           "pptx"),
    ("export it as a word document",     "word"),
    ("just answer normally",             None),
]

# --- complex-export (codegen) detection ------------------------------------ #
COMPLEX = [
    ("excel with a bar chart of sales",  True),
    ("add conditional formatting",       True),
    ("make a pivot table",               True),
    ("multiple sheets please",           True),
    ("convert this pdf to excel",        False),
    ("just a plain table to excel",      False),
]

# --- denylist (codegen safety) --------------------------------------------- #
DENY_BLOCK = [
    "import socket",
    "import os\nos.system('rm -rf /')",
    "import requests; requests.get('http://x')",
    "open('/etc/passwd').read()",
    "subprocess.run(['ls'])",
    "eval(user_input)",
]
DENY_ALLOW = [
    "import os\nfrom openpyxl import Workbook\nWorkbook().save(os.environ['OUTPUT_PATH'])",
    "from docx import Document\nd=Document()\nd.save(os.environ['OUTPUT_PATH'])",
    "import matplotlib; matplotlib.use('Agg')",
]


# --- pytest-style tests (also called by the standalone runner) ------------- #
def test_routing():
    for text, img, want in ROUTING:
        got = m._route(text, img)
        assert got == want, f"route({text!r}, img={img}) = {got!r}, want {want!r}"


def test_export_format():
    for text, want in EXPORT:
        got = m._export_format(text)
        assert got == want, f"_export_format({text!r}) = {got!r}, want {want!r}"


def test_complex_export():
    for text, want in COMPLEX:
        got = m._is_complex_export(text)
        assert got == want, f"_is_complex_export({text!r}) = {got}, want {want}"


def test_denylist_blocks():
    for code in DENY_BLOCK:
        assert m._scan_code(code) is not None, f"denylist MISSED: {code!r}"


def test_denylist_allows():
    for code in DENY_ALLOW:
        assert m._scan_code(code) is None, f"denylist false-positive: {code!r}"


def _main():
    tests = [test_routing, test_export_format, test_complex_export,
             test_denylist_blocks, test_denylist_allows]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
    total = len(tests)
    print(f"\n{total - failures}/{total} test groups passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_main())
