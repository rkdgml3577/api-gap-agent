import os
from pathlib import Path
from sample_service.app import create_app

ROOT = Path(__file__).resolve().parents[1]

def expanded():
    # CORPUS=expanded adds out-of-scope distractor rules/tests so retrieval (RAG)
    # has something to retrieve from. Default keeps the small 3-rule corpus.
    return os.getenv("CORPUS", "default").lower() == "expanded"

def use_rag():
    # RETRIEVAL=rag returns only the top-k items relevant to the order scope;
    # default "full" returns the whole corpus (the baseline to compare against).
    return os.getenv("RETRIEVAL", "full").lower() == "rag"

def _rag_sections(text, k):
    # Split a rules doc into "## ..." sections, keep the k most relevant, rejoin.
    from agent.retrieval import top_k, SCOPE_QUERY
    head, _, body = text.partition("## ")
    if not body:
        return text
    sections = {f"s{i}": "## " + s for i, s in enumerate(("## " + body).split("## ")) if s.strip()}
    chosen = set(top_k(SCOPE_QUERY, list(sections.items()), k))
    return head + "\n".join(sec for key, sec in sections.items() if key in chosen)

def _rag_files(result, k):
    from agent.retrieval import top_k, SCOPE_QUERY
    items = list(result.items())
    chosen = set(top_k(SCOPE_QUERY, items, k))
    return {path: content for path, content in result.items() if path in chosen}

def numbered(text):
    return "\n".join(f"{i}: {line}" for i, line in enumerate(text.splitlines(), 1))

def files(variant):
    result = {str(p.relative_to(ROOT)): p.read_text() for p in (ROOT / "sample_service/tests").glob("test_*.py")}
    if variant == "covered":
        result["sample_service/tests/test_boundaries.py"] = (ROOT / "evaluation/complete_tests.py.txt").read_text()
    if expanded():
        for p in sorted((ROOT / "evaluation/expanded/tests").glob("test_*.py")):
            result[str(p.relative_to(ROOT))] = p.read_text()
    if use_rag():
        result = _rag_files(result, int(os.getenv("RAG_K_TESTS", "4")))
    return result

def list_endpoints():
    spec = create_app().openapi()
    return {"endpoints": [{"method": method.upper(), "path": path, "operation_id": op["operationId"]}
                          for path, methods in spec["paths"].items() for method, op in methods.items()]}

def search_rules(variant="healthy", query=""):
    # The fixture is small: return the entire document to avoid retrieval false negatives.
    # The "ambiguous" variant serves a conflicting rules doc to test whether the agent
    # abstains (uncertain) instead of forcing a verdict on an unresolvable rule.
    path = "evaluation/ambiguous_rules.md" if variant == "ambiguous" else "data/rules/order_rules.md"
    text = (ROOT / path).read_text()
    if expanded():
        text += "\n\n" + (ROOT / "evaluation/expanded/rules/distractor_rules.md").read_text()
    if use_rag():
        text = _rag_sections(text, int(os.getenv("RAG_K_RULES", "6")))
    return {"path": path, "query": query, "content": numbered(text)}

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
