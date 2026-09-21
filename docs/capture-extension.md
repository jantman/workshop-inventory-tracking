# The Browser Capture Extension

Reads a vendor's listing or order page in your browser and hands what it read to
this application, which opens its confirmation or order review already filled
in. It replaces the capture bookmarklet, which no longer exists.

- [Why it replaced the bookmarklet](#why-it-replaced-the-bookmarklet)
- [Installing it](#installing-it)
- [Pointing it at your application](#pointing-it-at-your-application)
- [Using it](#using-it)
- [What it can read](#what-it-can-read)
- [When something goes wrong](#when-something-goes-wrong)
- [Updating it](#updating-it)
- [What it asks for, and what it does not](#what-it-asks-for-and-what-it-does-not)

---

## Why it replaced the bookmarklet

The bookmarklet was a loader: clicking it appended this application's
`capture-agent.js` to the vendor's page as a `<script>`. That is a subresource
from another origin, and a site is entitled to refuse those.

**McMaster-Carr does.** Their `Content-Security-Policy` names a `script-src`
that does not include your server, so the browser refuses to load the script and
clicking the bookmark does nothing at all — no message, no error a person would
notice, nothing. No McMaster page could be captured by any route: the paste-an-
address path cannot express an order, and it was the order pages that mattered
most.

An extension's content script runs in an **isolated world**, which carries its
own content policy rather than the page's. It is never measured against
McMaster's `script-src`. That is the whole fix, and it is why the extension
exists rather than some adjustment to the bookmarklet.

Two things improved along the way:

- **The submission no longer comes from the vendor's page.** The extension reads
  the page, then submits from a page of its own. A vendor's
  `upgrade-insecure-requests` — which broke the transport in issue #54 — is no
  longer in the path, and neither is the popup blocker.
- **Your vendor tab stays where it is.** The review opens in a new tab and the
  page you were reading is never navigated away from.

One thing got worse, and it is the reason this page exists:

> **Changing what a capture reads now needs a new extension, installed by hand.**
> With the bookmarklet, the reader was served by the application, so upgrading
> the application was the whole deployment. The reader now lives inside the
> extension. An application upgrade that changes what a capture sends needs the
> matching extension version installed in your browser, by you. Nothing does
> this automatically and nothing warns you — compare the version on the
> extension's options screen with the one in the application's footer.

---

## Installing it

There is no signed package and no Web Store listing. A signed `.crx` would be
refused by Chrome outside its store on Windows and macOS; an unpacked directory
loads on every platform with no key. So the install is:

1. Go to this repository's [releases][releases] and pick the release matching
   the version in your application's footer.
2. Download **`capture-extension.zip`** from that release's assets, and unzip it
   somewhere it can stay. Chrome loads it from that directory every time the
   browser starts — if you delete or move the directory, the extension stops
   working.
3. Open `chrome://extensions`.
4. Turn on **Developer mode**, top right.
5. Click **Load unpacked** and select the unzipped directory — the one holding
   `manifest.json`.

The extension appears in the list, and its icon appears in the toolbar. You may
have to pin it: click the puzzle-piece button beside the address bar and pin
*Workshop Capture*.

Every ordinary CI build also publishes the same zip as a build artifact, which
is how you install a version that has not been released yet.

[releases]: https://github.com/jantman/workshop-inventory-tracking/releases

---

## Pointing it at your application

Nothing is built into the package — it has no idea where your installation is
until you tell it.

1. On `chrome://extensions`, click **Details** under *Workshop Capture*, then
   **Extension options**. (Or right-click the toolbar icon → **Options**.)
2. Enter your application's address: scheme, host and port, for example
   `https://workshop.example.com:15603`.
3. **Save.**

**Paste straight from the address bar.** Surrounding spaces, a trailing slash,
and the path of whatever page you copied it from are all trimmed off when the
value is stored — `https://workshop.example.com:15603/products/capture` is
stored as `https://workshop.example.com:15603`. What is kept is the scheme, the
host and the port, because the extension appends `/api/capture` itself.

That also means **the application has to be at the root of its host**. A
deployment served under a sub-path is not supported.

The address is kept in Chrome's synced storage, so it survives a browser restart
and follows you to your other signed-in Chrome profiles.

> ### The application must be served over HTTPS
>
> Save an `http://` address and the options screen warns you, and saves it
> anyway — it is your installation, and you are told rather than blocked. But
> capture will very likely fail against it: the extension's own page is a secure
> context, and a browser may refuse to submit from one to an insecure address.
>
> This is not new with the extension. Serving this application over TLS was
> already required for capture and is covered in the
> [deployment guide](deployment-guide.md).

**Check the version while you are here.** The options screen shows the
extension's version. It must match the version in the application's footer.

---

## Using it

Open the vendor page you want to capture — the listing, or the order — and
either:

- **click the toolbar icon**, or
- **right-click the page** and choose *Capture to Workshop*. The right-click
  entry is offered only on Amazon and McMaster-Carr; both entry points do
  exactly the same thing.

A new tab opens on this application's confirmation form or order review, filled
in with what the page yielded. **Nothing has been recorded yet** — you finish
the description, check what it found, and submit from there.

An order page takes several seconds, because each line's own listing is read as
well. A banner on the vendor's page says how far it has got.

---

## What it can read

| Page | What you get |
|---|---|
| An Amazon **listing** (`/dp/<ASIN>`) | The confirmation form, pre-filled: price, brand, description, the *About this item* bullets, the product-information rows, and every image the page's own data names |
| An Amazon **order** (`/your-orders/order-details?orderID=…`) | The order review, one row per ordered line, each with its own listing read as well |
| A McMaster **product** (`mcmaster.com/<part>/`) | The confirmation form, pre-filled from the part page |
| A McMaster **order** (`/order-history/order/<id>`) | The order review, one row per line |

Anything else — a search results page, an Amazon order *list*, a McMaster family
table — gets a message on the page saying it is not one the extension can read.
It never captures a page it did not recognize.

**It reads page markup, which is not a contract.** Vendors change their markup
without warning, and when they do, the field that moved is lost and nothing else
is. A capture that comes back thin is the signal that something moved; that is
why the confirmation page tells you what it found before you commit it. The
paste-an-address box on the application's capture page still works for anything
the extension cannot read, and it cannot break this way.

---

## When something goes wrong

| What you see | What it means |
|---|---|
| "No application address is configured yet", and the options screen opens | Exactly what it says. Enter the address and try again. |
| "This is not a page it can read" | The address is not one of the four kinds above. On a McMaster family table, open the individual part. On an Amazon order *list*, open the order. |
| "The page could not be read. Nothing was sent." | The reader failed outright. Nothing partial is ever submitted. Usually a vendor markup change large enough to break the reader rather than one field; the paste box is the fallback. |
| The capture tab opens but the POST fails | The address is wrong, the application is unreachable, or it is not served over TLS. |
| The capture tab says the browser **did not send** the capture | The navigation was refused rather than failing — almost always an `http://` address, which a page belonging to an extension may not be allowed to submit to. Correct the address on the options screen and come back to that tab: the capture is still held, and **Try sending it again** reads the address afresh, so it uses the corrected one. |
| A console message naming a `script-src` violation | Should be impossible now — the reader runs in an isolated world. If you see one, the injection is going into the page's main world, which is a defect worth an issue. |
| One field missing, everything else present | A vendor markup change. This is the designed behavior, not a transport fault — do not chase it as one. |
| Nothing at all happens | Nothing should ever produce silence. Check `chrome://extensions` → *Workshop Capture* → **service worker** for its console. |

---

## Updating it

1. Download the new `capture-extension.zip` from the release matching your
   upgraded application.
2. Unzip it **over the same directory** you loaded from.
3. On `chrome://extensions`, click the reload arrow on *Workshop Capture*.

Your configured address survives; it lives in browser storage, not in the
package.

**Do this whenever you upgrade the application.** The extension's version and
the application's version are the same string by construction — a test fails the
build if they ever disagree — so they tell you plainly whether you are running a
matched pair.

---

## What it asks for, and what it does not

The install screen lists four permissions, and each is load-bearing:

| Permission | Why |
|---|---|
| `activeTab` | Lets it read the tab you invoked it on — **only** the one you invoked it on, and only when you invoke it |
| `scripting` | Puts the reader into that tab |
| `storage` | Holds the one address you configured |
| `contextMenus` | The right-click entry |

It asks for **no host permissions**, so it has no standing access to Amazon,
McMaster-Carr, or anywhere else. Nothing runs on any page until you ask for it.

It holds no credentials, sends no telemetry, has no identifier of its own, and
talks to nothing but the address you configured. What it sends is described in
the [capture payload contract][payload].

[payload]: ../specs/028-mcmaster-order-capture/contracts/capture-payload.md
