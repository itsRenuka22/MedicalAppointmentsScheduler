# Sooner Clinic Registry

Onboard your clinic onto Sooner by describing it in chat. Send one field per line:

```
name: Smile Dental
address: 12 Pine St, San Francisco, CA
specialties: dental
insurance: Aetna, Cigna
slots: 2026-10-27 10:00 $120, 2026-10-28 14:30 $150
```

I ask for anything missing, reject duplicates, and ignore clinics with no valid future slots.
On success your clinic gets its own hosted agent (or a place on the shared clinic hub when the
account is at its agent limit) and I reply with the serving agent's address. Manage slots by
chatting with that agent: `add slot 2026-10-28T10:00 150`, `list slots`, `cancel booking <slot_id>`.

_Demo: clinics and payments are simulated._
