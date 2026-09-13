# Contract: Material Alias Surfaces

These are the three user-facing surfaces this feature touches, and what each must do once it
ships.

## 1. `GET /admin/materials`: taxonomy tree (HTML)

For each `.taxonomy-node[data-name="<material name>"]` whose material has one or more aliases,
the node's own heading contains:

```text
(aliases: <alias 1>, <alias 2>, ..., <alias n>)
```

- Aliases appear in stored order, each trimmed, with empty entries omitted.
- They are separated by exactly `", "`, whatever separator was used when they were stored.
- If a material has no aliases, no `(aliases: ...)` text appears.

| Stored `aliases` | Rendered |
|------------------|----------|
| `Oilite, Sintered Bronze, 841 Bronze` | `(aliases: Oilite, Sintered Bronze, 841 Bronze)` |
| `304 Stainless,SS304` | `(aliases: 304 Stainless, SS304)` |
| `Oilite,, Sintered Bronze ,` | `(aliases: Oilite, Sintered Bronze)` |
| `NULL` or empty | *(nothing)* |

## 2. `POST /admin/api/materials/validate`: live form validation (JSON)

The request and response shapes are unchanged. What changes is the verdict for aliases, which
follows the rule in [data-model.md](../data-model.md#validation-rule).

Existing data: material `Oil Embedded Bronze` with aliases `Oilite, Sintered Bronze, 841 Bronze`.

| Submitted `aliases` | `valid` | Error mentions |
|---------------------|---------|----------------|
| `Oilite` | `false` | alias conflicts with `Oil Embedded Bronze` |
| `OILITE` | `false` | same |
| `Bronze` | `true`, provided no other rule fails | none |
| `841` | `true`, provided no other rule fails | none |
| `Carbon Steel` (an existing material name) | `false` | conflicts with existing material |

`POST /admin/materials/add` (the form submission) MUST reach the same accept/refuse verdict for
the same aliases. It reports a refusal through its existing error flash; only the verdict is
required to match.

## 3. `GET /api/taxonomy`: public taxonomy API (JSON), unchanged

Material nodes carry `"aliases": [<str>, ...]`, trimmed and without empty entries, and `[]`
when there are none. This is its behavior today, and it MUST stay byte-for-byte identical for
the same data. Only where the list is produced moves, from the route into the service.
`tests/e2e/test_api_client.py::test_get_taxonomy_aliases_are_lists` guards it.
