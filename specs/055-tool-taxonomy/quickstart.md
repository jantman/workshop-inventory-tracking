# Quickstart: validating 055

```bash
N="PATH=$HOME/.pyenv/versions/3.13.12/bin:$PATH /home/jantman/GIT/workshop-inventory-tracking/venv/bin/nox"
env $N -s tests                                           # shape + record agreement
env $N -r -s e2e -- tests/e2e/test_category_taxonomy.py   # offering unoccupied branches
```

Expected:

- `TestCategoryPathShape`, `TestSpecificationKeyShape` and `TestAgreementWithTheRecord` all
  pass with six roots.
- The new probe test passes: `tools/taps & dies/taps` is offered, and so are `Chamfer` and
  `Shank`.

Manually, in a running app with an empty catalog:

1. Go to Products → Add. In the Category field type `tools/dr`. `tools/drill bits/twist drills`
   is suggested.
2. In a specification name field type `Len`. Both `Length` and `Length Series` are suggested.
3. Open Products → Categories. `adhesives & chemicals`, `mechanical` and `tools` are listed
   with count 0.

Record check: every probe in spec.md, User Story 3, resolves from `docs/category-taxonomy.md`
alone.
