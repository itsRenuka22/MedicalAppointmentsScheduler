"""Run the clinic, matchmaker and escrow agents in one Bureau (port 8200).
The patient agent runs separately: python -m sooner.agents.patient_agent"""
from uagents import Bureau

from sooner.agents import clinic_agent, escrow_agent, matchmaker_agent
from sooner.core.policy import load_clinics
from sooner.shared import config


def build() -> Bureau:
    config.ensure_event_loop()
    clinics = load_clinics()
    cagents = {cid: clinic_agent.build_agent(c, cancel_interval_s=60) for cid, c in clinics.items()}
    addrs = {cid: a.address for cid, a in cagents.items()}
    mm = matchmaker_agent.build_agent(addrs)
    esc = escrow_agent.build_agent()
    bureau = Bureau(port=config.BUREAU_PORT, endpoint=[config.BUREAU_ENDPOINT])
    for a in [*cagents.values(), mm, esc]:
        bureau.add(a)
    return bureau


if __name__ == "__main__":
    print(config.SYNTHETIC_NOTICE)
    build().run()
