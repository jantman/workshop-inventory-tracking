"""
Retrieve the images a capture named, and attach them to the product.

The only place in ``app/`` that makes an outbound HTTP request to a third party,
and the reason the capture write is split in two. ``CatalogService.capture_order``
does the fast transactional half -- product, purchase, specification rows -- and
this does the slow, partially-failing half. Putting these seconds of network I/O
inside that transaction would mean one refused image rolling back a purchase,
which is the opposite of FR-020.

**Nothing here raises for a per-image problem.** Every failure mode is a counter
on ``ImageCaptureResult``. That is what allows the capture to have already
succeeded before the first image is even attempted: the specifications and the
description are the point too, and an unreachable CDN must not cost the operator
the purchase they just made.

Not a class -- there is no state to hold. Not a retry loop -- a failed image is
reported, and the operator can add it by hand or capture again. Not concurrent;
see research.md, "Why image retrieval is synchronous".

**No URL allow-list, no host validation, no SSRF mitigation.** The addresses come
from a page the operator is looking at, submitted by the operator, on a machine
only the operator can reach. There is no adversary in this system to build a wall
against. What bounds are here -- a timeout, the existing 20 MB file limit, the
existing MIME allow-list, the per-product cap -- are there because bad data
breaks the inventory, which is the constitution's stated reason to validate.
"""

import base64
import binascii
import logging
import os
from typing import List, Optional
from urllib.parse import unquote, urlparse

import requests

from app.models import PDF_DATA_PREFIX, ImageCaptureResult
from app.photo_service import PhotoService

logger = logging.getLogger(__name__)

# Amazon's own image filenames are opaque hashes, so the stored name is derived.
# The attachment card shows filenames today; FR-013 makes it a thumbnail grid,
# but the filename is still what a download is called.
_DEFAULT_EXTENSION = '.jpg'
_KNOWN_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf'}


def _extension_of(url: str) -> str:
    """The address's file extension, when it has a plausible one."""
    path = unquote(urlparse(url).path)
    extension = os.path.splitext(path)[1].lower()
    return extension if extension in _KNOWN_EXTENSIONS else _DEFAULT_EXTENSION


def _label(url: str) -> str:
    """How an address is named in the log.

    An inline PDF is the whole file, a hundred-odd kilobytes of base64; logging
    it would bury every line around it.
    """
    if url.startswith(PDF_DATA_PREFIX):
        return f"an inline PDF ({len(url) - len(PDF_DATA_PREFIX)} base64 characters)"
    return url


def store_listing_images(
    product_id: int,
    urls: List[str],
    storage_backend,
    timeout: float = 10.0,
    vendor_item_id: Optional[str] = None,
) -> ImageCaptureResult:
    """Retrieve captured image addresses and attach them to a product.

    Args:
        product_id: The product the images belong to.
        urls: Addresses in the order the agent found them, gallery first. An
            entry may instead be an inline PDF (``PDF_DATA_PREFIX``), which is
            decoded rather than requested.
        storage_backend: Passed to PhotoService rather than constructed here,
            matching how the routes already build it.
        timeout: Per-request, so one unresponsive address cannot hold the
            confirmation POST open indefinitely. A parameter with a default
            rather than a configuration setting -- a knob for a value nobody
            will change is speculative generality. It is a parameter at all so
            the tests can assert it reaches requests.get.
        vendor_item_id: Used to name the stored files.

    Returns:
        Counts of what happened. See data-model.md, "Image storage path".
    """
    result = ImageCaptureResult()
    if not urls:
        return result

    stem = vendor_item_id or 'listing'
    # What each address came to the first time it was named. An address named
    # twice is fetched once -- that is a network optimization -- but it must
    # still be *counted* as whatever it actually came to, or the tally reports
    # something that did not happen. A second mention of an unreachable address
    # is a second failure, not a duplicate of anything.
    outcomes = {}

    photo_service = PhotoService(storage_backend)
    try:
        for index, url in enumerate(urls):
            previous = outcomes.get(url)
            if previous is not None:
                # A second copy of something stored is a duplicate; a second
                # mention of anything else repeats that outcome.
                repeat = 'duplicates' if previous == 'stored' else previous
                setattr(result, repeat, getattr(result, repeat) + 1)
                continue

            label = _label(url)

            if url.startswith(PDF_DATA_PREFIX):
                # 051: bytes the agent fetched in the page, because the vendor
                # refuses them to anything without the operator's session.
                # Nothing to request -- decode, then the same checks as below.
                try:
                    data = base64.b64decode(url[len(PDF_DATA_PREFIX):], validate=True)
                except (binascii.Error, ValueError) as e:
                    logger.info(f"Could not decode {label}: {e}")
                    result.failed += 1
                    outcomes[url] = 'failed'
                    continue
                content_type = 'application/pdf'
            else:
                try:
                    response = requests.get(url, timeout=timeout)
                except requests.RequestException as e:
                    logger.info(f"Could not retrieve {label}: {e}")
                    result.failed += 1
                    outcomes[url] = 'failed'
                    continue

                if response.status_code != 200:
                    logger.info(f"Could not retrieve {label}: HTTP {response.status_code}")
                    result.failed += 1
                    outcomes[url] = 'failed'
                    continue

                content_type = (
                    (response.headers.get('Content-Type') or '').split(';')[0].strip()
                )
                data = response.content

            if content_type not in PhotoService.SUPPORTED_TYPES:
                logger.info(f"Skipping {label}: content type {content_type!r} is not supported")
                result.skipped += 1
                outcomes[url] = 'skipped'
                continue

            if len(data) > PhotoService.MAX_FILE_SIZE:
                logger.info(f"Skipping {label}: {len(data)} bytes is over the file size limit")
                result.skipped += 1
                outcomes[url] = 'skipped'
                continue

            # A PDF is named for what it is: an inline one has no path to read an
            # extension from, and a vendor's address need not end in .pdf.
            extension = '.pdf' if content_type == 'application/pdf' else _extension_of(url)
            filename = f"{stem}-{index:02d}{extension}"
            try:
                attachment = photo_service.upload_product_attachment_if_new(
                    product_id, data, filename, content_type
                )
            except ValueError as e:
                if 'attachments allowed' in str(e):
                    # FR-022: stop cleanly and say so rather than grinding
                    # through the rest of the gallery refusing each one.
                    logger.info(f"Attachment cap reached on product {product_id}; stopping")
                    result.cap_reached = True
                    break
                logger.info(f"Skipping {label}: {e}")
                result.skipped += 1
                outcomes[url] = 'skipped'
                continue
            except RuntimeError as e:
                # Bytes that fetched cleanly but would not decode. Reported as a
                # failure for the same reason as a 404: the operator's next
                # action is identical either way.
                logger.info(f"Could not store {label}: {e}")
                result.failed += 1
                outcomes[url] = 'failed'
                continue

            outcomes[url] = 'duplicates' if attachment is None else 'stored'
            if attachment is None:
                result.duplicates += 1
            else:
                result.stored += 1
                if content_type == 'application/pdf':
                    result.pdfs += 1
    finally:
        photo_service.close()

    logger.info(
        f"Listing images for product {product_id}: stored {result.stored} "
        f"({result.pdfs} PDF), "
        f"duplicates {result.duplicates}, skipped {result.skipped}, "
        f"failed {result.failed}, cap reached {result.cap_reached}"
    )
    return result
