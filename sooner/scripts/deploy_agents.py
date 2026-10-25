"""Create/update the hosted Sooner agents through the Agentverse Hosting API.
Idempotent: addresses live in deploy_state.json (gitignored), so a re-run updates code in place.
Usage: python -m sooner.scripts.deploy_agents [--dry-run]"""
import json
import os
import sys
import time
from pathlib import Path

from sooner.build_hosted import bundle, check_allowed, readme
from sooner.scripts.env import load_env
from sooner.shared import config
from sooner.shared.hosting_api import HostingClient, HostingError

STATE = Path(__file__).resolve().parents[1] / "deploy_state.json"
ORDER = ["escrow", "clinic_hub", "registry", "matchmaker", "patient"]  # dependency order
NAMES = {"escrow": "sooner_escrow", "clinic_hub": "sooner_clinic_hub", "registry": "sooner_registry",
         "matchmaker": "sooner_matchmaker", "patient": "sooner_patient"}
FREE_TIER_LIMIT = 8


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2))


def secrets_for(role: str) -> dict:
    wanted = {"registry": ["AGENTVERSE_API_KEY", "ASI1_API_KEY"], "patient": ["ASI1_API_KEY"]}.get(role, [])
    return {k: os.environ[k] for k in wanted if os.environ.get(k)}


def main(dry_run: bool = False) -> dict:
    load_env()
    key = os.environ.get("AGENTVERSE_API_KEY")
    if not key:
        sys.exit("AGENTVERSE_API_KEY is not set (see .env.example)")
    client = HostingClient(key)
    existing = {a["address"] for a in client.list_agents()}
    state = {r: a for r, a in load_state().items() if a in existing}  # drop addresses deleted remotely
    missing = [r for r in ORDER if r not in state]
    print(f"hosted agents on this account: {len(existing)}; to create: {len(missing)}")
    if len(existing) + len(missing) > FREE_TIER_LIMIT:
        sys.exit(f"would exceed the {FREE_TIER_LIMIT}-agent free tier; delete nothing automatically, ask first")
    if dry_run:
        return state
    for role in missing:  # pass 1: identities, so every bundle can embed every address
        state[role] = client.create_agent(NAMES[role])
        save_state(state)
        print(f"created {NAMES[role]} {state[role]}")
    for role in ORDER:  # pass 2: code, secrets, start (dependency order)
        files = bundle(role, state, config.MAX_DEDICATED_CLINIC_AGENTS)
        bad = check_allowed(files)
        if bad:
            sys.exit(f"disallowed imports in {role}: {bad}")
        try:
            client.deploy(NAMES[role], files, secrets_for(role), address=state[role], readme=readme(role))
        except HostingError as e:
            sys.exit(f"deploy failed for {role}: {e}")
        print(f"deployed {NAMES[role]} ({len(files)} files)" +
              (f"  [profile/readme not set: {client.profile_warning}]" if client.profile_warning else ""))
        client.profile_warning = ""
    time.sleep(20)
    for role in ORDER:
        st = client.status(state[role])
        print(f"{NAMES[role]:20} {state[role]}  running={st.get('running')} compiled={st.get('compiled')}")
    return state


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
