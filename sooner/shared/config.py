"""Agent seeds, addresses, ports, and timeouts. Real seeds come from the environment."""
import os

OFFER_TIMEOUT_S = float(os.getenv("OFFER_TIMEOUT_S", "8"))
OFFER_TTL_S = 120
RETRIES = 2
RETRY_DELAY_S = 0.2

PORTS = {"patient": 8100, "matchmaker": 8001, "escrow": 8002,
         "clinic_downtown": 8010, "clinic_bayside": 8011, "clinic_northgate": 8012}

# One of the 8 free-tier hosted agents always stays free for onboarding or redeploys.
MAX_DEDICATED_CLINIC_AGENTS = int(os.getenv("MAX_DEDICATED_CLINIC_AGENTS", "2"))

CLINIC_IDS = ["clinic_downtown", "clinic_bayside", "clinic_northgate"]


def seed(name: str) -> str:
    return os.getenv(f"{name.upper()}_SEED", f"sooner-dev-seed-{name}")


AGENTVERSE_API_KEY = os.getenv("AGENTVERSE_API_KEY", "")
ASI1_API_KEY = os.getenv("ASI1_API_KEY", "")

# Filled by scripts/register_agents.py output / README; dev falls back to Bureau-local addresses.
AGENT_ADDRESSES: dict[str, str] = {}

SYNTHETIC_NOTICE = "Demo: clinics and patients are synthetic; payments are testnet-simulated."

BUREAU_PORT = 8200
BUREAU_ENDPOINT = f"http://127.0.0.1:{BUREAU_PORT}/submit"


def ensure_event_loop():
    """Python 3.12+ no longer creates a default loop; uAgents expects one."""
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def agent_address(name: str) -> str:
    """Deterministic uAgent address for an agent name, derived from its seed."""
    from uagents.crypto import Identity
    return Identity.from_seed(seed(name), 0).address

