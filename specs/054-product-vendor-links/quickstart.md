# Quickstart: Vendor Links on the Product Page

## Automated

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e      # ~20 min; run detached
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless screenshots_verify
```

`tests/unit/test_vendor_page_links.py` covers each vendor's address, both identifier types,
de-duplication, encoding, unsupported vendors and the absent row.
`tests/e2e/test_product_vendor_links.py` opens a seeded product page and checks each link's
`href`, `target` and `rel`.

## Manual

1. Open a product carrying an Amazon ASIN → Details shows **Vendor Pages: Amazon <ASIN>**
   linking to `https://www.amazon.com/dp/<ASIN>`; clicking opens a new tab.
2. A product with a McMaster-Carr part number → `https://www.mcmaster.com/<part>/`.
3. A product with a DigiKey part number → DigiKey's keyword search, which redirects to the
   part's page.
4. A product with only an MPN → no Vendor Pages row.
