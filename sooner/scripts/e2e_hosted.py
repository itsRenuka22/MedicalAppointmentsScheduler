"""End-to-end check against the deployed hosted agents (Phase 3). Scenario:
seed the demo clinics through the Registry, onboard a new dental clinic by chat, search + book it,
race two patients for its only slot (winner books, loser refunded), then cancel the booking so the
losing patient, waiting on the matchmaker's waitlist, is re-offered the slot and books it.
Usage: python -m sooner.scripts.e2e_hosted"""
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from sooner.scripts.deploy_agents import load_state

SEEDS = Path(__file__).resolve().parents[1] / "data" / "clinics.json"


def spawn(steps: list, seed: str):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(steps, f)
    f.close()
    return subprocess.Popen([sys.executable, "-m", "sooner.scripts.live_user", f.name, seed],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)


def collect(proc) -> list[dict]:
    out, _ = proc.communicate(timeout=400)
    return [json.loads(line) for line in out.splitlines() if line.startswith("{")]


def show(who: str, lines: list[dict]) -> None:
    for ln in lines:
        stamp = time.strftime("%H:%M:%S", time.localtime(ln["t"]))
        print(f"[{stamp}] {who:7} {ln['label']:14} {ln['text'].strip()[:260]!r}")


def main() -> None:
    st = load_state()
    run = datetime.now().strftime("%H%M%S")
    now = datetime.now()
    when = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    # later runs get an earlier slot, so this run's clinic is always offer #1 even with older demo clinics
    slot_time = (datetime(2000, 1, 1, 23, 59) - timedelta(minutes=now.hour * 60 + now.minute)).strftime("%H:%M")
    dental = (f"name: Smile Dental {run}\naddress: 12 Pine St #{run}, San Francisco, CA\n"
              f"specialties: dentist\ninsurance: Aetna\nslots: {when} {slot_time} $120")
    seeds = [dict(c, insurance=c["insurance"]) for c in json.loads(SEEDS.read_text())["clinics"]]
    clinic_id = "smile_dental_" + run
    ask = "I need a dentist, Aetna, deposit under $40"
    # Agent quota is 8 for ALL agents (hosted + mailbox). 5 core + 1 dental clinic + 2 test users = 8,
    # so user A is also the clinic owner, and every test identity removes itself at the end.
    book_at = time.time() + 130  # both patients book at the same instant, after onboarding settles
    cancel_at = book_at + 60
    taken = "just taken"
    loser = [{"op": "sleep_until", "epoch": cancel_at - 25},
             {"op": "chat", "to": st["patient"], "text": ask, "label": "retry-search", "timeout": 90}]
    race = [{"op": "chat", "to": st["patient"], "text": ask, "label": "search", "timeout": 90, "contains": "Smile Dental"},
            {"op": "sleep_until", "epoch": book_at},
            {"op": "chat", "to": st["patient"], "text": "book 1", "label": "book", "timeout": 90}]
    rebook = [{"op": "wait_chat", "label": "re-offer", "contains": "just opened", "timeout": 150},
              {"op": "chat", "to": st["patient"], "text": "book 1", "label": "book-after", "timeout": 90}]
    a_steps = ([{"op": "register", "to": st["registry"], "profile": c, "prefer_hub": True,
                 "label": "seed:" + c["clinic_id"]} for c in seeds]
               + [{"op": "chat", "to": st["registry"], "text": dental, "label": "onboard"},
                  {"op": "sleep", "seconds": 35}] + race
               + [{"op": "if_last_contains", "label": "book", "text": taken, "then": loser},
                  {"op": "sleep_until", "epoch": cancel_at},
                  {"op": "chat", "to_from": {"label": "onboard", "regex": "Serving agent: (agent1\\w+)"},
                   "text": f"cancel booking {clinic_id}-1", "label": "cancel", "contains": "cancelled"},
                  {"op": "if_last_contains", "label": "book", "text": taken, "then": rebook},
                  {"op": "chat", "to": st["registry"], "text": f"deregister {clinic_id}", "label": "deregister",
                   "contains": "removed"}])
    b_steps = (race[:1] + race[1:] + [{"op": "if_last_contains", "label": "book", "text": taken,
                                       "then": loser[:1] + [{"op": "chat", "to": st["patient"], "text": ask,
                                                             "label": "retry-search", "timeout": 90}] + rebook}])
    print("== seed + onboard (user A is the clinic owner), then two patients race for the single slot")
    a, b = spawn(a_steps, "sooner-e2e-user-a"), spawn(b_steps, "sooner-e2e-user-b")
    la, lb = collect(a), collect(b)
    show("userA", la); show("userB", lb)

    def reply(lines, label):
        return next((l["text"] for l in lines if l["label"] == label), "")
    ok_onboard = "Serving agent: agent1" in reply(la, "onboard")
    ok_race = sorted(["Booked" in reply(x, "book") for x in (la, lb)]) == [False, True]
    ok_refund = any("refunded" in reply(x, "book") for x in (la, lb))
    ok_reoffer = any("just opened" in l["text"].lower() for l in la + lb if l["label"] == "re-offer")
    ok_rebook = any("Booked" in l["text"] for l in la + lb if l["label"] == "book-after")
    print(f"\nresults: onboarded={ok_onboard} race_one_winner={ok_race} loser_refunded={ok_refund} "
          f"reoffer_after_cancel={ok_reoffer} loser_rebooked={ok_rebook}")
    sys.exit(0 if all([ok_onboard, ok_race, ok_refund, ok_reoffer, ok_rebook]) else 1)


if __name__ == "__main__":
    main()
