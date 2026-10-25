from datetime import datetime

from sooner.core.registry import Registry
from sooner.core.registry_chat import RegistryChat, merge_draft, parse_clinic_text
from sooner.core.store import MemoryStore
from sooner.tests.test_registry import FakeProvisioner

NOW = datetime(2026, 10, 25, 8, 0)
FULL = """name: Smile Dental
address: 12 Pine St, San Francisco, CA
specialties: dentist, dental
insurance: Aetna, Cigna
slots: 2026-10-27 10:00 $120, 2026-10-28T14:30 150"""
NO_LLM = lambda t: (_ for _ in ()).throw(RuntimeError("down"))


def test_regex_fallback_parses_full_message():
    d = parse_clinic_text(FULL, llm=NO_LLM)
    assert d["name"] == "Smile Dental" and d["address"] == "12 Pine St, San Francisco, CA"
    assert d["specialties"] == ["dentist", "dental"] and d["insurance"] == ["Aetna", "Cigna"]
    assert d["slots"] == [{"time": "2026-10-27T10:00", "price": 120.0},
                          {"time": "2026-10-28T14:30", "price": 150.0}]


def test_llm_result_is_used_and_nulls_dropped():
    llm = lambda t: {"name": "LLM Clinic", "address": None, "specialties": ["dental"], "slots": []}
    d = parse_clinic_text("anything", llm=llm)
    assert d["name"] == "LLM Clinic" and "address" not in d and "slots" not in d


def test_merge_draft_keeps_earlier_fields_and_appends_slots():
    a = {"name": "X", "slots": [{"time": "t1", "price": 1}]}
    b = {"address": "Y", "slots": [{"time": "t2", "price": 2}]}
    assert merge_draft(a, b) == {"name": "X", "address": "Y",
                                 "slots": [{"time": "t1", "price": 1}, {"time": "t2", "price": 2}]}


def chat(max_dedicated=2, prov=None):
    r = Registry(MemoryStore(), prov or FakeProvisioner(), max_dedicated, "agent-hub")
    return RegistryChat(r), r


def test_asks_for_missing_fields_then_completes_across_messages():
    c, r = chat()
    reply, res = c.handle("clinic1", "name: Smile Dental\naddress: 12 Pine St", llm=NO_LLM, now=NOW)
    assert res is None and "specialties" in reply and "insurance" in reply and "slots" in reply
    reply, res = c.handle("clinic1", "specialties: dental\ninsurance: Aetna\nslots: 2026-10-27 10:00 $120",
                          llm=NO_LLM, now=NOW)
    assert res.ok and "agent-dedicated-1" in reply
    assert r.get(res.clinic_id)["status"] == "active"
    assert r.get(res.clinic_id)["agent_address"] == "agent-dedicated-1"


def test_drafts_are_per_sender():
    c, _ = chat()
    c.handle("a", "name: A", llm=NO_LLM, now=NOW)
    reply, _ = c.handle("b", "name: B", llm=NO_LLM, now=NOW)
    assert "address" in reply


def test_duplicate_reply_and_no_valid_slots_reply():
    c, _ = chat()
    assert c.handle("a", FULL, llm=NO_LLM, now=NOW)[1].ok
    reply, res = c.handle("b", FULL, llm=NO_LLM, now=NOW)
    assert not res.ok and "already" in reply
    bad = FULL.replace("Smile Dental", "Other").replace("2026-10-27 10:00", "2020-01-01 10:00").replace("2026-10-28T14:30", "2020-01-02T10:00")
    reply, res = c.handle("c", bad, llm=NO_LLM, now=NOW)
    assert not res.ok and "slot" in reply.lower()


def test_hub_fallback_is_explained_to_the_clinic():
    c, _ = chat(prov=FakeProvisioner(fail_always=True))
    reply, res = c.handle("a", FULL, llm=NO_LLM, now=NOW)
    assert res.ok and res.host == "hub" and "hub" in reply.lower() and "402" in reply


def test_deregister_command_via_chat():
    c, r = chat()
    res = c.handle("clinic1", FULL, llm=NO_LLM, now=NOW)[1]
    reply, none = c.handle("clinic1", f"deregister {res.clinic_id}", llm=NO_LLM, now=NOW)
    assert none is None and "removed" in reply.lower() and r.entries() == []
    assert "not allowed" in c.handle("clinic1", "deregister nope", llm=NO_LLM, now=NOW)[0].lower()
