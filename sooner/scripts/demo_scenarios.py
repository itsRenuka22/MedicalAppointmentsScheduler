"""Scripted happy path, race, and failover using the in-process handlers."""
import asyncio

from sooner.tests.integration.harness import World


async def main():
    w = World()
    print("--- happy path")
    p = w.patient()
    print(await p.handle_message("I need a dermatologist, Aetna, deposit under $40"))
    print(await p.handle_message(w.first_tap(p)))
    print("--- race: two patients, one slot")
    a, b = w.patient(), w.patient()
    await a.handle_message("dermatologist Aetna deposit under $40")
    await b.handle_message("dermatologist Aetna deposit under $40")
    tap = w.first_tap(a)
    print(await a.handle_message(tap)); print(await b.handle_message(tap))
    print("--- failover: a clinic offline")
    w.logics["clinic_bayside"].online = False
    print(await w.patient().handle_message("dermatologist Aetna deposit under $40"))


if __name__ == "__main__":
    asyncio.run(main())
