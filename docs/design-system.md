# Shared SelfOS styling

Representative synthetic screenshots: [desktop settings, light](images/design-system/settings-desktop-light.png), [mobile settings, dark](images/design-system/settings-mobile-dark.png), [desktop knowledge, dark](images/design-system/knowledge-desktop-dark.png), [mobile knowledge, light](images/design-system/knowledge-mobile-light.png). They contain fixture data only.

The packaged frontend uses CSS roles rather than a framework. Both the standalone login page and dashboard load `styles/tokens.css` and `styles/controls.css`. Feature styles remain in their existing component files.

`tokens.css` owns light and dark palettes, the UI font, spacing and radius roles, focus geometry, and reduced-motion behavior. `body.dark` and the standalone login's `body.auth-dark` use the same dark roles. Use `--panel` for opaque panels, `--surface` for translucent cards, `--soft` for secondary surfaces, and `--text` / `--muted` for text. Interactive borders use `--control-line`, not the decorative separator `--line`.

`controls.css` owns shared inputs, buttons, dialogs, focus-visible outlines and semantic primary/secondary/danger roles. Knowledge cards are excluded from generic button decoration. Feature files own component layout, sizing and unique behavior. Add a semantic variant to the shared stylesheet when a common control needs one; avoid copying theme palettes or focus and reduced-motion rules into each feature. Register new files in the resource manifest.

The existing accent remains `--blue`. White primary-button text uses a slightly darker `--action-bg` (#006de0) to meet 4.5:1 contrast. Input borders use a separate role to meet 3:1 contrast. These are deliberate accessibility changes, not a new page design.

Cached dashboard refresh replaces the token and shared-control owners rather than accumulating styles. It also replaces the privacy dialog/script once, preventing duplicate JavaScript declarations after regeneration. Unrelated custom scripts are preserved.

Validation uses synthetic authenticated profiles with external requests blocked. Browser coverage exercises English/Chinese, light/dark, desktop/mobile, keyboard focus, reduced motion, disabled controls, representative contrast, overflow, and page errors. Screenshots cover login, dashboard, knowledge, settings, model, import, privacy, onboarding and account surfaces. This does not claim every legacy decorative value has been migrated. The frozen frontend extraction fixture remains historical evidence; intentional CSS changes are checked through packaged resources and browser behavior.
