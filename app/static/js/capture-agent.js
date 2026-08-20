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

    // Elements whose text was never prose. `textContent` includes them, which is
    // why a captured A+ description used to arrive carrying a stylesheet and a
    // function body rendered as writing (issue #91). `template` is here for the
    // next reader rather than out of necessity -- the parser puts a template's
    // children in its `content` fragment, so its `textContent` is already ''.
    const NON_CONTENT = 'style, script, noscript, template';

    // What the reader sees as a new paragraph. Matched on `nodeName`, which is
    // upper-case for HTML elements. Deliberately short: `DIV` and `P` dominate
    // A+ markup, everything else worth naming contains one of these, and the
    // fold in `proseFrom` makes a redundant separator invisible anyway.
    const BLOCK_ELEMENTS = {
        P: true, DIV: true, LI: true, TR: true,
        H1: true, H2: true, H3: true, H4: true, H5: true, H6: true
    };

    /**
     * A detached copy of `node` with the non-content elements gone.
     *
     * **The original is never touched.** `canonicalDocument()` falls back to the
     * live `document` whenever the canonical fetch fails, so removing nodes in
     * place would edit the page the operator is looking at (FR-003). Cloning
     * makes the fetched-document path and the fallback path behave identically,
     * which is also what makes the fixture-driven test mean anything.
     *
     * Callers wanting *images* must go on passing the original block:
     * `knownEdges()` reads `img.naturalWidth`, which is 0 on a detached clone,
     * so a clone would silently change which images survive the size filter.
     */
    function contentClone(node) {
        const clone = node.cloneNode(true);
        const junk = clone.querySelectorAll(NON_CONTENT);
        for (let i = 0; i < junk.length; i++) {
            junk[i].remove();
        }
        return clone;
    }

    /**
     * The text of an already-cleaned clone, with the page's line structure kept.
     *
     * A `<br>` becomes one newline and a block boundary becomes a paragraph
     * break, emitted on *both* sides of the element -- which is what makes
     * `Intro<div>Boxed</div>` two paragraphs rather than `IntroBoxed`. The
     * doubling that produces is what step 3 below folds away.
     *
     * **A newline inside a text node is not a line break.** Markup is indented,
     * so a paragraph's own text is full of source newlines the reader never
     * sees; collapsing each text node as it is appended is what guarantees every
     * newline in the result is one this walk deliberately emitted.
     */
    function proseFrom(clone) {
        const parts = [];

        const walk = function (node) {
            const children = node.childNodes;
            for (let i = 0; i < children.length; i++) {
                const child = children[i];
                if (child.nodeType === 3) {  // Node.TEXT_NODE
                    parts.push((child.data || '').replace(/\s+/g, ' '));
                } else if (child.nodeType !== 1) {  // comments and the rest
                    continue;
                } else if (child.nodeName === 'BR') {
                    parts.push('\n');
                } else if (BLOCK_ELEMENTS[child.nodeName]) {
                    parts.push('\n\n');
                    walk(child);
                    parts.push('\n\n');
                } else {
                    walk(child);
                }
            }
        };
        walk(clone);

        // These four run in this order and the order is load-bearing. Step 2
        // must precede step 3, or a line holding nothing but spaces survives the
        // fold and shows up as a blank line the listing never had.
        return parts.join('')
            .replace(/[^\S\n]+/g, ' ')   // 1. spaces and tabs, but not newlines
            .replace(/ *\n */g, '\n')    // 2. so a "blank" line is really empty
            .replace(/\n{3,}/g, '\n\n')  // 3. at most one blank line (FR-007)
            .trim();                     // 4.
    }

    /** Text with the page's line structure kept -- for descriptions and values. */
    function proseOf(node) {
        return node ? proseFrom(contentClone(node)) : '';
    }

    /**
     * Trimmed, whitespace-collapsed text, or '' -- never null, never a throw.
     *
     * Same contract as it has always had: one line, runs collapsed, trimmed.
     * Only the *content* changed -- it no longer reports a stylesheet as prose.
     * Defined through `proseOf` so the stripping has exactly one implementation;
     * the single-line guarantee is what `brandFrom`'s patterns and the
     * specification-name fold both depend on (FR-009).
     */
    function textOf(node) {
        return proseOf(node).replace(/\s+/g, ' ').trim();
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

    // "About this item": the bullets Amazon writes above the detail tables, and
    // on some listings the only place a physical fact appears at all. Every
    // dimension B01N4OSKWE publishes is in its five bullets and in no table on
    // the page, which is why issue #92 called the capture of it an empty record.
    //
    // **Not a member of the list above, and it could not be.** `rowsFrom`'s two
    // shapes are a two-cell table row and a bullet with a bold name span; an
    // About-this-item bullet is neither, so adding this selector there would
    // read the container and find nothing in it. It needs its own reader.
    //
    // The container holds more than the bullets -- see `bulletsRow`.
    const BULLET_CONTAINER = '#feature-bullets';

    // The row name, matching the heading the listing itself puts on the section.
    // Folded case-insensitively by both merges, like every other captured name.
    const BULLET_ROW_NAME = 'About this item';

    /** Trim the punctuation Amazon puts between a bullet's name and its value. */
    function tidyName(name) {
        // The bidi marks are literally in the markup: "Date First Available ‏ : ‎".
        return name.replace(/[‎‏؜]/g, '').replace(/[\s:]+$/, '').trim();
    }

    /** Name/value pairs out of one container, whichever of the shapes it uses. */
    function rowsFrom(container) {
        const rows = [];

        // Shape one: a two-cell table row, th/td or td/td.
        //
        // The name is read single-line and the value is not. A name with a
        // newline in it would be two spellings of one name to the two folds that
        // follow -- `specificationsFrom`'s and `merge_specifications`' -- and a
        // value with one is a cell the listing genuinely showed on two lines.
        const tableRows = container.querySelectorAll('tr');
        for (let i = 0; i < tableRows.length; i++) {
            const cells = tableRows[i].querySelectorAll('th, td');
            if (cells.length === 2) {
                rows.push({ name: tidyName(textOf(cells[0])), value: proseOf(cells[1]) });
            }
        }

        // Shape two: a detail bullet, where the name is the bold span and the
        // value is whatever is left over.
        //
        // "Left over" used to mean `whole.slice(textOf(bold).length)`, which
        // assumed the name's text was a character-for-character prefix of the
        // item's. That held only while both sides were single-line, and it would
        // have failed by silently slicing at the wrong offset rather than by
        // throwing. Removing the node says the same thing and cannot drift.
        const items = container.querySelectorAll('li');
        for (let i = 0; i < items.length; i++) {
            const bold = items[i].querySelector('.a-text-bold');
            if (!bold) {
                continue;
            }
            const name = tidyName(textOf(bold));
            const remainder = contentClone(items[i]);
            const boldInClone = remainder.querySelector('.a-text-bold');
            if (boldInClone) {
                boldInClone.remove();
            }
            const value = proseFrom(remainder).replace(/^[\s:]+/, '');
            if (name && value) {
                rows.push({ name: name, value: value });
            }
        }

        return rows;
    }

    /**
     * The listing's "About this item" bullets as one row, or null (issue #92).
     *
     * **Read from the `li` elements, never from the container's own text.**
     * `#feature-bullets` carries an `<h2>About this item</h2>` heading and, after
     * the list, a `<div>` holding "See more product details" -- both inside the
     * container and both outside the `<ul>`. A reader taking the container's
     * `textContent` captures them: on a real listing it begins "About this item
     * Country of Manufacture: CHINA...". Scoping to `li` excludes both for free,
     * and excludes nothing a bullet contains.
     *
     * **There is deliberately no visibility test here, and there could not be
     * one.** Issue #92 expected a hidden "See more product details" list item;
     * on all three listings read on 2026-08-19 it is a visible sibling `div`
     * instead, and no bullet was hidden by anything. That is just as well,
     * because `canonicalDocument()` hands this a `DOMParser` document: detached,
     * unstyled, without layout. `offsetHeight` is 0 for every element in it and
     * `getComputedStyle` reports the UA default rather than what Amazon's CSS
     * would produce, so "is the shopper shown this" cannot be asked on this side
     * of the fetch at all. Excluding the furniture is structural or it does not
     * happen.
     *
     * Bullets are joined with **one** newline rather than two: they are list
     * items, not paragraphs, and `proseFrom` already emits paragraph breaks for
     * the block structure *within* a bullet.
     *
     * Returns null rather than a row with an empty value. `_payload_specifications`
     * would drop such a row on arrival and nobody would ever hear about it.
     */
    function bulletsRow(doc) {
        const container = doc.querySelector(BULLET_CONTAINER);
        if (!container) {
            return null;
        }

        const lines = [];
        const items = container.querySelectorAll('li');
        for (let i = 0; i < items.length; i++) {
            // A nested list belongs to the bullet containing it, not to the
            // page. `querySelectorAll` returns the outer and inner items both,
            // and taking both would emit the nested text twice -- once inside
            // its parent's prose and once on a line of its own.
            const parent = items[i].parentElement;
            if (parent && parent.closest('li')) {
                continue;
            }
            const line = proseOf(items[i]);
            if (line) {
                lines.push(line);
            }
        }

        if (!lines.length) {
            return null;
        }
        return { name: BULLET_ROW_NAME, value: lines.join('\n') };
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

        // The bullets lead, as they do on the page -- and they are seeded into
        // the fold rather than merely pushed onto the list. A listing naming a
        // detail-table row "About this item" as well would otherwise yield two
        // rows of one name, which is the one duplicate neither this fold nor
        // merge_specifications downstream would catch. Seeding also settles the
        // collision the right way round: what survives is the bullets.
        const bullets = bulletsRow(doc);
        if (bullets) {
            entries.push(bullets);
            seen[bullets.name.toLowerCase()] = true;
        }

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

        const description = descriptionBlocks(doc);
        if (description.length) {
            // Uncapped, and sent whole. b1a0c0d10009 widened the column it lands
            // in to 16,777,215 bytes precisely so there is nothing to truncate
            // against and FR-006 holds without an exception.
            // Text from the **first** block, images from **all** of them. 007
            // FR-005 stands for the text -- whichever form the description takes,
            // never a requirement that both be present -- and merging prose
            // across nested containers would simply duplicate it. Images are the
            // opposite case, and are what the `seen` map above is for
            // (021 C-15, C-17).
            set('description_text', descriptionProse(description[0]));
            // The *original* blocks, not clones: `knownEdges()` falls back to
            // `img.naturalWidth`, which is 0 on anything detached.
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
    // sampled listings one way and three the other, and **never both** -- so the
    // *text* is read from whichever is present rather than from both combined
    // (FR-005). 021 split the two: the **images** are gathered from every
    // container, because a listing turned out to be able to carry more than one
    // A+ region and reading only the first dropped the product's own pictures.
    //
    // The list itself is unchanged since 007, and that is the point:
    // `#aplus_feature_div` was always here. It was unreachable, because the
    // `#aplus` ahead of it matched a *different* element of the same id -- see
    // `descriptionBlocks()`.
    const DESCRIPTION_CONTAINERS = ['#productDescription', '#aplus', '#aplus_feature_div'];

    // The vendor's *other* products. Amazon renders the "From the brand"
    // carousel inside this container, and on B0FX4PDW6M that container holds its
    // own `<div id="aplus">` -- a second element carrying an id the page already
    // uses, sitting *first* in document order. `querySelector('#aplus')`
    // therefore returned the brand story, `descriptionBlock()` returned with it,
    // and `#aplus_feature_div` was never reached. One lookup that captured 126
    // cross-sell images and dropped the product's own description along with its
    // specification table. That is the whole of issue #94.
    //
    // Excluded by position, never by size. These are large, well-produced
    // product photographs that clear 300px as comfortably as real content does;
    // no dimension test can tell you it is the wrong product. 021 FR-005 forbids
    // moving `MIN_DESCRIPTION_EDGE` to chase them.
    const CROSS_SELL_CONTAINER = '#aplusBrandStory_feature_div';

    /**
     * Whether a node belongs to the brand-story carousel.
     *
     * Two of the three listings probed on 2026-08-19 carry this container
     * present but **empty**, which is why the defect stayed invisible: it bites
     * only when the vendor has actually published a brand story. A page with no
     * such container must behave exactly like a page carrying an empty one, so a
     * missing container reads as "nothing here is cross-sell" rather than as an
     * error -- and this cannot throw for any document (021 C-2, C-19).
     */
    function isCrossSell(node) {
        return !!(node && node.closest && node.closest(CROSS_SELL_CONTAINER));
    }

    // A deferred-loading placeholder: an address that resolves, to a 1x1 grey
    // GIF rather than to a picture of anything. Amazon parks this in `src` while
    // the real address waits in `data-src` for the module to scroll into view --
    // which never happens here, because `canonicalDocument()` yields a document
    // that is never laid out.
    // Matched as a *filename*, not as a substring: `grey-pixel` anywhere in the
    // address would also reject a vendor's photograph of grey pixel art, and
    // silently dropping a content image is the exact class of bug this whole
    // change exists to fix.
    const PLACEHOLDER_ADDRESS = /\/(?:grey|transparent)-pixel\.gif(?:[?#]|$)/;

    /**
     * The address an image will really load, or ''.
     *
     * `data-src` in preference to `src`, then nothing at all for a placeholder.
     *
     * Reading `data-src` recovers no image *today*: Amazon pairs every lazy
     * image with a `<noscript>` twin carrying the same address in a plain `src`,
     * and `DOMParser` parses noscript content into real elements, so the address
     * is reachable either way. It is here for the day the twins stop being
     * emitted.
     *
     * Rejecting the placeholder is not optional. `/^https?:/` passes on it, it
     * declares no dimensions, so FR-019's keep-on-unknown rule *kept* it -- and
     * every A+ listing with a lazy image has been storing a 1x1 grey GIF as a
     * product photograph since 007 shipped. Nothing downstream catches it:
     * `.gif` is a legitimate product image type and the server cannot know that
     * this one is a placeholder. Only the browser can (021 C-4).
     */
    function addressOf(img) {
        const source = img.getAttribute('data-src') || img.getAttribute('src') || '';
        return PLACEHOLDER_ADDRESS.test(source) ? '' : source;
    }

    /**
     * Every description block the listing carries, in container-list order.
     *
     * `querySelectorAll`, and **every** match rather than the first: a page may
     * carry two elements with `id="aplus"`, and the second is invisible to a
     * single-element lookup. That is not hypothetical -- B0FX4PDW6M does it, and
     * reading only the first is issue #94 (021 C-6).
     *
     * Ordered by `DESCRIPTION_CONTAINERS`, then by document order within each
     * selector -- deliberately **not** whole-document order. The list's order is
     * a precedence: 007 put `#productDescription` first so the plain form wins
     * if a page ever carries both, and sorting by position in the document would
     * silently hand that precedence to whichever block the page laid out first.
     *
     * Blocks may contain one another -- `#aplus` nested inside
     * `#aplus_feature_div` is the ordinary shape and yields the same element
     * twice. Deduplication is the caller's job, and the caller already has a
     * `seen` map (021 C-9).
     *
     * The `textOf(block)` test is what earns **014** FR-004 -- a block whose
     * remaining text is empty after stripping carries no description, and the
     * reader moves on -- and it does so through the stripping rather than
     * through any code here: a block whose only text was a stylesheet and a
     * script now reads as '', fails the test, and is skipped. It is tested
     * rather than assumed precisely because it is behavior emerging from a
     * change somewhere else. (The bare `FR-` references in this file are 007's;
     * this one is not, and has been misread as 007 FR-004, which is about
     * gallery resolution.)
     */
    /**
     * The description block's prose, with any cross-sell region taken out.
     *
     * `descriptionBlocks()` drops a block that *is* inside the carousel; this
     * drops a carousel nested inside a block that is otherwise the real
     * description. `descriptionImages()` already covers that shape per image,
     * and without this the text path did not -- so a nested carousel's prose
     * walked into `description_text` and reproduced the text half of #94
     * (021 FR-011).
     *
     * Its own function rather than a rule inside `contentClone`, which
     * `brandFrom`, `priceFrom` and the specification readers all share and none
     * of which should learn what a brand story is.
     */
    function descriptionProse(block) {
        const clone = contentClone(block);
        const carousels = clone.querySelectorAll(CROSS_SELL_CONTAINER);
        for (let i = 0; i < carousels.length; i++) {
            carousels[i].remove();
        }
        return proseFrom(clone);
    }

    function descriptionBlocks(doc) {
        const blocks = [];
        for (let i = 0; i < DESCRIPTION_CONTAINERS.length; i++) {
            const found = doc.querySelectorAll(DESCRIPTION_CONTAINERS[i]);
            for (let j = 0; j < found.length; j++) {
                if (textOf(found[j]) && !isCrossSell(found[j])) {
                    blocks.push(found[j]);
                }
            }
        }
        return blocks;
    }

    /**
     * Whatever edge lengths can be established for an image, before fetching it.
     *
     * Two sources, in order of how much they can be trusted: the element's own
     * width/height attributes, then the dimension token in the address. An empty
     * list means nothing could be established, which FR-019 answers explicitly:
     * keep the image.
     *
     * **021 does not change the rule** -- same two patterns, same threshold, same
     * keep-on-unknown clause. The address is now passed in rather than read from
     * `src`, because for a deferred-loading image `src` names a grey placeholder
     * and its token, if it had one, would describe the wrong picture. Measuring
     * the image you are actually deciding about is the same rule applied to the
     * right string.
     */
    function knownEdges(img, address) {
        const width = parseInt(img.getAttribute('width'), 10);
        const height = parseInt(img.getAttribute('height'), 10);
        if (width > 0 && height > 0) {
            return [width, height];
        }

        const source = address || '';
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

        // Only when the address we are deciding about is the one the element
        // actually loaded. For a deferred-loading image they differ: `src` holds
        // the grey placeholder and `address` the real picture, so on the live
        // document -- `canonicalDocument()`'s fallback, a first-class path under
        // FR-007 -- this would report the placeholder's 1x1 and drop the very
        // image 021 exists to keep. Detached documents report 0 and never reach
        // the question, which is why the suite cannot see this: it is not
        // observable on the canonical-fetch path every test takes.
        if (source === (img.getAttribute('src') || '') &&
                img.naturalWidth > 0 && img.naturalHeight > 0) {
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
    function descriptionImages(blocks) {
        const kept = [];

        for (let b = 0; b < blocks.length; b++) {
            const images = blocks[b].querySelectorAll('img');

            for (let i = 0; i < images.length; i++) {
                // Position first, and **before** any size test. A cross-sell
                // image is a real product photograph that clears 300px on both
                // edges; the only thing wrong with it is which product it shows,
                // which no dimension can tell you (021 C-10).
                //
                // Not redundant with the block-level exclusion in
                // `descriptionBlocks()`. That one keeps the carousel's *prose*
                // out of the description; this one covers a listing that nests
                // the carousel inside the real description block. They answer
                // different questions, and 021 FR-006 needs the narrower one.
                if (isCrossSell(images[i])) {
                    continue;
                }
                const source = addressOf(images[i]);
                if (!/^https?:/.test(source)) {
                    continue;
                }
                const edges = knownEdges(images[i], source);
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
