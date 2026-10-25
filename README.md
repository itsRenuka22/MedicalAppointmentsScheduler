# Sooner

Agent-to-agent marketplace for the soonest medical appointment, running as **Agentverse hosted agents**
(Fetch.ai uAgents, Chat Protocol for ASI:One, Agent Payment Protocol for the deposit).
Search by chat, book by chat, clinics onboard themselves by chat.

> Demo: clinics and patients are synthetic and the payment is **simulated**. We run every clinic agent ourselves.

## Deployed agents (Agentverse, hosted)
| Agent | Address |
|---|---|
| sooner_escrow | `agent1qdlr0n2wswjcq8k7h0g2y47xu8ymhvxxa9qd2wwm0hq4gqekrz0x55lwfwj` |
| sooner_clinic_hub | `agent1qttpje69zawx0l677ahxamrju88090kymg6vlye9k4g934xuejlgyy4gwma` |
| sooner_registry | `agent1qfj3efxru5pluvslt4987hhwndwmhdaatu7jmasaz5v2kxdketsqztwat4g` |
| sooner_matchmaker | `agent1qw53y0gmlu5zzveage4qjs7herr0qv4esw89h43jjp67vsdhymxa7vejyvw` |
| sooner_patient | `agent1qdcu8vqckkph8smfu0nn9wt4tmknwf2z8ethcex7q3l7qrug463xvgt4cjp` |

Onboarded clinics get their own hosted agent (up to `MAX_DEDICATED_CLINIC_AGENTS`, default 2) or a place on
`sooner_clinic_hub`; their addresses are returned to the clinic in chat.

**Try it in ASI:One:** open [asi1.ai](https://asi1.ai), enable Agents, and message `sooner_patient`
(or open it from Agentverse and use "Chat with Agent"):
1. `I need a dermatologist, Aetna, deposit under $40` -> ranked offers
2. `book 1` (or `book Bayside`) -> booking confirmation, deposit marked (simulated)
3. To onboard a clinic, message `sooner_registry` with `name:`, `address:`, `specialties:`, `insurance:`, `slots:` lines.
   Manage a clinic from its own agent: `add slot 2026-10-28T10:00 150`, `list slots`, `cancel booking <slot_id>`.
   Remove it with `deregister <clinic_id>` to the registry.

## What is real, what is simulated
| Real | Simulated |
|---|---|
| Hosted agents on Agentverse, created/updated through the Hosting API | Clinics, patients, calendars (synthetic seed data) |
| Chat Protocol (ack, then reply) and Agent Payment Protocol handlers | The deposit: an escrow ledger in agent storage, no funds move |
| Compare-and-set slot lock with version numbers, in agent storage | Clinic location: onboarded clinics default to an approximate SF location (no geocoder) |
| Registry-driven discovery, per-agent timeouts, last-known-list fallback | Authentication: clinic owner = the chat address that registered; hub seed clinics have no owner |
| Dedicated clinic agents created at onboarding by the Registry agent | Intake LLM: ASI:One when `ASI1_API_KEY` is set, else a field-per-line regex parser |

## Hosting limits and how the design respects them (free tier)
- **8 agents total**, counting hosted *and* mailbox/registered agents. Core = 5 (patient, matchmaker, escrow,
  registry, clinic hub). Dedicated clinic agents are capped (`MAX_DEDICATED_CLINIC_AGENTS`, default 2); after that,
  or on any creation error (quota, 4xx, 5xx), the clinic is hosted-in-hub and told so. Registration never fails
  because of the limit. `deregister` deletes a dedicated agent to free the slot.
- **~5MB storage / agent, 10K messages, 60K compute-seconds:** no `on_interval`, no logs or histories in storage,
  one query per serving agent (the hub answers for all its clinics at once), clinics that cannot match are never contacted.
  Measured per flow (agent-to-agent messages, in-process model): **search = 6**, **booking = 6**
  (plus ~4 Chat Protocol messages each: user message, ack, reply, ack). About 20 messages per search+book, ~500 flows per quota.
- Hosted loader quirks found by deploying (enforced by tests): no module-level `__file__`, no `try/except` around imports.

## Layout
`shared/` contracts, config, hosting client; `core/` tested logic over a `Store` (in-memory for tests,
`ctx.storage` when hosted): slots, `slotbook` (CAS), `escrow`, `ranking`, `policy`, `clinic_host`, `registry`, `registry_chat`;
`agents/` local uAgents + shared logic; `hosted/` hosted entry points; `build_hosted.py` bundles each agent into the flat
multi-file form Agentverse accepts; `scripts/deploy_agents.py` creates/updates agents (idempotent via gitignored `deploy_state.json`).

## Run
    pip install -r sooner/requirements.txt
    cp sooner/.env.example sooner/.env          # AGENTVERSE_API_KEY, optional ASI1_API_KEY; never commit
    pytest -q                                   # unit + in-process flow tests (hosted model)
    python -m sooner.scripts.deploy_agents      # create/update the hosted agents
    python -m sooner.scripts.e2e_hosted         # live end-to-end check (needs free agent quota: see above)

The original local Bureau flow still works: `python -m sooner.bureau` and `python -m sooner.agents.patient_agent`.
