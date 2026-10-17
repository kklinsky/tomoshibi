# Tomoshibi Face: Animation Brief

Thank you for drawing Tomoshibi's face! This brief explains what the face is for, what
screen it will be shown on, every expression and animation needed, and exactly which files
to deliver. You don't need to know anything about the code. Draw the pieces described here
and the software will put them together and animate them.

## 1. What this is

Tomoshibi (灯火, Japanese for "lamplight") is a small talking companion for an older
person whose memory is fading. They press a lit button, talk, and it answers in a warm voice.
It reminds them about pills, visits and appointments, and it's happy to answer the same
question over and over.

It sits on a table in their home. The **face on its little screen** is what makes it feel like
a friendly companion rather than a gadget. The person using it will look at this face every
day, often from across the room, sometimes confused or tired, so the face has to be:

- **Friendly and calm.** Never startling, never sad, never "broken".
- **Simple and cartoon-like.** Not a realistic human face. Someone with memory loss might
  believe a realistic face is a real person trapped inside the box, which is upsetting.
  Think friendly robot, lantern spirit, or a simple Studio Ghibli-style creature, not a person.
- **Clear at a glance.** Especially whether it's *listening*.
- **Consistent.** One character, the same every day. Expressions change, the character doesn't.

The device is shaped like a small lantern, so a lantern or warm-light theme would fit
beautifully, but the character design is up to you.

## 2. The screen

| | |
|---|---|
| Size | **2.0 inches** diagonal (about the size of a large postage stamp) |
| Resolution | **320 × 240 pixels**, landscape (wider than tall) |
| Face area | The **top 320 × 168 pixels**. The bottom 72 pixels are reserved for a day/time strip ("Saturday afternoon · 2:15") that the software draws |
| Colors | Full color IPS screen. Looks best with a **dark background** and **warm, soft colors** |
| Frame rate | About 20 frames per second |

Because the screen is tiny and viewed from a distance:
- Use **thick, bold shapes** and **strong contrast**. Fine lines and small details disappear.
- Big eyes do most of the work. The mouth can be simple.
- Before finishing, **look at your drawing at actual size** (2 inches across, about 5 cm) from
  2–3 meters away. If you can't tell "listening" from "idle" at that distance, push it further.

### Color suggestions
- Background: very dark warm color (deep navy, charcoal or dark plum), not pure black.
- Face/eyes: warm light colors (cream, soft amber, warm white).
- Avoid: harsh pure red (reads as alarm), flashing, high-contrast strobing patterns.
- The software draws the background and the bottom strip, so please tell us your exact
  background color (hex code, e.g. `#1E1B2E`) so they match.

## 3. How to draw it: parts, not frames

Instead of drawing every animation frame, draw the face as **separate parts**. The
software layers them on top of each other and moves them to create the animations.

**The one rule:** draw every part on its own **320 × 168 pixel transparent canvas, in the exact
position where it sits on the face.** Then all the files line up perfectly when stacked,
like layers in your drawing app. (Easiest way: draw the whole face with each part on its
own layer, then export each layer separately at full canvas size.)

Two exceptions are noted below: **pupils** and **extras** are drawn centered, because the
software moves them around.

Use any app you like (Procreate, Krita, Photoshop, Aseprite, Clip Studio, etc.).

## 4. The states and animations

There are three kinds of animation:
- **States** loop for as long as the device is in that mode.
- **Expressions** change the eyes and mouth during a state.
- **Transitions** are short one-time animations between states.

The software handles timing and movement (breathing, glances, blinking, lip sync) using your
parts. Where a state needs special artwork, it's listed under "Parts needed".

### States (looping)

| State | When it happens | How it should look and feel | Parts needed |
|---|---|---|---|
| **Idle** | Most of the day, waiting | Relaxed and content. Software adds gentle "breathing" (a slow bob), a blink every few seconds, and eyes drifting to look around now and then | Normal eyes, pupils, closed/smile mouth |
| **Listening** | After the button is pressed, while the person talks | **The most important one.** Wide, attentive eyes looking straight out, slightly leaning in: "I'm listening to you." Must look clearly different from idle, even from across a room | Wide eyes, raised brows (if you use brows) |
| **Thinking** | While working out the answer (1–2 seconds) | Eyes glance up and to the side, as if pondering. Small "…" thinking dots | Thinking dots (3 dots, or a dot animation) |
| **Speaking** | While talking | Soft, friendly eyes. Mouth moves with the voice (see mouth shapes) | 5 mouth shapes |
| **Sleeping** | Late at night (midnight to 7 AM) | Peaceful. Eyes closed, very slow breathing. The screen is dimmed | Closed eyes, a small "z" (optional) |

### Expressions

| Expression | When | Look |
|---|---|---|
| **Happy** | Saying good morning, good news, "Karen is visiting today!", goodbyes | Smiling, upward-curved eyes (like `^ ^`), smile mouth |
| **Concerned** | The person sounds upset, confused or hurt | **Soft and sympathetic**, gently drooping brows/eyelids. Caring, never frightened or alarmed. Think "oh, I'm here for you" |
| **Curious** | It didn't hear clearly: "Sorry, could you say that again?" | A small head tilt, one brow slightly raised, attentive |
| **Looking it up** | Searching the internet for an answer (a few seconds) | Like thinking, with eyes glancing sideways. Optional small magnifying glass |

