# **Sooner: Implementation Plan for Claude Code**

A detailed, feature-by-feature build plan for a four-person team: Renuka Patwari, Atharva Mokashi, Prathamesh Sawant, Sarvesh Reshimwale. Pure Fetch.ai, no custom UI, no other sponsors. Each ticket is written so you can paste it to Claude Code as one task.

## **How to use this plan**

* Every ticket has a goal, an interface (its inputs and outputs), acceptance criteria, and test notes. Hand one ticket at a time to Claude Code.  
* Build in tracer-bullet order: get one thin end-to-end path working first, then add depth feature by feature.  
* Design rule: put the hard logic in plain Python modules (the core folder) with small interfaces, and keep the agents thin. Test the core without the agent framework. This keeps the correctness-critical code easy to verify and change.

## **Repo structure**

* sooner/shared/models.py: the message types that every agent imports. This is the shared contract.  
* sooner/shared/config.py: agent seeds, addresses, ports, and timeouts.  
* sooner/core/slots.py: the Slot state machine and the optimistic lock.  
* sooner/core/ranking.py: ranks offers (the sooner score).  
* sooner/core/policy.py: each clinic's match, price, and deposit rules.  
* sooner/core/escrow.py: the escrow state machine (hold, release, refund).  
* sooner/agents/patient\_agent.py, matchmaker\_agent.py, clinic\_agent.py, escrow\_agent.py: thin uAgents that call core.  
* sooner/cards/interactive\_cards.py: ASI1 Interactive Card builders.  
* sooner/data/clinics.json, patients.json: synthetic data, labeled.  
* sooner/bureau.py: run all agents locally in one Bureau for development.  
* sooner/scripts/register\_agents.py: Agentverse registration. demo\_scenarios.py: scripted happy path, race, and failover.  
* sooner/tests/: unit tests for the core modules (slots, ranking, escrow, policy).  
* sooner/README.md: agent names and Agentverse addresses, the Innovation Lab and hackathon badges, and run and test instructions.

## **Message contracts (agree and freeze first, in shared/models.py)**

* SlotRequest: request\_id, specialty, time\_window (start, end), location (lat, lng), radius\_miles, insurance, max\_deposit, patient\_address.  
* SlotOffer: request\_id, clinic\_id, clinic\_name, slot\_id, slot\_time, price, deposit, distance\_miles, expires\_at, clinic\_address.  
* BookingRequest: request\_id, clinic\_id, slot\_id, patient\_address, expected\_version.  
* BookingResult: ok, slot\_id, reason (confirmed, slot\_taken, or expired), confirmation\_id.  
* PaymentIntent and PaymentReceipt: booking\_id, amount, status (held, released, or refunded), tx\_ref.  
* CancellationEvent: clinic\_id, slot\_id, slot\_time, freed\_at.

## **Core modules (deterministic, unit-tested, no agent framework)**

* core/slots.py. A Slot has slot\_id, state (open, held, booked), version, time, price, deposit. Functions: try\_hold(slot, expected\_version) returns (ok, new\_version, reason); confirm(slot); release(slot). The lock is compare-and-set: move open to held only if the version matches, otherwise return slot\_taken. Tests: two holds on one open slot and only one wins; a hold on an already-held slot is rejected; a released slot can be held again.  
* core/ranking.py. rank(offers, request) returns offers sorted by the sooner score: earliest slot\_time first, then shortest distance, then lowest deposit, dropping any offer that breaks a hard constraint (outside the window, over max\_deposit, out of radius, wrong insurance). Tests: ordering is deterministic and stable; violations are dropped.  
* core/policy.py. For a clinic: matches(request) returns a bool; soonest\_slot(request) returns a slot or none; price\_and\_deposit(slot) returns price and deposit. Tests: a clinic with no matching slot returns none; the deposit respects the clinic's policy.  
* core/escrow.py. hold(amount) returns an escrow\_id; release(escrow\_id); refund(escrow\_id). Tests: release and refund are idempotent; you cannot release a refunded escrow.

## **The agents (thin, call core, speak the Chat Protocol)**

