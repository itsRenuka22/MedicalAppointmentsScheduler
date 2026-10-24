# Sooner

Agent-to-agent marketplace for the soonest medical appointment, built on Fetch.ai uAgents,
Agentverse, the Chat Protocol (ASI:One) and the Agent Payment Protocol.

**All clinics and patients are synthetic and the payment is simulated on testnet. We run every clinic agent ourselves.**

## Layout
`shared/` message contracts, `core/` deterministic logic (slots lock, ranking, policy, escrow),
`agents/` thin uAgents, `cards/` card builders, `bureau.py` local run, `scripts/` registration + demo.

## Run
    pip install -r sooner/requirements.txt
    cp sooner/.env.example .env      # fill in keys; never commit .env
    pytest -q                        # unit + in-process flow tests
    python -m sooner.scripts.demo_scenarios   # happy path, race, failover (no network)
    python -m sooner.bureau                   # all agents locally in one Bureau

## Agents (fill in after `python -m sooner.scripts.register_agents`)
| Agent | Address |
|---|---|
| sooner_patient | _TBD_ |
| sooner_matchmaker | _TBD_ |
| escrow | _TBD_ |
| clinic_downtown / clinic_bayside / clinic_northgate | _TBD_ |

Badges: _add the Innovation Lab and hackathon badges here._