### Transitions (½ to 1 second, play once)

| Transition | Between | Feel |
|---|---|---|
| **Wake up** | Sleeping → awake | Eyes open slowly, a little stretch or shake. Gentle, not a jolt |
| **Fall asleep** | Idle → sleeping | Eyes droop, half-close, close |
| **Notice** | Idle → listening (button pressed) | A quick blink and eyes snap to center: "Oh! Yes?" Shows the button press was noticed |
| **Ahem** | Idle → announcing a reminder | Eyebrows go up, eyes turn toward the person, a polite "excuse me" look before speaking |
| **Settle** | End of a conversation → idle | A soft nod, eyes relax back to content |

**Timing:** keep everything **slow and smooth**. Nothing should snap, flash or bounce fast.
If you're making any frame-by-frame transitions, about 10–20 frames at 20 fps is right.

## 5. Parts checklist (what to deliver)

All files are **PNG with transparency**, full **320 × 168** canvas (except where noted),
named exactly as below. Names are lowercase with underscores.

### Eyes
| File | Description |
|---|---|
| `eyes_open.png` | Normal, relaxed open eyes (without pupils if pupils are separate) |
| `eyes_wide.png` | Wide, attentive (listening) |
| `eyes_half.png` | Half-closed (used in blinks and falling asleep) |
| `eyes_closed.png` | Closed (blink, sleeping) |
| `eyes_happy.png` | Smiling arcs `^ ^` |
| `eyes_sympathetic.png` | Soft, gently drooping (concerned) |

### Pupils (if your eyes have pupils)
| File | Description |
|---|---|
| `pupils.png` | Both pupils, drawn **centered in the eyes**. The software slides this layer a few pixels to make the eyes look around, so keep pupils well inside the eye shape |

### Blink
The software can blink using `eyes_open` → `eyes_half` → `eyes_closed` → `eyes_half` → `eyes_open`.
If you'd like a smoother blink, add `blink_1.png` … `blink_4.png`.

### Mouth
The mouth shapes are picked **by how loud the voice is** at each moment, not by exact words.
So they're just "how open" the mouth is, plus one round shape:

| File | Description |
|---|---|
| `mouth_closed.png` | Closed, neutral |
| `mouth_smile.png` | Closed smile (idle, happy) |
| `mouth_open_1.png` | Slightly open (quiet sounds) |
| `mouth_open_2.png` | Open (normal talking) |
| `mouth_open_3.png` | Wide open (loud or long vowels "ah") |
| `mouth_oo.png` | Small round "oo" |

### Eyebrows (optional, but they add a lot of expression)
| File | Description |
|---|---|
| `brows_neutral.png` | Normal |
| `brows_raised.png` | Raised (listening, notice, ahem, curious) |
| `brows_soft.png` | Gently worried (concerned) |

### Extras (drawn on a small canvas, centered; any size up to 64 × 64)
| File | Description |
|---|---|
| `thinking_dots_1.png` … `thinking_dots_3.png` | Thinking dots building up: `.`, `..`, `...` |
| `sleep_z.png` | A small "z" for sleeping |
| `magnifier.png` | Optional, for "looking it up" |

### Base
| File | Description |
|---|---|
| `face_base.png` | Anything that never changes: head shape, outline, cheeks, lantern frame, etc. Can be empty if the face is just eyes and mouth floating on the background |

### Small face (corner icon)
When the screen shows a reminder or a photo, a **small version of the face** sits in the corner
so the character never disappears.
| File | Description |
|---|---|
| `mini_face.png` | The whole face (normal, content) at **64 × 64**, transparent background |

### Reference
| File | Description |
|---|---|
| `preview_states.png` | One image showing each state and expression assembled, side by side, labeled. This is how we check the parts combine the way you intended |
| `colors.txt` | Background color and main colors as hex codes |

Please put everything in one folder named `tomoshibi` (zip it if sending by email).

## 6. Things the face should never do

- Look sad, crying, angry, scared, sick or "broken", even when something's wrong with the device.
- Flash, flicker, spin quickly, or change color suddenly.
- Look like a realistic human or a specific real person.
- Show text (the software handles all words on screen).
- Rely on tiny details that vanish at 2 inches.

## 7. Suggested order of work

1. **Sketch the character** on paper or digitally, a few options. Share them with the family
   (and ideally the person who'll use it) before going further.
2. Draw the **five states** (idle, listening, thinking, speaking, sleeping) as still images. Check
   that **listening** is unmistakable at actual size from across the room.
3. Split into **parts** and export the checklist files.
4. Add **expressions** and **transitions**.
5. We'll load it into a desktop previewer that animates the parts, so you can see it move and
   adjust before it goes on the real device.

## 8. Credit and sharing

Tomoshibi is an open-source project on GitHub so other families can build one. The default
face may be included in that public project. We'll **credit you by name** (or a handle you
choose) in the project, and we'll agree on a license with you before publishing, typically
Creative Commons Attribution-ShareAlike (CC BY-SA 4.0), which lets others use and adapt it as
long as they credit you and share alike. If you'd rather the face stay private to our family,
that's completely fine too: just say so.

---

*Technical reference for developers: docs/DESIGN.md §3, "Screen: an animated face".*
