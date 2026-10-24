"""Agent seeds, addresses, ports, and timeouts. Real seeds come from the environment."""
import os

OFFER_TIMEOUT_S = float(os.getenv("OFFER_TIMEOUT_S", "8"))
OFFER_TTL_S = 120
RETRIES = 2
RETRY_DELAY_S = 0.2

PORTS = {"patient": 8000, "matchmaker": 8001, "escrow": 8002,
         "clinic_downtown": 8010, "clinic_bayside": 8011, "clinic_northgate": 8012}

CLINIC_IDS = ["clinic_downtown", "clinic_bayside", "clinic_northgate"]


def seed(name: str) -> str:
    return os.getenv(f"{name.upper()}_SEED", f"sooner-dev-seed-{name}")


AGENTVERSE_API_KEY = os.getenv("AGENTVERSE_API_KEY", "")
ASI1_API_KEY = os.getenv("ASI1_API_KEY", "")

# Filled by scripts/register_agents.py output / README; dev falls back to Bureau-local addresses.
AGENT_ADDRESSES: dict[str, str] = {}

SYNTHETIC_NOTICE = "Demo: clinics and patients are synthetic; payments are testnet-simulated."
