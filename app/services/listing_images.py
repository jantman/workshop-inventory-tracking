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

import logging
import os
from typing import List, Optional
from urllib.parse import unquote, urlparse

import requests

from app.models import ImageCaptureResult
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
        urls: Addresses in the order the agent found them, gallery first.
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
    seen_addresses = set()

    photo_service = PhotoService(storage_backend)
    try:
        for index, url in enumerate(urls):
            # Cheap first pass, and an optimization of the network rather than
            # the correctness rule: the same address twice need not be fetched
            # twice. Correctness is the content hash, further down.
            if url in seen_addresses:
                result.duplicates += 1
                continue
            seen_addresses.add(url)

            try:
                response = requests.get(url, timeout=timeout)
            except requests.RequestException as e:
                logger.info(f"Could not retrieve {url}: {e}")
                result.failed += 1
                continue

            if response.status_code != 200:
                logger.info(f"Could not retrieve {url}: HTTP {response.status_code}")
                result.failed += 1
                continue

            content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip()
            if content_type not in PhotoService.SUPPORTED_TYPES:
                logger.info(f"Skipping {url}: content type {content_type!r} is not supported")
                result.skipped += 1
                continue

            data = response.content
            if len(data) > PhotoService.MAX_FILE_SIZE:
                logger.info(f"Skipping {url}: {len(data)} bytes is over the file size limit")
                result.skipped += 1
                continue

            filename = f"{stem}-{index:02d}{_extension_of(url)}"
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
                logger.info(f"Skipping {url}: {e}")
                result.skipped += 1
                continue
            except RuntimeError as e:
                # Bytes that fetched cleanly but would not decode. Reported as a
                # failure for the same reason as a 404: the operator's next
                # action is identical either way.
                logger.info(f"Could not store {url}: {e}")
                result.failed += 1
                continue

            if attachment is None:
                result.duplicates += 1
            else:
                result.stored += 1
    finally:
        photo_service.close()

    logger.info(
        f"Listing images for product {product_id}: stored {result.stored}, "
        f"duplicates {result.duplicates}, skipped {result.skipped}, "
        f"failed {result.failed}, cap reached {result.cap_reached}"
    )
    return result
