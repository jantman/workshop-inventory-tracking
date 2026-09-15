# Verification: Feature 044

## Red before the fix (T004)

The SC-001 regression test, `tests/unit/test_order_product_details.py::TestTheReportedFailure`,
was written before any production change and run against the unchanged code:

```text
tests/unit/test_order_product_details.py::TestTheReportedFailure::test_a_listing_capture_after_its_order_fills_the_product_in FAILED [100%]

tests/unit/test_order_product_details.py:114: in test_a_listing_capture_after_its_order_fills_the_product_in
    assert response.status_code == 302
E   assert 200 == 302
E    +  where 200 = <WrapperTestResponse streamed [200 OK]>.status_code
============================== 1 failed in 0.55s ===============================
```

The listing capture of an item an order had already captured was re-rendered with its two
questions (200) rather than filling the product in. That is issue #156: no answer to either
question avoided a second purchase.