* PatientAgent: discoverable in ASI:One. On a user message, parse the intent into a SlotRequest using the ASI:One LLM, send it to the Matchmaker, receive ranked offers, render Interactive Cards, and on the user's card tap send a BookingRequest and then trigger payment. If the offer timeout fires, show whatever arrived.  
* MatchmakerAgent: on a SlotRequest, discover clinic agents on Agentverse by specialty and location, broadcast the request, collect SlotOffers until a timeout (for example 8 seconds), drop late replies, rank with core/ranking, and return the ranked list.  
* ClinicAgent (run three instances with different data): on a SlotRequest, use core/policy to find its soonest matching slot and reply with a SlotOffer. On a BookingRequest, call core/slots.try\_hold with the expected version and reply with a BookingResult. On an interval, free a slot and emit a CancellationEvent.  
* EscrowAgent: on a PaymentIntent, hold the deposit through the Payment Protocol on testnet and reply with a PaymentReceipt. Release on a confirmed booking, refund on a cancellation.

## **Shared foundation (T0, first 30 minutes, everyone together)**

* Write shared/models.py (the six message types above) and shared/config.py. Freeze the fields. Change a field only by a quick group OK.  
* Stand up bureau.py so anyone can run all agents locally with stub agents that just log messages.  
* Create .env.example with the Agentverse and ASI:One keys, and never commit real keys.

## **Renuka Patwari: patient side, ASI:One, cards, and integration lead**

* R1. PatientAgent skeleton, register on Agentverse, make it discoverable in ASI:One. Done when a judge can find and message the agent in ASI:One and get a reply. Blocked by: models.  
* R2. Intent parsing: turn user text into a SlotRequest using the ASI:One LLM. Done when three sample phrasings produce correct structured requests.  
* R3. Offer ranking integration: call core/ranking and present the top offers. Done when offers show soonest first within the constraints. Blocked by: R2, A4.  
* R4. ASI1 Interactive Cards for slot selection, plus the booking-confirm flow on tap. Done when tapping a card books that slot and shows a confirmation in chat. Blocked by: R1, P3.  
* R5. Integration lead: keep the end-to-end path green, own demo\_scenarios.py, and write the three-minute pitch. Ongoing.

## **Atharva Mokashi: the market engine**

* A1. MatchmakerAgent skeleton, register on Agentverse. Blocked by: models.  
* A2. Clinic discovery on Agentverse by specialty and location. Done when it returns the set of clinic agents to query.  
* A3. Broadcast, collect with a timeout, drop late replies, and aggregate partial results. Done when, with one clinic slow or offline, it still returns the others within the timeout. Blocked by: A2, models.  
* A4. Rank and return, calling core/ranking. Done when it returns a ranked SlotOffer list to the patient agent. Blocked by: A3.

## **Prathamesh Sawant: clinics and correctness (owns the moment)**

* P1. core/slots.py optimistic lock plus unit tests. Done when the contention tests pass and only one hold wins. No blockers, start immediately (pure Python).  
* P2. core/policy.py plus synthetic data/clinics.json with three clinics that have different calendars and prices. Done when each clinic returns its soonest matching slot. Blocked by: nothing.  
* P3. ClinicAgent: offer on a SlotRequest, hold on a BookingRequest using P1, reply with a BookingResult. Run three instances. Blocked by: models, P1, P2.  
* P4. Real-time cancellation: on an interval, free a slot and emit a CancellationEvent. Done when a freed slot re-appears as an offer to a waiting request. Blocked by: P3.

## **Sarvesh Reshimwale: escrow, resilience, deploy, submission**

* S1. core/escrow.py plus unit tests. No blockers, start immediately.  
* S2. EscrowAgent on the Payment Protocol testnet: hold, release, refund. Done when a deposit is held and shown in the receipt, and a cancellation refunds it. Blocked by: models, S1.  
* S3. Resilience wrappers: timeouts, retries, and graceful handling when a clinic agent is offline. Done when killing a clinic mid-search does not break the booking. Blocked by: the agent skeletons.  
* S4. Ops and submission: bureau.py, scripts/register\_agents.py, the README with agent names and addresses and the Innovation Lab and hackathon badges, the ASI:One submission-agent registration, and the three to five minute demo video. Ongoing, finish Sunday morning.

## **Build order (tracer bullets)**

* T0 (all, 30 minutes): models, config, bureau, and stub agents that log.  
* T1 (Renuka, Atharva, Prathamesh, by about two hours in): the thin end-to-end path. One patient request goes through the matchmaker to one clinic and returns one offer, printed in ASI:One. This proves the Chat Protocol wiring before anyone builds depth.  
* Then parallel: P1 to P4, A2 to A4, R2 to R4, S1 to S4. The core modules P1 and S1 can start before the agents, since they are pure Python.  
* Integration 1 (Saturday evening): the full happy path in ASI:One (request, offers, cards, pick, book, escrow, confirm).  
* Integration 2 (Saturday night): the moment (two patients race for one slot and the lock resolves it), resilience (a clinic offline), and the real-time cancellation re-offer.  
* Freeze Saturday night. Sunday by 8am: record the video and register via the ASI:One submission agent. Submit by 9am.

