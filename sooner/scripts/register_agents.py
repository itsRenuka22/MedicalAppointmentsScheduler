"""Print each agent's address; with AGENTVERSE_API_KEY set, agents connect via mailbox/
Almanac when run (see README). Run this to collect addresses for the README table."""
from sooner.agents import clinic_agent, escrow_agent, matchmaker_agent, patient_agent
from sooner.core.policy import load_clinics
from sooner.shared import config


def main():
    if not config.AGENTVERSE_API_KEY:
        print("warning: AGENTVERSE_API_KEY not set; see .env.example")
    clinics = load_clinics()
    ca = {cid: clinic_agent.build_agent(c) for cid, c in clinics.items()}
    addrs = {cid: a.address for cid, a in ca.items()}
    mm, esc = matchmaker_agent.build_agent(addrs), escrow_agent.build_agent()
    pa = patient_agent.build_agent(mm.address, esc.address, addrs)
    for name, a in [*ca.items(), ("matchmaker", mm), ("escrow", esc), ("patient", pa)]:
        print(f"{name}: {a.address}")


if __name__ == "__main__":
    main()
