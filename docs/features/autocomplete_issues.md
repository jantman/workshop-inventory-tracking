# Feature: Autocomplete Issues

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

There is something wrong with our Material autocomplete menus (on the Add and Edit Item forms) that allow either selecting an autocomplete or browsing the material hierarchy. Something with the hierarchy browsing is wrong... the "Back" button often goes back to the top of the hierarchy not the previous node, and selecting a second-tier item ("Family" in our taxonomy) does not show the list of its children but rather goes back to the top of the hierarchy.

I think that we need to write e2e tests to validate navigation to, display of, and selection at every level of the hierarchy, and then use those (presumably failing) tests to guide our identification of the bug(s) and fixing them.

See `fix_material_autocomplete_issues.md` in this directory for history of the original feature implementation.