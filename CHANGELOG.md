# Changelog

## Unreleased

- Added an animated README demo GIF.
- Added PyInstaller packaging docs and a portable Windows app spec.

## v1.1.3 - 2026-05-14

- Improved transparent background rendering by moving the transparency key away from black and white text colors.
- Reworked click-through on Windows to use the window click-through style when available, with a hub-menu action to disable click-through on all notes.
- Reasserted topmost state when click-through fallback restores a note.
- Added appearance/click-through regression tests.

## v1.1.2 - 2026-05-11

- Fixed edit-mode `Select all` so it clears the existing selection before selecting note text.

## v1.1.1 - 2026-05-11

- Added an edit-mode right-click text menu with cut, copy, paste, and select-all actions.
- Clamped the font family picker popup to the visible screen.
- Added tests for font family persistence through duplicate, stash, and preset flows.

## v1.1.0 - 2026-05-11

- Added a searchable font family picker for individual notes.
- Added a default font family picker for new notes.
- Persisted note font family in saved sessions, stash, presets, and duplicates.

## v1.0.0 - 2026-05-11

Initial public release.

- Floating always-on-top notes built with Python and Tkinter.
- Quick note creation from the hub or `send_label.ps1`.
- Local-only socket listener bound to `127.0.0.1`.
- Per-note colors, opacity, resize, stash, presets, and pasted images.
- Light and dark mode actions for existing notes and new-note defaults.
- Plain-text checklist syntax with click-to-toggle behavior.
- Notes stored outside the project folder in `%APPDATA%\ScrollyPollyNotely`.
- Public test suite and GitHub Actions CI.
