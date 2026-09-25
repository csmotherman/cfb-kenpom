# Bundled brand fonts

Used by `cfb_analytics.social.images.brand` to render social-post PNGs
locally with Pillow, matching the brand fonts the web app self-hosts via
`next/font` (`web/app/layout.tsx`) without needing a WOFF2-capable renderer
(Pillow/FreeType only reads TTF/OTF).

All three are Google Fonts, SIL Open Font License (`OFL.txt`), pulled from
the [google/fonts](https://github.com/google/fonts) repository:

- `BigShouldersDisplay[wght].ttf` -- variable font, used at heavy weight for headlines.
- `PublicSans[wght].ttf` -- variable font, used for body/label text.
- `IBMPlexMono-{Regular,SemiBold,Bold}.ttf` -- static weights, used for numeric columns.
