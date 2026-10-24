"""Run all agents locally in one Bureau for development."""
from uagents import Bureau

from sooner.agents import clinic_agent, escrow_agent, matchmaker_agent, patient_agent
from sooner.core.policy import load_clinics
from sooner.shared import config


def build() -> Bureau:
    clinics = load_clinics()
    cagents = {cid: clinic_agent.build_agent(c, cancel_interval_s=60) for cid, c in clinics.items()}
    addrs = {cid: a.address for cid, a in cagents.items()}
    mm = matchmaker_agent.build_agent(addrs)
    esc = escrow_agent.build_agent()
    patient = patient_agent.build_agent(mm.address, esc.address, addrs)
    bureau = Bureau(port=8100)
    for a in [*cagents.values(), mm, esc, patient]:
        bureau.add(a)
    return bureau


if __name__ == "__main__":
    print(config.SYNTHETIC_NOTICE)
    build().run()
