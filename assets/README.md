# Brand assets

`logo.png` is the source of truth: 800×800, used in the README, as the bot's
WhatsApp profile picture, and on the web page.

There is a second copy at `core/static/logo.png`. That one is served by the
API, and the API image is built from the `core/` directory alone, it cannot
reach files above it. Twenty-five kilobytes duplicated is cheaper than
rebuilding the container's build context the week we ship.

**If you change the logo, change both.**

## Palette

Taken from the logo, and used everywhere else in the project:

| | | |
|---|---|---|
| Cream | `#f7f4ee` | page background |
| Ink | `#14181d` | text, the speech bubble |
| Terracotta | `#c0551d` | the mark, links, buttons |
