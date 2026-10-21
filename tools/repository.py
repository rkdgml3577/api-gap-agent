from pathlib import Path
from sample_service.app import create_app

ROOT = Path(__file__).resolve().parents[1]

def numbered(text):
    return "\n".join(f"{i}: {line}" for i, line in enumerate(text.splitlines(), 1))

def files(variant):
    result = {str(p.relative_to(ROOT)): p.read_text() for p in (ROOT / "sample_service/tests").glob("test_*.py")}
    if variant == "covered":
        result["sample_service/tests/test_boundaries.py"] = (ROOT / "evaluation/complete_tests.py.txt").read_text()
    return result

def list_endpoints():
    spec = create_app().openapi()
    return {"endpoints": [{"method": method.upper(), "path": path, "operation_id": op["operationId"]}
                          for path, methods in spec["paths"].items() for method, op in methods.items()]}

def search_rules(query=""):
    # The fixture is small: return the entire document to avoid retrieval false negatives.
    return {"path": "data/rules/order_rules.md", "query": query,
            "content": numbered((ROOT / "data/rules/order_rules.md").read_text())}

def inspect_schema(operation_id):
    spec = create_app().openapi()
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            if op["operationId"] == operation_id:
                return {"method": method.upper(), "path": path, "operation": op,
                        "schemas": spec.get("components", {}),
                        "fixture": (ROOT / "data/service_context.md").read_text()}
    raise ValueError("unknown operation_id")

def search_tests(variant, query=""):
    # Always list all files, including common tests; a search hit is not proof of coverage.
    return {"files": [{"path": path, "matches": [f"{i}: {line}" for i, line in enumerate(text.splitlines(), 1)
                        if query.lower() in line.lower()][:20]} for path, text in files(variant).items()],
            "note": "Read files to check assertions; names alone do not establish coverage."}

def read_test_file(variant, path):
    allowed = files(variant)
    if path not in allowed:
        raise ValueError("Only listed test files can be read")
    return {"path": path, "content": numbered(allowed[path])}
