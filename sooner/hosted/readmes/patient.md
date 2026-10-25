# Sooner Patient Agent

Finds you an earlier medical appointment. Sooner watches clinics for cancelled and newly
freed slots, ranks what is available, and books the one you choose.

## What it does
- **Earlier appointments from cancelled slots:** asks nearby clinic agents for their soonest
  open slot and re-offers slots the moment a cancellation frees them.
- **Specialties:** dermatology, primary care (general) and dental requests.
- **Insurance filtering:** only shows clinics that accept your insurance.
- **Refundable deposits:** a small deposit is held in escrow when you book, released to the
  clinic on confirmation, and refunded if the slot is taken first.
- **Booking confirmation:** you get a confirmation ID in chat. Nothing is booked or paid
  until you explicitly choose an offer.

## Example prompts
1. `I need a dermatologist tomorrow, Aetna, deposit under $40`
2. `Find me a primary care appointment this week with Blue Shield, within 10 miles`
3. `Any dental openings in the next 3 days? Cigna, max deposit $30`
4. `Earliest dermatology slot within 5 miles, Kaiser`

To book, reply with the offer shown, e.g. `book:clinic_bayside:bs-1`.

_Demo notice: clinics and patients are synthetic and payments are testnet-simulated._
