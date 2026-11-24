# MEMORY

Preferences for price comparisons (supermarket-compare skill). Read at the start of every session.

## Search defaults
- Always use a **5 km radius** (straight-line). Every branch inside Kfar Saba must be included.
- Home area: **Kfar Saba**. Usual store: **Shuk HaIr (שוק העיר) Kfar Saba East, branch 011, Eli Horovitz 26**.
- **SPAR Israel, Eli Horovitz 26** is a *separate* store right next to Shuk HaIr, at the same address. Treat them as two different stores. SPAR is not supported by the tool, so compare SPAR receipts directly by barcode with `price_check.py prices`.
- Shuk HaIr is supported by the tool as chain `shukhayir` (Bina portal, `shuk-hayir.binaprojects.com`, allowed in the environment). For a Shuk HaIr receipt use `--home shukhayir:011`; in no-receipt checks it is included automatically and should be shown as the user's own store.
- If a Kfar Saba branch can't be placed on the map, locate it manually (add it to `scripts/branch_locations.json` in the installed skill) instead of skipping it.

## How to present results
- Always deliver results as a **dark-theme table artifact**: dark background, white text, clear row separation (soft rules, alternating rows, grouped sections), green/red savings pills with a bar.
- Template: `templates/results-table.html`. Copy it, replace the header text, the summary stats and the `rows` array (`[items, store, address, km, location, spar, here]`), keep the notes and the disclaimer, and publish it with the Artifact tool.
- Also give a short summary in chat (Hebrew), including what was not checked and the disclaimer word for word.
