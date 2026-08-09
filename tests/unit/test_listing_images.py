"""
Unit tests for retrieving the images a capture named.

Every branch of ``store_listing_images`` with ``requests.get`` patched, because
the one property that matters more than any individual branch is that **none of
them raise**: the capture has already succeeded by the time the first image is
attempted, and FR-020 says an unreachable CDN must not cost the operator the
purchase they just made.

The unit suite blocks the network (``--blockage``), so an unmocked ``requests.get``
fails loudly rather than reaching out. That is a feature, and the reason there is
no network marker anywhere in this file.
"""

import io
from unittest.mock import patch

import pytest
from PIL import Image

from app.catalog_service import CatalogService
from app.photo_service import PhotoService
from app.services.listing_images import store_listing_images

GALLERY = 'https://m.media-amazon.com/images/I/'


def jpeg_bytes(size=(40, 30), colour=(10, 120, 200)):
    """A real JPEG -- the service decodes what it is given"""
    buffer = io.BytesIO()
    Image.new('RGB', size, colour).save(buffer, format='JPEG')
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, content=b'', status_code=200, content_type='image/jpeg'):
        self.content = content
        self.status_code = status_code
        self.headers = {'Content-Type': content_type}


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def product(service):
    return service.create_product(description='12V 3A PSU')


@pytest.fixture
def photos(test_storage):
    photo_service = PhotoService(test_storage)
    yield photo_service
    photo_service.close()


def store(product_id, urls, storage, responses, **kwargs):
    """Run the fetcher with requests.get answering from `responses`."""
    def fake_get(url, **request_kwargs):
        answer = responses[url]
        if isinstance(answer, Exception):
            raise answer
        fake_get.timeouts.append(request_kwargs.get('timeout'))
        return answer

    fake_get.timeouts = []

    with patch('app.services.listing_images.requests.get', side_effect=fake_get) as mock:
        result = store_listing_images(product_id, urls, storage, **kwargs)
    result.calls = mock.call_args_list
    return result