## **Definition of done and submission checklist**

* Public GitHub repo, with a README listing each agent's name and Agentverse address, plus the Innovation Lab and hackathon badges.  
* All agents registered on Agentverse and reachable through ASI:One.  
* The full flow completes inside an ASI:One conversation, with no custom UI.  
* The Payment Protocol is used for the deposit on testnet.  
* The core modules have passing unit tests (slots, ranking, escrow, policy).  
* A three to five minute demo video, registered through the ASI:One submission agent.

## **Guardrails (do not skip)**

* Book or pay only on an explicit user action, a card tap. Never auto-book or auto-charge.  
* Label the synthetic data and the testnet payment on screen. We run all the clinic agents ourselves, so say so.  
* Do not add other sponsors. If you use a model to parse intent, prefer the ASI:One LLM, and do not pitch any model as a separate sponsor.  
* Do not fake the agent layer. Real Agentverse registration, real Chat Protocol messages, and a real compare-and-set lock. The money and the clinics are simulated; the Fetch.ai mechanics are real.

## **GitHub workflow (branches and commits)**

* main is protected and always green. Nobody commits to main directly. All work lands through pull requests.  
* One branch per feature, named feat/\<area\>, for example feat/slot-lock. One owner per branch.  
* Only the feature's owner commits to that branch. Claude Code does the typing, but set the local git identity to the owner before any commit on their branch, so the commit is attributed to them. The cleanest setup is one git worktree per owner, each with its own user.name and user.email, so every commit on that worktree auto-attributes.  
* Set identity on the owner's branch like this: git config user.name "Renuka Patwari" and git config user.email "patwarirenuka22@gmail.com", using the matching values from the identities list below.  
* Commit periodically, after every important step: after you write a failing test, after it passes, after a refactor, and whenever a ticket acceptance criterion is met. Small, frequent commits, never one big dump at the end.  
* Commit messages are short and imperative, saying what changed and why, for example slots: add compare-and-set hold, or test(slots): add failing double-hold test. If Claude Code adds its own co-author trailer, that is fine, as long as the author of record is the owner.  
* Merge the shared contract first. One person creates feat/shared-models with shared/models.py, merges it to main, then everyone branches from main so all features share the same message types.  
* Open a pull request from each feature branch to main when its tests pass. The owner reviews against the ticket acceptance criteria, then merges. Keep each pull request to one feature.  
* Pull main into your feature branch a few times over the weekend to avoid a big conflict at the end.  
* Never commit secrets. Commit .env.example only. Keep real keys in .env, which is gitignored.

## **TDD workflow (test first, every feature)**

* Write the test first. Red, green, refactor: write a failing test that states the behaviour, watch it fail, write the smallest code to pass it, then clean up.  
* No ticket is done until its tests pass. Every feature ships with tests.  
* Test the core modules hard, since they are pure Python and hold the correctness. slots: two holds race one slot and only one wins, a hold on a held slot is rejected, a released slot can be held again, the version increments. ranking: ordering is deterministic and stable, and constraint violations are dropped. policy: no matching slot returns none, and the deposit respects the clinic policy. escrow: release and refund are idempotent, and you cannot release a refunded escrow.  
* Test the agents through their logic, not the network. Pull each message handler into a plain function that takes a message and returns a reply or an action, and test that function directly. Keep the uAgent wrapper thin.  
* Add one integration test per key flow using the Bureau: a happy-path booking, the race (two patients, one slot), and a clinic-offline timeout.  
* Run the tests before every commit and before every pull request. A branch with failing or missing tests is not ready to merge.  
* Use pytest. Put unit tests in sooner/tests, one file per core module, and Bureau flow tests in sooner/tests/integration.

## **Branch and owner map**

* feat/shared-models (merge first): the message contracts. Then everyone branches off main.  
* Renuka Patwari: feat/patient-agent, feat/intent-parsing, feat/interactive-cards, plus the integration branch and demo scripts.  
* Atharva Mokashi: feat/matchmaker-agent, feat/clinic-discovery, feat/broadcast-timeout.  
* Prathamesh Sawant: feat/slot-lock, feat/clinic-policy, feat/clinic-agent, feat/cancellation-events.  
* Sarvesh Reshimwale: feat/escrow-core, feat/escrow-agent, feat/resilience, feat/deploy-submission.

