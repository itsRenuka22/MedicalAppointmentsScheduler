"""Bundle each hosted agent into the multi-file form Agentverse accepts: the entry point becomes
agent.py and every sooner.* module it needs is inlined as a flat sooner_<name>.py file."""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = {"patient": "hosted/patient.py", "matchmaker": "hosted/matchmaker.py",
         "escrow": "hosted/escrow.py", "registry": "hosted/registry.py",
         "clinic_hub": "hosted/clinic_hub.py", "clinic_template": "hosted/clinic_template.py"}
README = {"patient": "patient", "matchmaker": "matchmaker", "escrow": "escrow", "registry": "registry",
          "clinic_hub": "clinic_hub", "clinic_template": "clinic"}
# Imports Agentverse allows (docs: Allowed Imports). Anything else in a bundle is a build error.
ALLOWED = {"uagents", "uagents_core", "pydantic", "requests"}  # plus the standard library
LOCAL = {"deploy_config", "clinic_profile", "clinic_bundle"}  # generated at deploy time


def _module_file(dotted: str):
    p = ROOT.joinpath(*dotted.split(".")[1:])
    return p.with_suffix(".py") if p.with_suffix(".py").exists() else None


def _deps(path: Path) -> set[Path]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("sooner"):
            f = _module_file(node.module)
            if f is not None and f.name != "__init__.py":
                out.add(f)
            for alias in node.names:
                sub = _module_file(f"{node.module}.{alias.name}")
                if sub is not None:
                    out.add(sub)
    return out


def _flat(src: str) -> str:
    def multi(m):
        ind, pkg, names = m.group(1), m.group(2), m.group(3)
        lines = []
        for n in [x.strip() for x in names.split(",")]:
            mod, _, alias = n.partition(" as ")
            lines.append(f"{ind}import sooner_{mod.strip()} as {(alias or mod).strip()}")
        return "\n".join(lines)
    src = re.sub(r"^([ \t]*)from sooner\.\w+\.(\w+) import", r"\1from sooner_\2 import", src, flags=re.M)
    src = re.sub(r"^([ \t]*)from sooner\.(\w+) import ([\w, ]+?)[ \t]*(?:#.*)?$", multi, src, flags=re.M)
    return src


def imported_roots(src: str) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def bundle(role: str, addresses: dict, max_dedicated: int = 2) -> dict[str, str]:
    entry = ROOT / ENTRY[role]
    seen, todo = {}, [entry]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen[f] = f.read_text()
        todo += list(_deps(f))
    files, names = {"agent.py": _flat(seen.pop(entry))}, {}
    for f, src in seen.items():
        name = f"sooner_{f.stem}.py"
        if name in files:
            raise ValueError(f"module name collision: {name}")
        files[name] = _flat(src)
    files["deploy_config.py"] = (f"ADDRESSES = {json.dumps(addresses, indent=2)}\n"
                                 f"MAX_DEDICATED_CLINIC_AGENTS = {int(max_dedicated)}\n")
    if role == "registry":
        files["clinic_bundle.py"] = clinic_bundle_module(addresses)
    return files


def readme(role: str) -> str:
    return (ROOT / "hosted" / "readmes" / f"{README[role]}.md").read_text()


def clinic_bundle_module(addresses: dict) -> str:
    """Registry-side copy of the clinic template, used to create dedicated clinic agents."""
    files = bundle("clinic_template", addresses)
    cfg = files.pop("deploy_config.py")
    return (f"CLINIC_FILES = {files!r}\nCLINIC_CONFIG_MODULE = {cfg!r}\n"
            f"CLINIC_README = {readme('clinic_template')!r}\n")


def check_allowed(files: dict[str, str]) -> list[str]:
    """Returns offending imports (empty means the bundle only uses allowed/local modules)."""
    local = {n[:-3] for n in files} | LOCAL
    bad = []
    for name, src in files.items():
        for r in imported_roots(src):
            if r not in ALLOWED and r not in local and r not in sys.stdlib_module_names:
                bad.append(f"{name}: {r}")
    return bad
