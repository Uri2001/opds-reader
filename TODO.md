## UI/UX improvements plan (detailed)

- [ ] Loading state
  - Add small status label/spinner next to search; show “Loading…” / “Ready”.
  - Disable Search/Download/Fix buttons during fetch; re-enable on finish/error.
  - Inline error label under URL row for network/parse failures.

- [ ] Navigation clarity
  - Add Back pushbutton (same handler as Backspace) above the table.
  - Show breadcrumb/current path text (“Root › …”) above the table, updated on navigation.

- [ ] Search/URL polish
  - Add placeholder to search input; focus search after catalog load.
  - Add Refresh action (button) next to URL to re-download current catalog.
  - Tighten layout spacing so URL/search/buttons align cleanly.

- [ ] Table usability
  - Enable column sorting (header click) without breaking filtering.
  - Remember column widths across sessions (store in prefs).
  - Increase row padding and add hover highlight.
  - Show empty states in the table area: “No results” / “No matches for ‘…’”.

- [ ] Library awareness
  - Visually mark rows already in library (icon or subtle color).
  - Add tooltip to “Hide books already in library” explaining behavior.

- [ ] Action buttons
  - Enable/disable Download and Fix timestamps based on selection presence.
  - Show selection count in Download text, e.g., “Download selected (N)”.

- [ ] Context actions
  - Add right-click menu on rows: copy link, open in browser, show metadata dialog.
