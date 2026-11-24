# MEMORY

Preferences for price comparisons (supermarket-compare skill). Read at the start of every session.

## Search defaults
- Always use a **5 km radius** (straight-line). Every branch inside Kfar Saba must be included.
- Home area: **Kfar Saba**. Usual store: SPAR, Eli Horovitz 26, Kfar Saba (not a chain the tool supports, so compare receipt prices directly by barcode with `price_check.py prices`).
- If a Kfar Saba branch can't be placed on the map, locate it manually (add it to `scripts/branch_locations.json` in the installed skill) instead of skipping it.

## How to present results
- Always deliver results as a **dark-theme table artifact**: dark background, white text, clear row separation (soft rules, alternating rows, grouped sections), green/red savings pills with a bar.
- Template: `templates/results-table.html`. Copy it, replace the header text, the summary stats and the `rows` array (`[items, store, address, km, location, spar, here]`), keep the notes and the disclaimer, and publish it with the Artifact tool.
- Also give a short summary in chat (Hebrew), including what was not checked and the disclaimer word for word.
