# Tomoshibi Brand Mark

## The wordmark

![tomo wordmark](../assets/brand/tomo-wordmark-preview.png)

The brand mark is the word **tomo**, lowercase, set in **Fredoka SemiBold (weight 600)**.
Whenever "tomo" appears as the mark (on the device, its screen, the setup page, the
enclosure, the project's pages), use this wordmark and no other font.

| | |
|---|---|
| Text | `tomo`, always lowercase |
| Typeface | [Fredoka](https://fonts.google.com/specimen/Fredoka), weight 600 (SemiBold), normal width |
| Primary color | Lamplight `#f2b45a` on night `#1e1b2e` |
| One-color use | Any single color, e.g. embossed in the enclosure's own filament |

"Tomoshibi" (the project's full name) in running text, documentation and code stays in
ordinary type; the wordmark is for the short mark "tomo".

## Files

| File | Use |
|---|---|
| [`assets/brand/tomo-wordmark.svg`](../assets/brand/tomo-wordmark.svg) | Outlined, `currentColor` fill. Takes the color of its surroundings on web pages, and imports cleanly into Fusion 360 |
| [`assets/brand/tomo-wordmark-lamp.svg`](../assets/brand/tomo-wordmark-lamp.svg) | Outlined, lamplight color |
| [`assets/brand/tomo-wordmark-preview.png`](../assets/brand/tomo-wordmark-preview.png) | Preview on the night background |
| [`assets/fonts/fredoka/`](../assets/fonts/fredoka/) | The Fredoka font and its license, for drawing the wordmark on the device |

The SVGs are **outlined**: the letters are shapes, so no font needs to be installed to use
them. Regenerate them after any change with:

```bash
uv run --no-project --with fonttools --with pillow python scripts/make_wordmark.py
```

## On the device's screen
- Shown on the **boot screen** while Tomoshibi starts, on the **setup mode** screen
  (§10b of the design doc), and in the setup page's header.
- Drawn from the bundled font (`assets/fonts/fredoka/Fredoka[wdth,wght].ttf`, variable:
  set weight 600, width 100), so it works offline.
- At least **28 px tall** on the 320 × 240 screen so its rounded shapes stay clean.
- It doesn't appear on the everyday face screen: the face is the character, and the mark
  would compete with it.

## On the enclosure
- Import `tomo-wordmark.svg` in Fusion 360 (*Insert → Insert SVG*), scale it, then
  emboss or deboss it.
- For clean FDM printing: wordmark **at least 25 mm wide**, embossed or debossed
  **0.6–1.0 mm**. Printing the letter face-up, or as a separate inlay in a contrasting
  filament (lamplight yellow on a dark body), gives the crispest result.
- Leave clear space around it of at least the height of the letter "o".

## License
Fredoka is © The Fredoka Project Authors, licensed under the
[SIL Open Font License 1.1](../assets/fonts/fredoka/OFL.txt). The font may be bundled,
used and redistributed with the project, including commercially; it can't be sold on its
own, and modified versions can't be called "Fredoka". The font files come from the
google/fonts repository (`ofl/fredoka`) at commit `a60a77e14f28abd4ef243a1b5dfc48df0cec5205`.

## For forks
The wordmark marks this project. A family that renames its device's persona (§9a) still
uses the same software; whether they keep "tomo" on their enclosure is up to them.
