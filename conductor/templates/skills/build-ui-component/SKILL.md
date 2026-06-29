---
name: build-ui-component
description: "Use to create or adjust a UI component by defining states (default, loading, error, empty, focus), writing semantic accessible HTML, applying a robust responsive style, and testing accessibility."
---

# Skill — build-ui-component

**When to use:** To create or adjust a UI component.

**Steps:**
1. Define states (default, loading, error, empty, focus).
2. Structure semantic and accessible HTML.
3. Apply a robust, responsive layout and style.
4. Wire data with the minimum necessary fetching.
5. Test accessibility (keyboard, screen reader, contrast) and summarize results.
6. Keep one responsibility per file — separate template, styles, component logic,
   and tests into dedicated files (e.g. Angular `templateUrl`/`styleUrls` +
   `.spec.ts`; React: component + CSS module + test). Inline template/styles only
   for trivial components (icon, spinner, badge); split them out as they grow.