## **Team git identities (set before committing on that person's branch)**

* Renuka Patwari. Username itsRenuka22. Email patwarirenuka22@gmail.com.  
* Atharva Mokashi. Username Atharva31. Email atharvamokashi31@gmail.com.  
* Prathamesh Sawant. Username Prathamesh0421. Email sawant.prathamesh2104@gmail.com.  
* Sarvesh Reshimwale. Username Sarvesh0827. Email sarveshreshimwale2708@gmail.com.

## **Review, test, and merge**

* The loop: the owner opens a pull request to main, CI runs the tests, one teammate reviews the diff against the ticket, the owner squash-merges, and everyone pulls. Main stays green and demo-ready throughout.  
* Test gate: CI runs pytest on every pull request, and branch protection on main requires it to pass before merge. A red suite cannot merge. The ci.yml is below.  
* Review: the owner runs the full suite locally, then opens a small pull request, one feature only, with a one-line summary and the ticket's acceptance criteria. Optionally have Claude Code review its own diff first. Then one teammate, usually Renuka as integration lead, checks that it meets the acceptance criteria and does not touch another person's module. That is the whole review. Do not gold-plate it.  
* Merge: before merging, update the branch with the latest main and let CI re-run, so conflicts surface early. Use squash merge, so each feature is one clean commit authored by the owner. Delete the branch after.  
* Merge order follows the build order: feat/shared-models first, then the pure-Python core (slot-lock, escrow-core, ranking, policy), then the agents, then integration. The contract merges before anything that imports it.  
* Keep main demo-ready: after each merge, Renuka runs the Bureau integration tests (happy path, the race, clinic-offline) and a quick ASI:One smoke test. If main breaks, fix or revert the last pull request immediately.  
* Avoid the end-of-night conflict: keep branches short-lived, merge small and often, and freeze shared/models.py. If the contract must change, do a tiny pull request that changes only that, merge it first, and everyone rebases.

## **Continuous integration (.github/workflows/ci.yml)**

name: ci  
on: \[pull\_request\]  
jobs:  
  test:  
    runs-on: ubuntu-latest  
    steps:  
      \- uses: actions/checkout@v4  
      \- uses: actions/setup-python@v5  
        with: { python-version: "3.11" }  
      \- run: pip install \-r requirements.txt  
      \- run: pytest \-q

## **Repo structure (tree)**

sooner/  
\|-- README.md                 \# agent names \+ Agentverse addresses, badges, run and test steps  
\|-- requirements.txt  
\|-- .env.example              \# Agentverse \+ ASI:One keys; real keys live in .env (gitignored)  
\|-- .github/  
\|   \`-- workflows/  
\|       \`-- ci.yml            \# runs pytest on every pull request  
\|-- shared/  
\|   \|-- models.py             \# the frozen message contracts (shared seam)  
\|   \`-- config.py             \# seeds, addresses, ports, timeouts  
\|-- core/                     \# deterministic, unit-tested, no agent framework  
\|   \|-- slots.py              \# Slot state machine \+ optimistic lock (compare-and-set)  
\|   \|-- ranking.py            \# the sooner score  
\|   \|-- policy.py             \# clinic match, price, deposit rules  
\|   \`-- escrow.py             \# hold, release, refund  
\|-- agents/                   \# thin uAgents that call core  
\|   \|-- patient\_agent.py  
\|   \|-- matchmaker\_agent.py  
\|   \|-- clinic\_agent.py       \# run three instances  
\|   \`-- escrow\_agent.py  
\|-- cards/  
\|   \`-- interactive\_cards.py  \# ASI1 Interactive Card builders  
\|-- data/  
\|   \|-- clinics.json          \# synthetic clinics \+ calendars (labeled)  
\|   \`-- patients.json  
\|-- scripts/  
\|   \|-- register\_agents.py    \# Agentverse registration  
\|   \`-- demo\_scenarios.py     \# happy path, race, failover  
\|-- bureau.py                 \# run all agents locally for dev  
\`-- tests/  
    \|-- test\_slots.py  
    \|-- test\_ranking.py  
    \|-- test\_policy.py  
    \|-- test\_escrow.py  
    \`-- integration/          \# Bureau flows: happy path, race, clinic-offline