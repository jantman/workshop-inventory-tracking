/**
 * The capture agent: what the bookmarklet loads into a vendor's listing page.
 *
 * The bookmarklet is only a loader now. It appends this file as a <script> with
 * `data-endpoint` naming this application's /api/capture, and everything that
 * reads the listing lives here -- in an ordinary reviewable file in this
 * repository rather than in a few hundred lines of unreadable `javascript:` URL.
 * The loader cache-busts, so editing this file is the whole deployment story.
 *
 * **It submits a form into a new tab rather than issuing a fetch.** A fetch from
 * the vendor's origin to this host would need CORS configuration this
 * application does not have, and would be refused as mixed content besides. A
 * form submission is a navigation: no preflight, no response header for the
 * vendor to influence, and it is the one path proven to survive Amazon's
 * `upgrade-insecure-requests` (issue #54).
 *
 * The payload rides as one hidden `listing` field holding JSON. `url` and
 * `listing_title` are still sent unchanged, so a server that ignored `listing`
 * entirely would behave exactly as it does today.
 *
 * **Every extraction step here is independent and optional.** Amazon's markup is
 * not a contract; today's capture reads only the URL for exactly that reason,
 * and this feature knowingly gives that up because the requirement cannot be met
 * from a URL. What bounds the damage is FR-007: a selector that stops matching
 * loses that one field and nothing else. Nothing below may throw.
 */

