import subprocess
import sys

import pytest

from sooner.build_hosted import ENTRY, bundle, check_allowed

ADDR = {"patient": "agent1p", "matchmaker": "agent1m", "escrow": "agent1e",
        "registry": "agent1r", "clinic_hub": "agent1h"}


@pytest.mark.parametrize("role", list(ENTRY))
def test_bundle_uses_only_allowed_imports(role):
    files = bundle(role, ADDR)
    assert check_allowed(files) == []
    assert "agent.py" in files and "deploy_config.py" in files
    assert not any("from sooner." in s or "import sooner." in s for s in files.values())


@pytest.mark.parametrize("role", list(ENTRY))
def test_bundle_imports_and_builds_an_agent(role, tmp_path):
    for name, src in bundle(role, ADDR).items():
        (tmp_path / name).write_text(src)
    if role == "clinic_template":
        (tmp_path / "clinic_profile.py").write_text('PROFILE_JSON = "{}"\n')
    r = subprocess.run([sys.executable, "-c", "import sys, asyncio; asyncio.set_event_loop(asyncio.new_event_loop()); sys.path.insert(0, '.'); import agent; print(type(agent.agent).__name__)"],
                       cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip().endswith("Agent"), r.stderr[-800:]


def test_registry_embeds_the_clinic_template_without_its_profile():
    reg = bundle("registry", ADDR)["clinic_bundle.py"]
    ns = {}
    exec(reg, ns)
    assert "agent.py" in ns["CLINIC_FILES"] and "clinic_profile.py" not in ns["CLINIC_FILES"]
    assert "agent1m" in ns["CLINIC_CONFIG_MODULE"]


def _module_level_nodes(tree):
    """Walk the module without descending into function or class bodies."""
    import ast
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack += [c for c in ast.iter_child_nodes(node)]


@pytest.mark.parametrize("role", list(ENTRY))
def test_hosted_loader_quirks(role):
    """Found by deploying: Agentverse has no __file__ at import time and rejects try/except imports."""
    import ast
    for name, src in bundle(role, ADDR).items():
        for node in _module_level_nodes(ast.parse(src)):
            assert not (isinstance(node, ast.Name) and node.id == "__file__"), f"{name}: module-level __file__"
            if isinstance(node, ast.Try):
                assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for b in node.body for n in ast.walk(b)), \
                    f"{name}: try/except around an import"
