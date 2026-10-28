---
name: rfq-quote
description: "Turn a customer's request for quote (RFQ) email into a priced, reviewed quote and a draft reply. Use whenever a customer asks for pricing, a quote, or to buy or license a batch of tracks."
---

# Request for Quote (RFQ)

Work through these steps in order, and track them in a todo list so Jane can
follow along.

## 1. Read the email

Have **inbox-manager** find the request and read the whole message. Note:
- who sent it (name, company, email address)
- exactly what they're asking for: which genres or tracks, and how many of each

## 2. Find (or add) the customer

- Have **chinook-analyst** look the customer up by email, then by name if the
  email search finds nothing.
- **If they're a new customer**, have chinook-analyst add them with
  `add_customer`. That call pauses for Jane's approval by itself, so the
  analyst should just make the call. Carry on once she approves.

## 3. Get the real prices

Have **chinook-analyst** pull the prices you need from the database:
- **"N tracks of genre X"**: how many tracks are available in that genre, and
  their `UnitPrice`. Tracks are usually $0.99, but check rather than assume.
- **"Your best sellers"**: the top-selling tracks by quantity sold, with
  their prices.

Never estimate a price.

## 4. Calculate the quote

- Use the **code interpreter** for all the math: quantity × unit price for
  each line, then any discount, then the grand total.
- Default volume discount: **10% off orders of 50 or more tracks.** If it
  applies, show it as its own line.

## 5. Get it reviewed

Send the line items and totals to **quote-reviewer**. Fix anything it flags
before you write the reply.

## 6. Draft the reply

- Write a short, friendly reply from Jane. Include a thank-you, a line for each
  item (description, quantity, unit price, line total), the discount if any,
  the grand total, and a suggested next step.
- Have **inbox-manager** save it as a draft addressed to the sender, with the
  subject and the full body. Saving pauses for Jane to approve or edit it, so
  don't ask her first in chat. Drafts are never sent automatically.

## 7. Log the quote

Add one row to `/outputs/quotes_ledger.md` with the date, customer, a summary
of the items, the total, and the draft ID. If the file doesn't exist yet,
create it with a header row first.

## Wrap up

Tell Jane the draft is waiting in her drafts folder, and give her the quote
total.