(function () {
    'use strict';

    // The payload shape. `ListingCapture.from_json` refuses anything else, which
    // is what makes a stale cached agent harmless rather than a 500.
    const PAYLOAD_VERSION = 1;

    // The same shape app/product/routes.py:_asin_from_url reads. Deliberately
    // duplicated rather than shared: a URL path is a contract, and the two live
    // on opposite sides of a machine boundary.
    const ASIN_PATTERN = /\/(?:dp|gp\/product|product)\/([A-Z0-9]{10})(?:[/?]|$)/;

    // ---------------------------------------------------------------
    // Reading the page
    // ---------------------------------------------------------------

    /** Trimmed, whitespace-collapsed text, or '' -- never null, never a throw. */
    function textOf(node) {
        if (!node) {
            return '';
        }
        return (node.textContent || '').replace(/\s+/g, ' ').trim();
    }

    /**
     * The price, as a string of digits and at most one decimal point.
     *
     * **It stays a string all the way to `_validate_price`.** JSON's only number
     * type is an IEEE double, so emitting this as a number would make it a float
     * before any Python saw it, and Principle III has no exemption for a value
     * in transit. Anything that does not read as a price yields null rather than
     * a guess.
     */
    function priceFrom(doc) {
        const shown = textOf(doc.querySelector('.a-price .a-offscreen'));
        if (!shown) {
            return null;
        }

        // Currency symbol off the front, thousands separators out of the middle.
        const digits = shown.replace(/[^0-9.,]/g, '').replace(/,/g, '');
        return /^[0-9]+(\.[0-9]+)?$/.test(digits) ? digits : null;
    }

    /**
     * The brand from the byline, with the two wrappers Amazon puts round it.
     *
     * "Visit the Acme Store" and "Brand: Acme" both mean Acme; the byline is
     * also sometimes just the name.
     */
    function brandFrom(doc) {
        const byline = textOf(doc.querySelector('#bylineInfo'));
        if (!byline) {
            return null;
        }

        const visit = byline.match(/^Visit the (.+?) Store$/i);
        if (visit) {
            return visit[1];
        }
        const labelled = byline.match(/^Brand:\s*(.+)$/i);
        if (labelled) {
            return labelled[1];
        }
        return byline;
    }

    /** The listing's own title, preferring the product title to the tab's. */
    function titleFrom(doc) {
        return textOf(doc.querySelector('#productTitle')) || doc.title || null;
    }

    // ---------------------------------------------------------------
    // Product information
    // ---------------------------------------------------------------

    // Every container issue #57 found across the six sampled listings.
    // #prodDetails was on all six with 6-25 rows, the overview on four, the
    // technical specifications on two and poExpander on one -- so no single one
    // of these is sufficient and all of them have to be read and merged.
    const SPECIFICATION_CONTAINERS = [
        '#prodDetails',
        '#productDetails_techSpec_section_1',
        '#productDetails_detailBullets_sections1',
        '#productOverview_feature_div',
        '#technicalSpecifications_feature_div',
        '#poExpander',
        '#detailBullets_feature_div'
    ];

    /** Trim the punctuation Amazon puts between a bullet's name and its value. */
    function tidyName(name) {
        // The bidi marks are literally in the markup: "Date First Available ‏ : ‎".
        return name.replace(/[‎‏؜]/g, '').replace(/[\s:]+$/, '').trim();
    }

    /** Name/value pairs out of one container, whichever of the shapes it uses. */
    function rowsFrom(container) {
        const rows = [];

        // Shape one: a two-cell table row, th/td or td/td.
        const tableRows = container.querySelectorAll('tr');
        for (let i = 0; i < tableRows.length; i++) {
            const cells = tableRows[i].querySelectorAll('th, td');
            if (cells.length === 2) {
                rows.push({ name: tidyName(textOf(cells[0])), value: textOf(cells[1]) });
            }
        }

        // Shape two: a detail bullet, where the name is the bold span and the
        // value is whatever is left over.
        const items = container.querySelectorAll('li');
        for (let i = 0; i < items.length; i++) {
            const bold = items[i].querySelector('.a-text-bold');
            if (!bold) {
                continue;
            }
            const whole = textOf(items[i]);
            const name = tidyName(textOf(bold));
            const value = whole.slice(textOf(bold).length).replace(/^[\s:]+/, '').trim();
            if (name && value) {
                rows.push({ name: name, value: value });
            }
        }

        return rows;
    }

    /**
     * Every product-information row, merged across the page's containers.
     *
     * FR-008 and FR-009. Names differing only in case or surrounding whitespace
     * are one name, first occurrence winning.
     *
     * **Nothing is filtered by name.** Best Sellers Rank, Customer Reviews and
     * Date First Available are emitted like everything else. An unwanted row is
     * one click to delete; a physical fact lost to a filter rule is
     * unrecoverable once the listing is gone.
     *
     * This fold is *not* the one CatalogService.merge_specifications performs.
     * That one folds captured names against the product's existing rows; this
     * one folds the page's containers against each other. Two folds, two
     * questions, and a shared helper would be a coincidence rather than a reuse.
     */
    function specificationsFrom(doc) {
        const entries = [];
        const seen = {};

        for (let i = 0; i < SPECIFICATION_CONTAINERS.length; i++) {
            const container = doc.querySelector(SPECIFICATION_CONTAINERS[i]);
            if (!container) {
                continue;
            }
            const rows = rowsFrom(container);
            for (let j = 0; j < rows.length; j++) {
                const name = rows[j].name;
                const value = rows[j].value;
                if (!name || !value) {
                    continue;
                }
                const key = name.toLowerCase();
                if (seen[key]) {
                    continue;
                }
                seen[key] = true;
                entries.push({ name: name, value: value });
            }
        }

        return entries;
    }

    // ---------------------------------------------------------------
    // The gallery
    // ---------------------------------------------------------------

    /**
     * Strip the transform token, so the address names the original file.
     *
     * FR-004. `._AC_SL1500_.` and its kin are not the original: issue #57
     * measured 1446x1500 with the token against 1601x1601 without, 345,670
     * bytes against 358,055. There is deliberately **no fallback to the tokened
     * address** if the stripped one 404s -- a silent fallback would satisfy
     * FR-004 by accident and nobody would know which images were originals. A
     * stripped address that fails is reported as a failed image instead.
     */
    function withoutTransform(url) {
        return url.replace(/\._[^./]*_\./, '.');
    }

    /**
     * The JSON array following `colorImages` ... `initial` in a script's text.
     *
     * Bracket-matched and parsed rather than pattern-matched, because entries
     * whose `hiRes` is null still name a usable `large` and a regex sweep for
     * one key at a time cannot pair them up. Returns null when the block is not
     * shaped the way this expects; the caller then sweeps.
     */
    function initialImageArray(text) {
        const anchor = text.indexOf('colorImages');
        if (anchor === -1) {
            return null;
        }
        const marker = text.slice(anchor).search(/["']initial["']\s*:\s*\[/);
        if (marker === -1) {
            return null;
        }

        const start = text.indexOf('[', anchor + marker);
        let depth = 0;
        let quote = null;
        for (let i = start; i < text.length; i++) {
            const character = text[i];
            if (quote) {
                if (character === '\\') {
                    i++;
                } else if (character === quote) {
                    quote = null;
                }
                continue;
            }
            if (character === '"' || character === "'") {
                quote = character;
            } else if (character === '[') {
                depth++;
            } else if (character === ']') {
                depth--;
                if (depth === 0) {
                    try {
                        return JSON.parse(text.slice(start, i + 1));
                    } catch (error) {
                        return null;
                    }
                }
            }
        }
        return null;
    }

    /** Last resort: pull whatever hi-res addresses the block names, in order. */
    function sweepImageAddresses(text) {
        const found = [];
        const pattern = /["'](?:hiRes|large)["']\s*:\s*"(https?:[^"]+)"/g;
        let match;
        while ((match = pattern.exec(text)) !== null) {
            found.push(match[1]);
        }
        return found;
    }

    /**
     * Every gallery image the listing's own page data names (FR-003).
     *
     * **Read out of the inline data block, never out of the DOM.** The
     * thumbnail strip shows a subset -- issue #57 found listings naming more
     * than twice what the strip displays -- and the full-size images are not in
     * the DOM at all until the gallery is interacted with. That single finding
     * is what ruled out every archiving approach that worked from rendered
     * markup.
     */
    function galleryFrom(doc) {
        const scripts = doc.querySelectorAll('script');
        for (let i = 0; i < scripts.length; i++) {
            const text = scripts[i].textContent || '';
            if (text.indexOf('colorImages') === -1) {
                continue;
            }

            const entries = initialImageArray(text);
            let addresses = [];
            if (entries && entries.length) {
                for (let j = 0; j < entries.length; j++) {
                    const entry = entries[j];
                    const address = entry && (entry.hiRes || entry.large);
                    if (typeof address === 'string' && /^https?:/.test(address)) {
                        addresses.push(address);
                    }
                }
            }
            if (!addresses.length) {
                addresses = sweepImageAddresses(text);
            }
            if (addresses.length) {
                return addresses.map(withoutTransform);
            }
        }
        return [];
    }

    /**
     * Everything the agent could read, as the payload object.
     *
     * A key is omitted when the page yielded nothing for it -- never sent as an
     * empty string, which would look to the server like an extracted blank.
     */
    function extract(doc, sourceUrl, asin) {
        const listing = {
            version: PAYLOAD_VERSION,
            source_url: sourceUrl
        };

        const set = function (key, value) {
            if (value) {
                listing[key] = value;
            }
        };

        set('vendor_item_id', asin);
        set('listing_title', titleFrom(doc));
        set('price', priceFrom(doc));
        set('brand', brandFrom(doc));

        // Gallery first. The server carries one flat list and never learns
        // which image came from where, which is what lets FR-019's "gallery
        // images are exempt from the size filter" be true without the server
        // being trusted to honour a distinction it cannot see.
        const images = [];
        const seen = {};
        const addImages = function (addresses) {
            for (let i = 0; i < addresses.length; i++) {
                if (!seen[addresses[i]]) {
                    seen[addresses[i]] = true;
                    images.push(addresses[i]);
                }
            }
        };
        addImages(galleryFrom(doc));

        const description = descriptionBlock(doc);
        if (description) {
            // Uncapped, and sent whole. b1a0c0d10009 widened the column it lands
            // in to 16,777,215 bytes precisely so there is nothing to truncate
            // against and FR-006 holds without an exception.
            set('description_text', textOf(description));
            addImages(descriptionImages(description));
        }

        if (images.length) {
            listing.images = images;
        }

        const specifications = specificationsFrom(doc);
        if (specifications.length) {
            listing.specifications = specifications;
        }

        return listing;
    }

    // ---------------------------------------------------------------
    // The description
    // ---------------------------------------------------------------

    // Under this on *either* edge, a description image is layout furniture
    // rather than content (FR-019). Gallery images are exempt and never reach
    // this code.
    const MIN_DESCRIPTION_EDGE = 300;

    // The plain form and the rich ("A+") form. Issue #57 found three of the six
    // sampled listings one way and three the other, and **never both** -- so
    // this reads whichever is present rather than combining them (FR-005).
    const DESCRIPTION_CONTAINERS = ['#productDescription', '#aplus', '#aplus_feature_div'];

    /** Whichever description block the listing carries, or null. */
    function descriptionBlock(doc) {
        for (let i = 0; i < DESCRIPTION_CONTAINERS.length; i++) {
            const block = doc.querySelector(DESCRIPTION_CONTAINERS[i]);
            if (block && textOf(block)) {
                return block;
            }
        }
        return null;
    }

    /**
     * Whatever edge lengths can be established for an image, before fetching it.
     *
     * Two sources, in order of how much they can be trusted: the element's own
     * width/height attributes, then the dimension token in the address. An empty
     * list means nothing could be established, which FR-019 answers explicitly:
     * keep the image.
     */
    function knownEdges(img) {
        const width = parseInt(img.getAttribute('width'), 10);
        const height = parseInt(img.getAttribute('height'), 10);
        if (width > 0 && height > 0) {
            return [width, height];
        }

        const source = img.getAttribute('src') || '';
        // _SR970,300_ and _CR0,0,970,300_ give both edges.
        const both = source.match(/\._(?:SR|CR[0-9]+,[0-9]+,)([0-9]+),([0-9]+)_\./);
        if (both) {
            return [parseInt(both[1], 10), parseInt(both[2], 10)];
        }
        // _SX679_, _SY679_, _UX970_ give one; _SL1500_ gives the *longest*, so a
        // small value there bounds both edges and a large one bounds neither.
        const one = source.match(/\._(?:S[XYL]|U[XY])([0-9]+)_\./);
        if (one) {
            return [parseInt(one[1], 10)];
        }

        if (img.naturalWidth > 0 && img.naturalHeight > 0) {
            return [img.naturalWidth, img.naturalHeight];
        }
        return [];
    }

    /**
     * The images inside a rich description block that are genuinely content.
     *
     * FR-019. A description block is full of spacers, rules and bullet glyphs,
     * and storing those alongside the product's photographs makes the gallery
     * useless to look through. The rule is one line: **drop an image only when
     * some edge we could establish is under 300 pixels.** An image whose
     * dimensions cannot be established at all is kept -- discarding on a guess
     * loses content, keeping on a guess costs one deletion.
     *
     * This filter runs **here, in the browser**, which is the only place the
     * dimensions are knowable before the bytes are fetched. It is also what lets
     * the payload carry one flat image list: the server never learns which image
     * came from the gallery and which from the description, so FR-019's
     * gallery-images-are-exempt carve-out is true without the server being
     * trusted to honour a distinction it cannot see. There is deliberately no
     * second implementation of this rule on the server side.
     */
    function descriptionImages(block) {
        const kept = [];
        const images = block.querySelectorAll('img');

        for (let i = 0; i < images.length; i++) {
            const source = images[i].getAttribute('src') || '';
            if (!/^https?:/.test(source)) {
                continue;
            }
            const edges = knownEdges(images[i]);
            let tooSmall = false;
            for (let j = 0; j < edges.length; j++) {
                if (edges[j] < MIN_DESCRIPTION_EDGE) {
                    tooSmall = true;
                }
            }
            if (!tooSmall) {
                kept.push(withoutTransform(source));
            }
        }

        return kept;
    }

    // ---------------------------------------------------------------
    // Reading the canonical listing rather than the open tab
    // ---------------------------------------------------------------

    /**
     * Fetch and parse `/dp/<ASIN>`, or fall back to the document on screen.
     *
     * FR-002. A tab left open through a few variant clicks silently acquires
     * `?th=1` and shows a different item than the one the address names; the
     * same-origin fetch carries the session and returns the listing the
     * identifier actually means.
     *
     * **Every failure falls back to the live document** -- no identifier in the
     * address, a refused fetch, an unparseable body. That is not defensive
     * decoration, it is FR-007: capturing the open tab is strictly better than
     * capturing nothing.
     *
     * @returns {Promise<{doc: Document, url: string}>} the document read from,
     *          and the address it was read from.
     */
    function canonicalDocument(asin) {
        const here = { doc: document, url: location.href };
        if (!asin) {
            return Promise.resolve(here);
        }

        const canonicalUrl = location.origin + '/dp/' + asin;
        return fetch(canonicalUrl, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                return response.text();
            })
            .then(function (html) {
                const parsed = new DOMParser().parseFromString(html, 'text/html');
                if (!parsed || !parsed.body) {
                    throw new Error('unparseable');
                }
                return { doc: parsed, url: canonicalUrl };
            })
            .catch(function (error) {
                console.warn('[capture-agent] could not read ' + canonicalUrl +
                             ' (' + error + '); reading the open tab instead');
                return here;
            });
    }

    // ---------------------------------------------------------------
    // Transport
    // ---------------------------------------------------------------

    /**
     * POST the payload into a new tab, landing on this app's confirmation page.
     *
     * @param {string} endpoint - this application's /api/capture, absolute.
     * @param {object} listing - the payload, serialized into the hidden field.
     */
    function submitCapture(endpoint, listing) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = endpoint;
        form.target = '_blank';

        const add = function (name, value) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            input.value = value;
            form.appendChild(input);
        };

        add('url', listing.source_url);
        add('listing_title', listing.listing_title || document.title);
        add('listing', JSON.stringify(listing));

        document.body.appendChild(form);
        form.submit();
        form.remove();
    }

    const script = document.currentScript;
    const endpoint = script && script.dataset ? script.dataset.endpoint : null;
    if (!endpoint) {
        // Without an endpoint there is nowhere to send it, and guessing this
        // application's address from a vendor's page is not possible.
        console.error('[capture-agent] no data-endpoint on the script element');
        return;
    }

    const asinMatch = location.pathname.match(ASIN_PATTERN);
    const asin = asinMatch ? asinMatch[1] : null;

    canonicalDocument(asin).then(function (source) {
        submitCapture(endpoint, extract(source.doc, source.url, asin));
    });
})();
