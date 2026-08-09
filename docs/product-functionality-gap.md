# Product Catalogue: What Was Planned but Isn't Built

The abandoned `archive/bmad-product-catalog` branch contains a large body of planning work for the
product catalogue. Only about half of it was ever built there, and the catalogue that now ships on
`main` was designed separately. This is a list of the user-facing things that plan describes and the
current application does not do.

It is not a to-do list. Several of these were dropped deliberately and should stay dropped; the
point is to have the reasoning written down before it is lost with the branch.

## Order capture

**The price isn't captured.** The whole premise of capturing at order time is that the listing is in
front of you and will not be there later. The plan had the capture read the price off the page along
with the title and item number. The bookmarklet as built reads only the page address and its title,
and works out the vendor and item number from the address. Everything else — price, quantity — is
typed in by hand afterwards, which is most of the work the feature was meant to remove.

The trade-off is real: reading the address is robust and reading the page is not, because a vendor
can rearrange its markup at any time. But as it stands, capturing an order still leaves the price to
be transcribed later, from a page that may have changed.

**~~You can't write the description while you're looking at the listing.~~** *Built — feature 006.*
Capture has a description field, and a manufacturer and part number alongside it. Left blank, the
listing title is still used, so the one-click case stays one click.

**~~And you can't fix it when the box arrives.~~** *Built — feature 006.* The receive screen's
description is an editable field, applied in the same submission that marks the purchase received,
on hand-recorded purchases as well as captured ones and on already-received ones too.

**~~Capturing the same thing twice can create duplicates.~~** *Built — feature 006.* Capture no
longer decides. A repeat is recognized by vendor, item number and date, falling back to the
listing's address when the URL yields no item number — and it is put to the operator as a question
naming the existing purchase, with "record it anyway" as one of the answers. Two genuinely separate
orders of the same item on the same day are therefore two purchases, which the old silent
idempotency merged.

**~~Nothing warns you when a vendor recycles an item number.~~** *Built — feature 006.* An item
number that already names a product produces a named choice showing that product's description and
part number. It attaches without asking only when the capture supplies a manufacturer *and* a part
number and both agree, which is what the plan called for.

The one thing capture still doesn't do is read the **price** off the listing — see the paragraph
above, and issue #56.

## Reordering and stock

**A manual low flag has no age.** A counted quantity shows how long ago it was counted, so you can
judge whether to trust it. A hand-set "low" or "out" flag shows nothing, so a product flagged two
years ago looks exactly like one flagged this morning.

**Receiving an order changes the count.** This is a difference rather than an absence, and it is the
one place where the built behaviour actively contradicts the plan. Receiving a purchase adds the
received quantity to a tracked count and marks the count as freshly updated. The plan was emphatic
that receiving must never touch a count, on the grounds that a count nobody verified should not
present itself as verified — an inaccurate number being worse than no number. Both positions are
defensible; what isn't is showing "counted just now" when nobody counted anything.

## Grouping products that are the same thing

The plan has a way to declare that several catalogue entries are one manufacturer's part sold under
different brand names — the same module relabelled by three sellers. Those entries then show each
other, with each one's latest price, so you can see where it's cheapest; they collapse to a single
line when reordering; and an order already in flight on any one of them suppresses the reorder
signal for all of them, so you don't order the same thing twice under a different name.

None of this exists, and its absence was a deliberate decision recorded in the current spec: several
listings for one item are meant to be handled by putting several identifiers and several purchases
on a single product. That covers the identification case well. It does not cover price comparison
across brands or the double-ordering problem, which is what the grouping was for.

## Organising the catalogue

**Categories and tags can't be renamed.** Categories are created by typing them, which means they
accrete typos and second thoughts. There is no way to rename one — the plan had a rename carry all
its sub-categories and every product filed under them, and refuse a rename that would collide with an
existing category. Today the only fix is to edit every affected product by hand. The same is true of
tags, which cannot be renamed or merged.

**Location and vendor don't suggest anything.** The application already knows every location and
vendor name used by the metal stock, and offers them as you type. Product location and purchase
vendor are plain text boxes that suggest nothing and contribute nothing back, so the two halves of
the application will drift apart by spelling. The plan had them share one vocabulary in both
directions. Products also have a location but no sub-location, where metal stock has both.

**Specifications are one block of text.** The plan stored them as named values, so you could ask for
every 12 V converter you own, and so a scan result could lay them out as fields. As built they are
free text: searchable by word, not filterable, and shown as a paragraph.

## Finding things

**A manufacturer's own 2D barcode doesn't resolve.** Scanning handles the codes this system prints,
distributor labels, and plain retail barcodes. It does not handle the standard structured form a
manufacturer uses to put a retail barcode in a 2D symbol, so scanning one of those falls through to
a plain text search instead of finding the product. This one is worth noting because the archived
branch found it during its own build and amended its spec for it.

**Notes aren't searched.** Descriptions, specifications, part numbers and identifiers are. Anything
written in the notes field is invisible to search.

**A product's address isn't derived from its label.** The plan gave each product a permanent address
built from the code printed on its label, so the label and the link are the same fact. Product
addresses are internal record numbers instead — which works, but means the printed code and the
product's location in the application are two separate things to keep in step.

## Labels

**No "if found, return to" text.** The plan reserved a human-readable line on the label for
ownership and return information. Labels carry the description, the purchase provenance and the code.

**The printed code is a conventional barcode rather than a 2D symbol.** The functional goal — a code
that can never be mistaken for a manufacturer's or a distributor's — is met either way. What the 2D
symbol would have bought is a smaller mark, which matters mainly on the narrow label stock where
space is tight.

## Worth noting: where the current application is ahead

The plan restricted capture to Amazon; the built version recognizes several vendors and falls back
to the site name for the rest, and has a paste-the-address page that works for anything at all. The
plan reserved the largest label stock for shipping and allowed catalogue labels on only two sizes;
the built version offers every stock. The plan stored attachments in a new mechanism of their own;
the built version reuses the photo storage the application already had. And the built version
refuses a barcode that reads as all zeros — a scanner misread rather than a product — which the
plan only discovered late.