class TestRetrievingListingImages:
    def test_the_ordinary_case_stores_each_one(self, test_storage, product, photos):
        urls = [f'{GALLERY}a.jpg', f'{GALLERY}b.jpg']
        result = store(product.id, urls, test_storage, {
            urls[0]: FakeResponse(jpeg_bytes(colour=(1, 2, 3))),
            urls[1]: FakeResponse(jpeg_bytes(colour=(4, 5, 6))),
        })

        assert result.stored == 2
        assert (result.failed, result.skipped, result.duplicates) == (0, 0, 0)
        assert result.cap_reached is False
        assert len(photos.get_product_attachments(product.id)) == 2

    def test_the_timeout_is_actually_passed_to_requests(self, test_storage, product):
        """A timeout that is not passed is a POST that can hang forever"""
        url = f'{GALLERY}a.jpg'
        result = store(
            product.id, [url], test_storage, {url: FakeResponse(jpeg_bytes())},
            timeout=2.5,
        )

        assert result.calls[0].kwargs['timeout'] == 2.5

    def test_a_timeout_is_counted_and_the_rest_still_land(self, test_storage, product):
        import requests

        urls = [f'{GALLERY}a.jpg', f'{GALLERY}b.jpg']
        result = store(product.id, urls, test_storage, {
            urls[0]: requests.Timeout('too slow'),
            urls[1]: FakeResponse(jpeg_bytes()),
        })

        assert result.failed == 1
        assert result.stored == 1

    def test_a_connection_failure_is_counted_rather_than_raised(self, test_storage, product):
        import requests

        url = f'{GALLERY}a.jpg'
        result = store(product.id, [url], test_storage, {
            url: requests.ConnectionError('no route to host'),
        })

        assert result.failed == 1
        assert result.stored == 0

    def test_a_non_200_is_counted(self, test_storage, product):
        """A stripped transform token that 404s lands here, and is not retried"""
        urls = [f'{GALLERY}a.jpg', f'{GALLERY}b.jpg']
        result = store(product.id, urls, test_storage, {
            urls[0]: FakeResponse(b'', status_code=404),
            urls[1]: FakeResponse(jpeg_bytes()),
        })

        assert result.failed == 1
        assert result.stored == 1

    def test_an_unsupported_content_type_is_skipped(self, test_storage, product):
        urls = [f'{GALLERY}a.svg', f'{GALLERY}b.jpg']
        result = store(product.id, urls, test_storage, {
            urls[0]: FakeResponse(b'<svg/>', content_type='image/svg+xml'),
            urls[1]: FakeResponse(jpeg_bytes()),
        })

        assert result.skipped == 1
        assert result.stored == 1

    def test_a_charset_on_the_content_type_does_not_confuse_it(self, test_storage, product):
        url = f'{GALLERY}a.jpg'
        result = store(product.id, [url], test_storage, {
            url: FakeResponse(jpeg_bytes(), content_type='image/jpeg; charset=binary'),
        })

        assert result.stored == 1

    def test_a_body_over_the_file_size_limit_is_skipped(self, test_storage, product):
        url = f'{GALLERY}huge.jpg'
        oversize = b'\xff' * (PhotoService.MAX_FILE_SIZE + 1)
        result = store(product.id, [url], test_storage, {url: FakeResponse(oversize)})

        assert result.skipped == 1
        assert result.stored == 0

    def test_the_same_address_twice_is_fetched_once(self, test_storage, product):
        """Network economy. Correctness is the hash, asserted below."""
        url = f'{GALLERY}a.jpg'
        result = store(product.id, [url, url], test_storage, {
            url: FakeResponse(jpeg_bytes()),
        })

        assert len(result.calls) == 1
        assert result.stored == 1
        assert result.duplicates == 1

    def test_a_repeated_address_that_failed_is_not_reported_as_a_duplicate(
        self, test_storage, product
    ):
        """The address-level pass must not invent a duplicate of nothing.

        An address named twice is fetched once, which is a network economy. What
        it *counts* as has to be what actually happened to it: reporting "1 could
        not be retrieved; 1 already stored" for a broken address named twice
        tells the operator something is on the product when nothing is.
        """
        import requests

        url = f'{GALLERY}gone.jpg'
        result = store(product.id, [url, url], test_storage, {
            url: requests.ConnectionError('no route to host'),
        })

        assert len(result.calls) == 1
        assert result.failed == 2
        assert result.duplicates == 0
        assert result.stored == 0

    def test_a_repeated_address_that_was_skipped_stays_skipped(self, test_storage, product):
        url = f'{GALLERY}a.svg'
        result = store(product.id, [url, url], test_storage, {
            url: FakeResponse(b'<svg/>', content_type='image/svg+xml'),
        })

        assert len(result.calls) == 1
        assert result.skipped == 2
        assert result.duplicates == 0

    def test_every_address_is_accounted_for_exactly_once(self, test_storage, product):
        """The tally has to add up, or the summary and the flash disagree"""
        import requests

        urls = [
            f'{GALLERY}good.jpg',
            f'{GALLERY}good.jpg',      # duplicate of a stored image
            f'{GALLERY}gone.jpg',
            f'{GALLERY}gone.jpg',      # repeat of a failure, not a duplicate
            f'{GALLERY}wrong.svg',
        ]
        result = store(product.id, urls, test_storage, {
            urls[0]: FakeResponse(jpeg_bytes()),
            urls[2]: requests.Timeout('too slow'),
            urls[4]: FakeResponse(b'<svg/>', content_type='image/svg+xml'),
        })

        assert (result.stored, result.duplicates, result.failed, result.skipped) == (
            1, 1, 2, 1
        )
        assert (
            result.stored + result.duplicates + result.failed + result.skipped
        ) == len(urls)

    def test_identical_bytes_at_two_addresses_are_stored_once(self, test_storage, product):
        """FR-018: judged by content, because a vendor serves one file many ways"""
        urls = [f'{GALLERY}a._AC_SL1500_.jpg', f'{GALLERY}a._SX679_.jpg']
        same = jpeg_bytes()
        result = store(product.id, urls, test_storage, {
            urls[0]: FakeResponse(same),
            urls[1]: FakeResponse(same),
        })

        assert len(result.calls) == 2
        assert result.stored == 1
        assert result.duplicates == 1

    def test_an_image_already_on_the_product_is_not_stored_again(
        self, test_storage, product, photos
    ):
        """The across-captures half of FR-018, which is the same mechanism"""
        same = jpeg_bytes()
        photos.upload_product_attachment(product.id, same, 'by-hand.jpg', 'image/jpeg')

        url = f'{GALLERY}a.jpg'
        result = store(product.id, [url], test_storage, {url: FakeResponse(same)})

        assert result.stored == 0
        assert result.duplicates == 1
        assert len(photos.get_product_attachments(product.id)) == 1

    def test_the_cap_stops_it_cleanly_and_says_so(self, test_storage, product, photos):
        """FR-022: stop and report, never truncate silently"""
        for index in range(PhotoService.MAX_ATTACHMENTS_PER_PRODUCT - 1):
            photos.upload_product_attachment(
                product.id, jpeg_bytes(colour=(index, 0, 0)), f'{index}.jpg', 'image/jpeg'
            )

        urls = [f'{GALLERY}{n}.jpg' for n in range(4)]
        result = store(product.id, urls, test_storage, {
            url: FakeResponse(jpeg_bytes(colour=(200, n, 5)))
            for n, url in enumerate(urls)
        })

        assert result.stored == 1
        assert result.cap_reached is True
        # It stopped rather than grinding through the rest refusing each one.
        assert len(result.calls) == 2
        assert len(photos.get_product_attachments(product.id)) == (
            PhotoService.MAX_ATTACHMENTS_PER_PRODUCT
        )

    def test_bytes_that_will_not_decode_are_counted_rather_than_raised(
        self, test_storage, product
    ):
        url = f'{GALLERY}a.jpg'
        result = store(product.id, [url], test_storage, {
            url: FakeResponse(b'this is not a JPEG at all'),
        })

        assert result.failed == 1
        assert result.stored == 0

    def test_an_empty_list_does_nothing_and_touches_no_network(self, test_storage, product):
        result = store(product.id, [], test_storage, {})

        assert result.stored == 0
        assert result.calls == []

    def test_the_filename_is_derived_from_the_item_id(self, test_storage, product, photos):
        """Amazon's own filenames are opaque hashes"""
        urls = [f'{GALLERY}71aBcDeF.jpg', f'{GALLERY}81zYxWvU.png']
        result = store(
            product.id, urls, test_storage,
            {
                urls[0]: FakeResponse(jpeg_bytes(colour=(9, 9, 9))),
                urls[1]: FakeResponse(jpeg_bytes(colour=(8, 8, 8)), content_type='image/png'),
            },
            vendor_item_id='B0CKXJLP4B',
        )

        assert result.stored == 2
        names = [a.photo.filename for a in photos.get_product_attachments(product.id)]
        assert names == ['B0CKXJLP4B-00.jpg', 'B0CKXJLP4B-01.png']

    def test_without_an_item_id_the_files_are_still_named(self, test_storage, product, photos):
        url = f'{GALLERY}71aBcDeF.jpg'
        store(product.id, [url], test_storage, {url: FakeResponse(jpeg_bytes())})

        assert photos.get_product_attachments(product.id)[0].photo.filename == 'listing-00.jpg'


class TestTheServerDoesNotReFilterBySize:
    """FR-019's filter has exactly one home, and it is not here.

    It runs in the agent, where an image's dimensions are knowable before it is
    fetched and where gallery images can be exempted from it. Two implementations
    of one rule is how that exemption silently stops being an exemption, so this
    asserts the absence rather than leaving it to be assumed.
    """

    def test_a_tiny_image_the_agent_sent_is_stored_without_argument(
        self, test_storage, product, photos
    ):
        url = f'{GALLERY}spacer.jpg'
        result = store(product.id, [url], test_storage, {
            url: FakeResponse(jpeg_bytes(size=(1, 1))),
        })

        assert result.stored == 1
        assert result.skipped == 0
        assert len(photos.get_product_attachments(product.id)) == 1
