"""Find async session_scope() blocks that may hold DB connections too long.

Heuristics:
- Block contains an await not directly on the session variable (e.g. not session.execute/rollback/commit/close/flush)
- Block contains calls to known slow/IO functions (asyncio.sleep, LLM clients, http clients, subprocess, etc.)
- Block is long (>15 lines)
"""

import ast
from pathlib import Path

SLOW_NAMES = {
    "sleep",
    "openai",
    "anthropic",
    "chat",
    "complete",
    "generate",
    "stream",
    "httpx",
    "aiohttp",
    "requests",
    "subprocess",
    "to_thread",
    "run_in_executor",
    "webfetch",
    "websearch",
    "task",
    "browser",
    "image",
    "video",
    "mobile",
    "desktop",
    "execute",
    "run_command",
    "docker",
    "playwright",
    "lancedb",
    "chromadb",
    "meilisearch",
}

SESSION_METHODS = {
    "execute",
    "scalar",
    "scalars",
    "commit",
    "rollback",
    "close",
    "flush",
    "refresh",
    "expire",
    "add",
    "delete",
    "merge",
    "get",
}


def is_session_await(node: ast.Await, session_names: set[str]) -> bool:
    """Return True if the await is on a method of the session variable."""
    value = node.value
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Attribute):
            if func.attr in SESSION_METHODS:
                if isinstance(func.value, ast.Name) and func.value.id in session_names:
                    return True
    return False


def iter_awaits(node: ast.AST):
    for child in ast.walk(node):
        if isinstance(child, ast.Await):
            yield child


def iter_calls(node: ast.AST):
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            yield child


def call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def analyze_file(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return

    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncWith, ast.With)):
            continue
        session_names = set()
        for item in node.items:
            ctx = item.context_expr
            # session_scope(), get_db_session(), session_factory(), get_db()
            name = ""
            if isinstance(ctx, ast.Call):
                func = ctx.func
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
            if name in {"session_scope", "get_db_session", "get_db", "sync_session_scope"}:
                if item.optional_vars:
                    var = item.optional_vars
                    if isinstance(var, ast.Name):
                        session_names.add(var.id)
                    elif isinstance(var, ast.Tuple):
                        for elt in var.elts:
                            if isinstance(elt, ast.Name):
                                session_names.add(elt.id)

        if not session_names:
            continue

        body_lines = node.body
        start = body_lines[0].lineno if body_lines else node.lineno
        end = body_lines[-1].end_lineno if body_lines and hasattr(body_lines[-1], "end_lineno") else node.lineno
        block_len = end - start + 1

        risky_awaits = []
        risky_calls = []
        for aw in iter_awaits(node):
            if not is_session_await(aw, session_names):
                risky_awaits.append(ast.dump(aw)[:120])
        for call in iter_calls(node):
            cname = call_name(call)
            if cname in SLOW_NAMES:
                risky_calls.append(cname)

        if risky_awaits or risky_calls or block_len > 15:
            yield {
                "path": path,
                "lineno": node.lineno,
                "session_names": session_names,
                "block_len": block_len,
                "risky_awaits": risky_awaits,
                "risky_calls": risky_calls,
            }


def main():
    root = Path(__file__).parent.parent / "app"
    results = []
    for path in root.rglob("*.py"):
        if "venv" in path.parts or ".venv" in path.parts:
            continue
        results.extend(analyze_file(path))

    # Sort by risk: many risky awaits/calls first, then block length
    results.sort(key=lambda r: (len(r["risky_awaits"]) + len(r["risky_calls"]), r["block_len"]), reverse=True)

    print(f"Found {len(results)} potentially long-holding session blocks\n")
    for r in results[:60]:
        rel = r["path"].relative_to(root.parent)
        print(
            f"{rel}:{r['lineno']}  block={r['block_len']} lines  "
            f"sessions={r['session_names']}  "
            f"risky_awaits={len(r['risky_awaits'])}  risky_calls={set(r['risky_calls'])}"
        )
        if r["risky_awaits"]:
            for a in r["risky_awaits"][:3]:
                print(f"    await {a}")
        print()


if __name__ == "__main__":
    main()
