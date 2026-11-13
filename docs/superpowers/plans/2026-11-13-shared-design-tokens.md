# Shared visual rules (#48)

Scope follows the existing issue: preserve the current SelfOS appearance, extract shared tokens/control ownership, remove duplicate theme/focus/motion overrides, and verify representative surfaces. No framework, workflow, locale text, or knowledge logic changes.

Current audit: visual-system.css owns two root palettes and shared modal/form/card overrides; auth.css duplicates dark tokens and focus; login.css hardcodes background/font; module CSS repeats button/input borders, radii, disabled rules and focus. Imported workload/privacy templates also retain inline fieldset styles.

- [x] Establish synthetic browser checks across login, dashboard, settings, model, account, knowledge and import surfaces, light/dark, desktop/mobile. Check contrast, focus, disabled and reduced motion, not just CSS strings.
- [x] Extract palette/typography/spacing/radius/focus/motion tokens into shared tokens.css; preserve role aliases. Extract existing shared control/surface rules into controls.css at the same effective source-order position.
- [x] Wire both standalone login and dashboard packaged resources. Migrate repeated control values to tokens and shared selectors, remove obsolete theme/focus/motion declarations. Keep component-specific sizing/layout in component files.
- [x] Verify screenshots, interactions and resource loading. Document ownership, run appropriate regression, independent review and PR linked to #48.
