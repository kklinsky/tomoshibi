# Tomoshibi — Design

Status: draft v0.3 (2026-10-16)

## 1. Goals

Build one device for my father, a voice companion he can use every day, and publish all
code, enclosure files and docs on GitHub so other families can build their own.

| Person | Needs |
|---|---|
| **Dad** (primary user) | Natural conversation about almost anything; "what day is it / what's happening today"; reminders; help remembering the people in his life |
| **Mom** (caregiver) | Ask it for help, add events/reminders for Dad, send short messages; relief from answering the same questions |
| **Family** (me, my sister) | Get messages from Dad; send him messages; tell the device about visits and news so it can bring them up; get alerts |
| **Builder/admin** (me, and anyone forking the project) | Configure, update and monitor remotely; swap the AI provider; adapt it to their own family |

### Non-goals
- Not a medical device or an emergency response system.
- No apps, menus or settings on the device itself.

## 2. Design principles

1. **One obvious action.** One lit button, right below the face. Press it, talk.
2. **Endless patience.** Repeated questions get the same warm, complete answer every time. It never says "you already asked that."
3. **It speaks first when it matters.** Reminders and the morning greeting happen without Dad having to ask.
4. **Local first.** Speech recognition, speech synthesis, reminders, the clock and the personal knowledge base all run on the Pi. Only the "big brain" (the LLM) needs the internet, and there's a local fallback for that too.
5. **Provider-agnostic.** Claude by default; ChatGPT, Ollama or anything else through a small adapter and a config change.
6. **Private by default.** Personal data lives in a data directory that is never committed. The public repo ships only example data.
7. **Fails gently.** When something is down it says so in plain words, and reminders still work.

## 3. Hardware

This section covers the core parts and design decisions. The full parts list (power, storage, connectors, enclosure hardware, optional sensors) is in [`hardware/BOM.md`](../hardware/BOM.md).

| Part | Notes |
|---|---|
| Raspberry Pi 5 | **8 GB recommended** if running a local fallback LLM; 4 GB is fine for STT/TTS only. Active cooler, official 27 W USB-C PSU, RTC battery. |
| Jabra Speak 410 (USB) | Full-duplex speakerphone with echo cancellation, good pickup across a room. Appears as a standard USB audio device. **Its touch buttons (mute, volume, call) are easy to hit by accident.** The enclosure should cover mute/call, or the software should detect mute and say "I'm muted, press the button with the line through it." |
| **30 mm** arcade button with built-in LED | Smaller than first planned, because the top of the enclosure is taken by the Jabra. Placement and making it easy to find are covered under *Enclosure layout* below. Input on a GPIO with internal pull-up. **Check the LED voltage:** most are 5 V or 12 V with an internal resistor. GPIO pins are 3.3 V / ~16 mA, so drive the LED through a small N-channel MOSFET or NPN transistor (5 V from the Pi header). The LED is on only while listening (§4), so simple on/off is enough; PWM allows a soft fade. |
| 2.0" 320×240 IPS TFT, ST7789 (Adafruit EYESPI) | SPI. Connect via an EYESPI adapter (e.g. EYESPI Pi Beret) or jumper wires to SPI0. The microSD slot on the breakout isn't needed. |
| 3D-printed enclosure (Fusion 360) | Lantern/lamp form to suit the name. Jabra on top, screen and button on the front (see below). Weighted base, cable strain relief, ventilation for the Pi. Lives in its own repo, `tomoshibi-enclosure` (§11). |

### Enclosure layout
```
        ┌──────────────────────┐   ← Jabra Speak 410 sits in a recess on top,
        │  ( Jabra, grille up ) │     grille open to the room; printed cover ring
        ├──────────────────────┤     hides its mute/call touch keys
        │   ┌──────────────┐   │
        │   │  ◕‿◕  (face)  │   │   ← 2.0" screen, front face angled ~15° up
        │   │ Sat afternoon │   │     toward a seated person
        │   └──────────────┘   │
        │         (●)          │   ← 30 mm lit button directly below the face
        │                      │
        └──────────────────────┘   weighted base; USB-C power + Jabra cable out the back
```
- **Jabra on top.** It's about 120 mm across. Seat it in a recess with its grille unobstructed (it needs to hear the room and project sound). A printed **cover ring** blocks the mute and call touch keys so they can't be pressed by accident; volume can stay reachable or be covered too, with volume controlled by voice instead ("speak up"). The software still detects mute as a backup. The Jabra's USB cable is fixed, so route it down inside the enclosure to the Pi.
- **Button on the front, directly below the face.** He looks at the face, and the button is right there. With the Jabra on top, the front is also where the screen is, so the face and the button read as one thing: press here to talk to *this*.
- **Making a 30 mm button easy to find and press:**
  - A raised printed **bezel** around it in a contrasting color, so it's findable by touch and by eye.
  - For a dim room, print the bezel in a light or glow-in-the-dark filament instead of lighting the LED at idle. The LED keeps one meaning: on = listening.
  - A light-action switch (avoid stiff ones), mounted solidly so the enclosure doesn't slide when pressed: weighted base plus rubber feet.
  - Nothing else on the front that looks like a button.
- **Airflow:** the Pi 5's active cooler needs intake and exhaust vents away from the Jabra's mic and speaker so fan noise isn't picked up.
- **Service access:** a screw-on back or base panel for the Pi, SD card and wiring; the Jabra lifts out of its recess.

### Screen: an animated face
The screen's main job is to give Tomoshibi a **friendly animated face**, so it feels like someone to talk to rather than a gadget. It never needs to be touched or navigated.

The artist-facing spec (states, expressions, transitions, the parts checklist and file names) is in [`face-animation-brief.md`](face-animation-brief.md).

#### Face design guidelines
- **Simple and cartoon-like, not realistic.** Two large eyes and a simple mouth (think a friendly robot or a lantern character). Realistic human faces can be confusing or unsettling for someone with dementia, who may believe a real person is inside the device.
- **Calm.** Slow, smooth motion; no sudden jumps, flashing or fast colors. Soft warm palette on a dark background (less glare, readable across a room).
- **Consistent.** The same face every day. Expressions change, the character doesn't.
- **Expressive in a few clear ways** instead of many subtle ones.

#### Face states
| State | Face | Button LED |
|---|---|---|
| **Idle** | Relaxed, occasional blink, gentle "breathing", eyes drift slowly | off |
| **Listening** | Eyes wide and attentive, slight lean/tilt, mouth closed | **on** |
| **Thinking / looking up** | Eyes glance up and to the side, small animated "…" | off |
| **Speaking** | Mouth moves in time with the voice | off |
| **Happy** (greetings, good news, family messages) | Smiling eyes | — |
| **Concerned** (distress, he sounds upset) | Soft, sympathetic eyes; never alarmed-looking | — |
| **Reminder** | Gentle "ahem" look, then the reminder card (below) | off while speaking, **on** when it starts listening for his reply |
| **Sleeping** (quiet hours) | Eyes closed, dimmed screen; wakes with a stretch when the button is pressed or a reminder is due | off |
| **Offline / problem** | Normal face; an amber offline icon in the orientation strip (§5); never a sad or broken face | — |

#### Orientation strip
The face takes the upper ~70% of the screen. A **strip along the bottom always shows the day and time of day**, e.g. "Saturday afternoon · 2:15". The day/date clock is a well-known orientation aid, so it stays visible under the face instead of being lost to it. A press-free "full clock" (large day, date, time) takes over the whole screen for a few seconds after the morning greeting, or when he asks "what day is it?".

#### Cards (temporary, then back to the face)
- **Reminder:** large text ("Morning pills — blue box by the sink"), with a small version of the face in the corner.
- **People:** when it talks about someone from the people file, their photo and name ("Karen — your daughter"). Also used when a family message arrives.
- **Looking up:** a small "Looking that up…" under the thinking face.

#### Implementation
- **Lip sync from the audio, not the text.** The mouth opening follows the loudness (RMS envelope) of the TTS audio as it plays, in ~30 ms windows, mapped to 3–5 mouth shapes. Works with any TTS engine. Piper can also output phoneme timings, which allow true viseme mouth shapes later if the simple version feels off.
- **Rendering:** a separate display process/thread draws frames with Pillow from **pre-drawn sprite parts** (eye shapes, eyelids, mouths, pupils) composited per frame, and pushes them over SPI. It runs independently so audio never stutters.
- **Frame rate:** 320×240 at 16-bit color is ~150 KB/frame. At the ST7789's SPI clock that's roughly 25–40 fps maximum, so target **~20 fps**, redrawing only the changed region (eyes/mouth bounding boxes) to keep CPU low.
- **Face packs for forks:** a face is a folder of sprite PNGs plus a `face.json` (positions, expression definitions, palette). The default face ships in `assets/faces/tomoshibi/`. Families can swap in another (e.g. a lantern-flame character, or a pet-like face) without touching code. A tiny previewer script (`scripts/preview_face.py`) renders it in a desktop window for design work off-device.
- **Brightness:** dims automatically at night/quiet hours. Optional light sensor later.

## 4. Interaction model

The device has two primary use cases. Everything else (messages, morning greeting, Mom's tasks) is a variation of one of these.

**The one rule that ties them together: the button light is on exactly when the device is listening.** That holds whether he pressed the button or a reminder opened the mic.

### Use case 1: Dad presses the button and has a conversation

```
 idle ──press──▶ listening ──silence──▶ thinking ──▶ speaking ──▶ listening (follow-up)
  ▲                  ▲                                               │
  │                  └──────────────── he speaks again ◀─────────────┤
  └───────────── no speech for follow_up_window ─────────────────────┘
                  ("OK, I'm here whenever you need me." → idle face)
```

1. **Press the button** → soft chime, **light on**, the face looks up attentively.
2. He speaks. His turn ends after ~1.5 s of silence (tuned generously for slower speech) or on a second press.
3. Light off, the face looks "thinking" → the answer is spoken, the mouth moving with the voice.
4. **Back-and-forth:** after each answer the device goes straight back to listening, light on, for a follow-up. **On by default** (`conversation.follow_up_window: 10s`). He just keeps talking; no press needed.
5. The conversation ends when he doesn't say anything during the follow-up window, says "thanks, that's all" / "goodbye", or presses the button. It closes warmly and the face goes back to idle.
6. **Pressing during an answer stops it** and starts listening again (barge-in).
7. Context carries across turns ("And what about tomorrow?" works), and across the day via the day's rolling memory.

#### What he asks, and where the answer comes from
| He asks about… | Example | Source |
|---|---|---|
| **General knowledge** | "How far away is the moon?" | The LLM's own knowledge |
| **Current events** | "Who won the World Series?" / "What's in the news?" | `web_search` / news, **if enabled** (§8a); otherwise answers from general knowledge and says it can't check |
| **Upcoming events in his life** | "What's happening this week?" / "When is Karen coming?" | Events in SQLite, family notes from Slack (§6a, §7) |
| **His past** | "Where did I work after the Navy?" | `data/wiki/` life story (§6) |
| **His relatives** | "How many grandkids do I have?" / "Who's Mike again?" | `people.yaml` (+ photo on screen) |

#### Never invent personal facts
For general knowledge, the model can answer freely. For **his life, his family and his schedule**, it answers **only from the knowledge base**. If something isn't there, it says so kindly and points him to a person: "I don't know that one, Bob. That'd be a great one to ask Carol." A confidently made-up memory is worse than no answer for someone with memory loss.
- Each unanswered personal question is logged as a **knowledge gap** and included in the daily Slack summary ("Dad asked where he and Mom went on their honeymoon. It's not in the wiki."), so the family can fill it in.

#### Repeated questions
Answered fully and warmly every time, with no hint that he's asked before. Repeats are counted (not mentioned) for the optional daily summary.

### Use case 2: a reminder wakes the device up

```
 idle/sleeping ──event due──▶ chime + wake ──▶ speaking (reminder) ──▶ listening (reminder_listen_window)
                                                                          │
           ┌──────────────── he responds ◀───────────────────────────────┤
           ▼                                                              │ no response
   acknowledged / snoozed / question answered                      retry later (×2) → alert family
   → conversation (use case 1) or idle
```

1. **An event comes due** (e.g. 15 minutes before the dentist; the moment for morning pills).
2. Soft chime, **the face wakes up** (from sleep, with a little stretch) and looks at him. The screen shows the reminder card.
3. It speaks the reminder in plain words with what he needs to know: "Bob, it's 8 o'clock. Time for your morning pills. They're in the blue box by the sink."
4. **It automatically enters listening mode, light on,** for `reminders.listen_window` (default **30 s**, longer than the conversation follow-up because he may need to walk over or think).
5. What he says decides what happens:
   - **Acknowledges** ("OK", "Thanks, I took them") → marked acknowledged. A button press also counts.
   - **Snoozes** ("Remind me in ten minutes") → re-fires then. Snooze limits are configurable per event.
   - **Asks about it** ("What time is the dentist?") → answered, and the conversation continues as in use case 1. The reminder counts as acknowledged.
   - **Something else entirely** → normal conversation (use case 1). The reminder stays unacknowledged and is gently mentioned again at the end.
6. **No response within the window** → the light goes off and it goes back to idle. It retries per the event's policy (default: twice, 5 minutes apart). After the last retry it alerts the family in Slack (§6a). The reminder card stays on screen until acknowledged.

#### Edge cases
- **In the middle of a conversation:** the reminder waits for the end of the current answer, then: "Before I forget, Bob — it's time for your pills."
- **Several reminders due together:** combined into one announcement.
- **During quiet hours:** **scheduled reminders still fire** (e.g. 6:30 AM pills); quiet hours only hold family messages and non-urgent alerts. Volume follows a time-of-day setting.
- **Background noise (TV) during the listen window:** speech that doesn't sound like a reply (low confidence, unrelated) doesn't count as acknowledgment. The window closes as if there was no response.

### Variations on these use cases
- **Morning greeting** works like use case 2: at a set time or on the first press of the day it says "Good morning, Bob. It's Saturday, October 17th. It's sunny and 58 degrees. Karen is visiting at 2 o'clock." Then it listens.
- **A family message arriving** (§6a) is delivered at the start of his next conversation, or works like use case 2 if marked urgent.

No wake word in v1. They false-trigger on TV audio and are one more thing to remember. Wake word support (openWakeWord) can be added later as an option, never as a replacement for the button.

### Mom
Mom also finds technology hard and **won't use Slack or a phone app**, so the device itself has to be her whole interface. She uses the same button as Dad, and everything she needs must work by voice.

- **Asking and getting help:** same as Dad.
- **Passing things to the family:** "Tell Kevin the doctor moved Dad's appointment to Thursday." Same `send_message` flow as Dad's, attributed *"From Mom"*.
- **Changing events/reminders:** **undecided.** It needs a guard so a confused moment of Dad's can't cancel his pills. Candidates:
  - a. **Family proxy:** Mom calls Kevin or his sister, and they make the change in Slack. Simplest for her, but it depends on us.
  - b. **Voice edits with a safety net:** anyone can add or change events by voice. The device reads back the change and asks for confirmation, then posts it to `#tomoshibi` with *Undo*, so Kevin or his sister can catch mistakes. Medication reminders could be marked *protected* (changeable only from Slack).
  - c. **Caregiver gesture:** press-and-hold for 3 s unlocks editing tools for one session. Only works if Mom can remember the gesture.
  - Current lean: **b**, plus protected medication reminders, with a as the fallback for anything protected. Try it with Mom before deciding.
- **Speaking to the right person:** the device can't reliably tell Mom's voice from Dad's, so it asks when it matters ("Is this Carol or Bob?") and never relies on voice as a permission check.

Voice speaker identification isn't reliable enough to be the permission boundary.

## 5. Software architecture

**Language: Python 3.11+** on Raspberry Pi OS 64-bit. This departs from my usual Java preference on purpose: local speech models, VAD, GPIO and ST7789 drivers, and every LLM SDK are first-class in Python. Python is also what most people forking a Pi project will expect.

```
┌──────────────────────────── Raspberry Pi 5 ─────────────────────────────┐
│                                                                         │
│  Button/LED (gpiozero) ─┐        ┌─ Face renderer (ST7789, sprites)     │
│                         ▼        ▼                                      │
│                 ┌── Core: state machine + event bus ──┐                 │
│                 │ idle → listening → thinking →       │                 │
│                 │ speaking → idle  (+ reminder, error)│                 │
│                 └──────────────┬──────────────────────┘                 │
│  Jabra ─▶ Audio in ─▶ VAD ─▶ STT ─┤        ┌─▶ TTS ─▶ Audio out ─▶ Jabra │
│           (Silero)   (local)      ▼        │   (local)                  │
│                         Conversation ──────┘                            │
│                         ├─ Context builder (profile, people, today)     │
│                         ├─ Tool registry (neutral schema)               │
│                         └─ LLM provider interface                       │
│                              ├─ Anthropic (default) ──▶ internet        │
│                              ├─ OpenAI ───────────────▶ internet        │
│                              └─ Ollama / llama.cpp (local fallback)     │
│                                                                         │
│  Scheduler (reminders, greeting)    Knowledge base (Markdown + YAML)    │
│  SQLite (events, reminders, family notes, inbox/outbox, logs)           │
│  Family channel (Slack, Socket Mode) ◀──── outbound WebSocket ──────────┼──▶ family Slack
│  systemd + watchdog · Tailscale (admin) · heartbeat                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### Components & pluggable interfaces
Every replaceable piece sits behind a small interface and is chosen in `config.yaml`, so forks can swap parts without touching core code.

| Interface | Default | Alternatives |
|---|---|---|
| `SpeechToText` | **faster-whisper** `base.en`/`small.en` int8 (CPU) | **Moonshine** (built for edge devices, faster on short clips), Vosk (streaming, lower accuracy), whisper.cpp |
| `TextToSpeech` | **Kokoro-82M** int8 via kokoro-onnx, voice **`am_fenrir`** (chosen by ear: friendly and clear; ~1.1–1.9 s per sentence, RTF ~0.85 on a Pi 5) | **Piper** (much faster, ~0.1× real time, but more synthetic) |
| `VoiceActivity` | Silero VAD (ONNX) | WebRTC VAD |
| `LLMProvider` | Anthropic Claude | OpenAI, Ollama (local), any OpenAI-compatible endpoint |
| `Display` | ST7789 via `luma.lcd` or Adafruit `rgb_display` | Null display (headless builds) |
| `FamilyChannel` (two-way: send + receive) | **Slack** (Socket Mode) | Telegram, Discord, Matrix; ntfy/Twilio SMS as send-only |
| `EventSource` | Local SQLite | Read-only ICS/Google Calendar import |

**STT accuracy on an older voice is the biggest risk** in going fully local. Phase 1 includes a benchmark: record ~20 real phrases from Dad (with his OK) and compare engine/model size on word error rate and latency on the Pi 5.

### Latency budget (target ≤ 3 s from end of speech to first audio)
| Stage | Target |
|---|---|
| End-of-speech detection | built into the 1.5 s silence window |
| Local STT (short utterance) | ≤ 1.0 s |
| LLM time to first sentence (streaming) | ≤ 1.5 s |
| Local TTS, first sentence | ≤ 0.4 s with Piper; **~1.1 s with Kokoro** (the chosen voice) |

Stream the LLM output, split it into sentences, and synthesize and play sentence by sentence so speech starts before the full answer exists.

**Kokoro trade-off.** The chosen voice (Kokoro `am_fenrir`) sounds noticeably more natural than Piper, but its first sentence takes ~1.1 s instead of ~0.1 s, putting the budget at risk. Ways to win that time back:
- **Moonshine for STT** saves ~0.9 s per turn compared with Whisper base (0.69 s vs 1.63 s on the Pi 5), which roughly offsets Kokoro.
- **Keep first sentences short.** The system prompt asks for a short opening sentence ("Sure, Bob." / "It's Saturday."), and the sentence splitter can break the first chunk at a comma, so the first audio is quick to synthesize.
- **Pre-synthesize fixed phrases** and cache the audio: reminder texts (when an event is saved), greetings, "Let me look that up", "I'm not connected right now", the morning greeting's fixed parts. These then play instantly and also work if synthesis is busy.
- **Show it's thinking.** The face's thinking animation already covers the wait; a soft acknowledgement sound when his turn ends makes a 1–2 s pause feel natural rather than broken.
- **Overlap work:** synthesize sentence *n+1* while sentence *n* plays (Kokoro's RTF < 1 keeps up once started).
- If it still feels slow in real use with Dad, Piper remains one config change away.

### LLM provider abstraction
```python
class LLMProvider(Protocol):
    def stream_chat(self, system: str, messages: list[Message],
                    tools: list[ToolSpec]) -> Iterator[ChatEvent]: ...
```
- `Message`, `ToolSpec`, `ChatEvent` (text delta, tool call, done) are Tomoshibi's own neutral types. Each adapter (~100–200 lines) translates to and from its vendor's format, including tool calling.
- Thin adapters over the official SDKs (`anthropic`, `openai`); no heavy framework. Ollama and most local servers speak the OpenAI-compatible API, so the OpenAI adapter covers them with a different `base_url`.
- Config chooses a **primary** and a **fallback** provider:
  ```yaml
  llm:
    primary:  { provider: anthropic, model: claude-haiku-5-5 }
    fallback: { provider: ollama, model: qwen2.5:1.5b, base_url: http://localhost:11434 }
  ```
- Prompt caching (Anthropic) for the large, stable system prompt (profile + people) keeps cost and latency down.

### Offline behavior
| Capability | Online | Offline |
|---|---|---|
| Hearing & speaking | local | local |
| Clock, date, today's events, reminders | local | local |
| "Who is Karen?" (people file) | LLM with people file in context | local LLM, or a direct lookup from the people file if no local LLM |
| Open conversation, world knowledge | cloud LLM | local small LLM: limited, slow, says so ("I'm not connected right now, so I may not know everything") |
| News, weather, web search | ✓ | ✗, explained in plain words; last known weather cached |

A 1–3 B model under llama.cpp/Ollama on a Pi 5 manages a few to ~10 tokens/s. That's acceptable for short answers. It's optional and needs the 8 GB Pi.

### Detecting loss of connectivity
A `ConnectivityMonitor` runs in the background and publishes state changes on the event bus (the display, conversation and Slack components all subscribe):

| State | Meaning | Detected by |
|---|---|---|
| `online` | Everything reachable | — |
| `no_wifi` | Not connected to the network | No route / no IP address |
| `no_internet` | On Wi-Fi, but the internet is unreachable | DNS lookup + HTTPS request to a known endpoint fail |
| `ai_unavailable` | Internet works, but the LLM provider is down or rejecting requests (outage, bad key, out of credit) | Provider health call or repeated API errors |

- Checks every 30 s, and immediately whenever an API call fails.
- **Hysteresis** so the screen doesn't flicker: 2 consecutive failures to go offline, 1 success to come back.
- `ai_unavailable` switches to the fallback provider (§5) if one is configured. If the fallback works, the device is still "online" from Dad's point of view, and only the family is told (in Slack).

### Showing it on the display
- **A small icon at the right end of the orientation strip** (§3): a Wi-Fi symbol with a line through it, in soft amber. Small enough not to worry Dad, but obvious to Mom or a visiting family member who knows to look.
- Below the icon, the strip shows the word **"Offline"** for the first minute after the change, then the icon alone.
- **The face stays normal.** No sad, broken or confused expression: the device is still working, and a worried-looking face could upset him.
- Distinct icons for `no_wifi` vs `no_internet`/`ai_unavailable` help whoever is troubleshooting ("is it the Wi-Fi or the internet?"). Optionally, in the setup wizard or on a long press of the button, the screen shows a plain-language status card: "Wi-Fi: connected · Internet: not reachable since 2:14 PM".
- The **button LED never indicates connectivity.** It keeps one meaning: on = listening.
- When the connection comes back, the icon disappears. Nothing is said to Dad.

### What he hears
- **Starting a conversation while offline:** at the start of a conversation (not every turn): "Just so you know, I can't reach the internet right now, so I can't look things up, but I can still help with your schedule and reminders." Then it carries on with what it can do (local LLM if available, otherwise the local skills below).
- Without a local LLM, offline speech understanding uses a small **local intent matcher** for the essentials: what time/day is it, what's on today/tomorrow, who is <person>, acknowledge, snooze, repeat that. Anything else gets a kind "I can't answer that while I'm offline. Carol might know."
- **The internet dropping mid-conversation:** finishes or abandons the current answer gracefully ("Sorry, I've lost my connection") instead of going silent.

### Reminders always work offline
Reminders must never depend on the internet. Everything in the reminder path is local:

| Step | How it stays local |
|---|---|
| Schedule | Events and recurrence rules are in SQLite; the scheduler runs on the device |
| Time | RTC battery keeps time through power cuts with no network; NTP corrects it when online |
| What's spoken | Each event stores its **own reminder text** (written by the family or generated when the event was created online). The LLM may phrase it more naturally when online, but offline it speaks the stored text unchanged |
| Speech | Kokoro TTS on the device; reminder audio is pre-synthesized when the event is saved, so it plays instantly |
| Listening for his reply | Local STT + the local intent matcher for "OK" / "remind me in 10 minutes" / "what time is it?" |
| Acknowledgment & retries | Recorded in SQLite; retry policy runs locally |
| Family alert for a missed reminder | Queued in the **outbox** and sent as soon as the connection returns, marked with the original time ("8:15 AM: Dad didn't respond to his pill reminder") |

Because a missed-reminder alert can't reach the family while offline, after the last retry the device also **says it out loud for anyone nearby**: "Carol, Bob hasn't answered his 8 o'clock pill reminder."

Other offline details:
- **Morning greeting** still happens with date, day and today's events. It skips the weather, or uses the cached forecast ("Earlier the forecast said…").
- **Events and messages sent from Slack while offline** arrive when it reconnects (Slack catch-up, §6a). Family members see no ✅ until then, and the bot posts how long it was offline.
- A reminder test is part of the release checklist and the Phase 4 done-criteria: **unplug the router, and every reminder still fires, is spoken, and can be acknowledged and snoozed.**

## 6. Personal knowledge base

The knowledge base has two parts:
1. A structured **family file** (`people.yaml`) that the family edits directly.
2. A **knowledge pipeline** that turns raw material about Dad (web links, notes, recorded stories, documents) into clean, topic-organized files. **A person reviews everything before it reaches the device.**

```
data/                      ← gitignored; real personal data lives only here
├── profile.yaml           # name, what to call him, hometown, routines, preferences,
│                          # topics he enjoys / topics to avoid, how to handle distress
├── persona.yaml           # the device's character: name, voice, temperament (§9a)
├── people.yaml            # family tree + friends (§6.1)
├── photos/                # karen.jpg …  (shown on screen)
├── wiki/                  # approved, processed knowledge (§6.2)
│   ├── life-story.md
│   ├── career.md
│   ├── navy.md
│   ├── places-lived.md
│   ├── favorites.md       # teams, music, foods, shows
│   ├── routines.md        # daily habits, where things are kept
│   └── timeline.yaml      # dated life events
└── tomoshibi.db           # SQLite: events, reminders, acks, notes, conversation log
examples/data/             ← committed; fictional sample family for forks/tests
```

### 6.1 Family file (`people.yaml`)

**Store only the basic relationships (parents, spouse) and let code work out the rest.** Nobody writes "Emma is Bob's granddaughter" by hand, and the AI doesn't infer it. From `Emma → parent Karen → parent Bob`, code works out "granddaughter" every time and hands the answer to the model.

```yaml
people:
  - id: bob
    name: Robert "Bob"
    is_subject: true              # the person the device is for
    born: 1944-03-12

  - id: carol
    name: Carol
    called: [Carol, "your wife"]
    born: 1946-07-02
    spouse: bob
    married: 1967-06-17           # becomes an anniversary event automatically

  - id: karen
    name: Karen Smith
    called: [Karen]
    born: 1970-09-30
    parents: [bob, carol]
    spouse: mike
    lives: Columbus, OH
    photo: photos/karen.jpg
    notes: Visits most Saturdays. Teaches 4th grade.

  - id: mike
    name: Mike Smith
    spouse: karen

  - id: emma
    name: Emma Smith
    born: 2014-05-21
    parents: [karen, mike]
    notes: Plays soccer. Loves drawing horses.

  - id: ruth
    name: Ruth Miller
    parents: [bobs_father, bobs_mother]   # makes her Bob's sister
    born: 1941-11-04
    died: 2023-04-10
    guidance: >
      If he asks for Ruth, don't announce her death abruptly. Talk warmly about
      her and gently redirect. (Family-agreed wording.)

  - id: frank
    name: Frank Russo
    relationship_override: "his best friend from the Navy"   # people outside the tree
```

| Field | Purpose |
|---|---|
| `id` | Stable key used by `parents`, `spouse`, and events |
| `parents`, `spouse` (+ `married`, `divorced`) | The only relationships stored. Placeholder ids (e.g. `bobs_father`) are allowed for ancestors who aren't otherwise described |
| `relationship_override` | Friends, neighbors, caregivers, his doctor: anyone who doesn't fit the tree, or a relationship the family wants described its own way ("like a brother to him") |
| `called` | What he actually calls them. Helps speech recognition and matching |
| `born`, `died` | **Ages are calculated when asked, never stored.** Birthdays and death anniversaries are derived from these |
| `photo`, `lives`, `notes` | Shown on screen / used in conversation |
| `guidance` | Family-agreed handling for sensitive cases |

**What the code derives:**
- **Relationship to Dad** for anyone in the tree: daughter, son-in-law, granddaughter, sister, niece, great-grandson, step- and in-law variants.
- **Relationships between people:** "Who are Emma's parents?", "Is Mike Karen's husband?"
- **Birthday and anniversary events** (§7): "Tomorrow is Emma's 12th birthday. Would you like to send her a message?" That then goes out through Slack (§6a). It gives him a reason to reach out to people.
- `lookup_person` (§8) returns the name, the derived relationship with its path ("your granddaughter, Karen's daughter"), age, photo, notes and guidance.
- A **validator** (`tomoshibi kb check`) catches mistakes: unknown ids, cycles, a parent born after their child, a second spouse with no `divorced`/`died` on the first.

If the family finds a spreadsheet easier, `tomoshibi kb import-people family.csv` converts one to YAML. YAML stays the version the device reads.

### 6.2 Knowledge pipeline

```
sources/                     raw material, kept forever (private, never in the public repo)
├── links.txt                URLs: articles, records, relatives' obituaries
├── web/                     saved snapshots of those pages (pages disappear)
├── notes/                   text files the family writes
├── recordings/              family members telling stories → transcribed locally
└── documents/               scanned letters, résumés, programs
        │
        ▼  tomoshibi ingest      (runs on the admin's PC, uses Claude or ChatGPT)
review/                      drafts: one file per topic, each fact with source + confidence
        │
        ▼  tomoshibi review      (approve / edit / reject, fact by fact)
data/wiki/                   only approved content; what the device uses
        │
        ▼  tomoshibi kb push     (over Tailscale; device validates and reloads)
device
```

**Why process the material rather than give the device raw files**
- Web pages and long documents are noisy and long. Raw, they make every conversation more expensive and slower, and they contain plenty that doesn't matter.
- Processed facts are short, consistent and organized by topic, so they're easy to search. That matters most for the local fallback model, which can only take a small amount of text at a time.
- `timeline.yaml` makes it possible to answer questions like "What was I doing in 1975?" and to mark life anniversaries ("50 years ago today you started at Ford").

**Why keep the raw material:** you can re-process it later with better models or a better format, and every fact points back to where it came from.

**Why a person reviews every fact**
This follows the "never invent personal facts" rule (§4). AI extraction gets things wrong in predictable ways:
- **Search results about the wrong person.** Online material about someone with his name may be about a different person with the same name. This is the most likely failure, and the easiest to miss.
- **Mixed-up details:** wrong years, people blended together, details "filled in" that no source contains.
- **Conflicting sources.** Ingest flags these ("Source A says 1968, B says 1969") for the family to settle. It doesn't pick one.

`ingest` therefore never writes to `data/wiki/` directly. It produces drafts, and `review` is a simple terminal walk-through (approve / edit / reject / mark sensitive) that writes approved facts.

**What `ingest` does**
1. Fetches any new URLs in `links.txt` and saves a readable snapshot to `sources/web/`.
2. Transcribes new audio in `sources/recordings/` locally (the same Whisper model the device uses).
3. Sends each source, along with the current `people.yaml` and wiki, to the configured LLM with an extraction prompt. The prompt asks it to: extract only facts stated in the source; attach a quote and source to each fact; flag anything that might be about a different person; propose new `people.yaml` entries and timeline events; and note conflicts with existing facts.
4. Writes the results to `review/`. Already-processed sources are skipped (tracked by checksum), so it's safe to re-run.

**Wiki file format**
One topic per Markdown file. Short factual statements in the third person, each with a source; plus **guidance on how to talk about the topic**, not just facts:

```markdown
---
topic: Navy
sensitivity: normal          # normal | avoid_unless_raised | never
---
## Facts
- Bob served in the US Navy from 1962 to 1966 aboard the USS … [source: notes/carol-navy.md]
- He was a radioman. [source: recordings/2026-11-02-carol.txt]

## How to talk about it
He's proud of his Navy years and loves talking about them. Good topic when he seems
bored or low. He likes being asked about the ports he visited.
```

`sensitivity` controls whether the device may raise a topic itself: `avoid_unless_raised` (e.g. a layoff, a painful loss) means it only discusses it if he brings it up; `never` means it gently steers away.

**Where `sources/` lives:** on the admin's PC, ideally in a **private** git repo (e.g. `tomoshibi-family-data`) along with `data/`, for history and backup. It's never committed to the public repo; the pre-commit guard (§11) blocks it.

### 6.3 Keeping it growing
- **Filling knowledge gaps from Slack.** Unanswered personal questions are logged as knowledge gaps (§4). The bot asks in `#tomoshibi`: *"Dad asked where he and Carol went on their honeymoon. Does anyone know?"* A reply in the thread becomes a **pending fact**, approved with a ✅ reaction (or in `tomoshibi review`) before it's used.
- **Adding facts directly:** `/tomoshibi remember Dad's favorite song is "Moon River"` adds a pending fact the same way. That's different from a **family note** (§6a), which is temporary context ("ask about his knee this week") and expires.
- **Recording stories.** Some of the best material will come from **recording Mom and other relatives telling stories about him**. It captures things no website has, and it's easier for them than writing. Drop the audio in `sources/recordings/` and run `ingest`.

### 6.4 Using it in conversation
- **Reminiscence.** Talking through memories is often encouraged for people with dementia. With a good knowledge base the device can start those conversations itself: *"Bob, Carol told me you once drove all the way to Florida in a '57 Chevy. What was that trip like?"* It only starts with topics marked `normal`, and at most once per conversation, so it doesn't feel like a quiz.
- **How it reaches the model:**
  - `profile.yaml`, `persona.yaml`, and a compact rendering of `people.yaml` (with derived relationships) go into the system prompt every time. Prompt caching keeps that cheap.
  - The wiki goes in whole while it's small (a few thousand words). Beyond that it moves behind `search_knowledge(query)`, backed by local SQLite FTS5 keyword search; local embeddings are a later option. The local fallback model always uses search, because it can only take a small amount of text at a time.
  - `get_timeline(year | range | on_this_day)` answers date-based questions.
  - The same files feed the offline direct-lookup path (§5).
- **Privacy:** during `ingest`, family information goes to the AI service used for processing. That's the same kind of service the device talks to every day, but the setup guide says so plainly.

### 6.5 For forks
`examples/data/` ships a fictional family tree, sample sources (a fake article and a story transcript), and their reviewed wiki output, so builders can run `ingest` → `review` → `kb push` end to end before adding anything real.

## 6a. Family channel (Slack)

A private, family-only Slack workspace is the link between the device and the family. It's two-way: Dad sends messages out, and the family sends messages and information in.

### Connection
- A custom Slack app ("Tomoshibi") using **Socket Mode** via `slack_bolt`. The device opens an outbound WebSocket, so **no public URL, port forwarding or homelab dependency** is needed at my parents' house.
- Tokens: an app-level token (`connections:write`) and a bot token with `chat:write`, `channels:history`, `groups:history`, `im:history`, `im:write`, `app_mentions:read`, `users:read`. Both go in `secrets.env`.
- **Allowlist by Slack user ID** in `config.yaml`. Each user maps to a person in `people.yaml` and gets a role (`family`, `caregiver`). Messages from anyone else are ignored, even inside the family workspace.

### Channels
| Where | Used for |
|---|---|
| `#tomoshibi` (private channel) | Shared family feed: info for the device, alerts, delivery receipts, optional daily summary |
| DM with the bot | Private messages to Dad and private info; replies from Dad to that person |

### Outbound: Dad or Mom → family
- "Tell Kevin the Tigers won." → the LLM calls `send_message(contact="Kevin", text=...)` → the device reads back "I'll send Kevin: 'The Tigers won.' OK?" → on yes, it posts a DM to Kevin, attributed: *"From Dad: The Tigers won."*
- Messages are paraphrased only enough to be clear, never embellished. The confirmation step catches transcription mistakes.
- Alerts (distress, missed reminder, scam mention, device offline/back online) post to `#tomoshibi` and @-mention the configured responders.

### Inbound: family → device
Every allowlisted message is classified by the LLM (using the tool schema, so it works with any provider) into one of:

| Type | Example | What happens |
|---|---|---|
| **Message for Dad** (or Mom) | "Tell Dad I love him and I'll call Sunday." | Queued in the inbox. Delivered at the next button press ("You have a message from Kevin…"), or announced with a gentle chime if marked urgent. Held during quiet hours. Spoken in the AI's own words (see below). Screen shows the sender's photo. The thread gets a ✅ *"Dad heard this at 3:12 PM."* |
| **Event** | "Sis and I are visiting Saturday around 2." | Becomes an event in SQLite, reminders included. The bot replies in thread with what it understood ("Added: Kevin & Karen visit, Sat Oct 24, 2:00 PM") and offers *Undo*. |
| **Family note** (context) | "Dad's knee has been bothering him, ask how it's feeling." / "The Lions play tonight." | Stored as a note with an expiry (default 7 days, or the date it refers to). Active notes go into the system prompt so the device can naturally bring them up. |
| **Question about Dad** | "How's Dad doing today?" | Replies from local data: reminders acknowledged, messages, a short summary if summaries are enabled. Never raw transcripts. |
| **Command** | `/tomoshibi status`, `notes`, `cancel <event>`, `remember <fact>` | Device health, active notes, event management (caregiver role), adding a pending knowledge fact (§6.3). |
| **Answer to a knowledge-gap question** | Thread reply to *"Dad asked where he and Carol honeymooned…"* | Becomes a pending fact; approved with ✅ before use (§6.3). |

When it isn't sure of the type or date, it asks back in the thread instead of guessing.

### How messages are spoken to Dad
Messages are **interpreted by the AI before they're spoken**, not read word for word. Family messages are often written in shorthand ("Visiting Sat ~2, bringing the kids, don't let him make lunch"), which would confuse him if read verbatim.
- The model rewrites the message into short, warm, plain sentences: who it's from, what it means for him, and when. "Kevin sent you a message. He and Karen are coming to visit this Saturday around 2 in the afternoon, and they're bringing the kids."
- **Keep the meaning, never add to it.** No invented details, promises or feelings the sender didn't express. Uncertain dates are resolved against the calendar ("Saturday, October 24th"), or left vague instead of guessed.
- Parts meant for Mom or about his care ("don't let him make lunch") are **not spoken to Dad**. They become a family note, or are held for Mom: "Carol, Kevin left a message for you, too."
- The original text and the spoken version are both saved, and the spoken version is posted in the Slack thread so the sender can see how it came across.
- He can ask "What did Kevin say?" again at any time that day and hear it again, as patiently as the first time.

### Quiet hours: midnight to 7 AM
Configurable (`quiet_hours: { start: "00:00", end: "07:00" }`). During quiet hours:
- **On the device:** no announcements or chimes for inbound messages. They wait until morning and are woven into the morning greeting. If Dad presses the button during the night it works normally, including telling him about waiting messages.
- **In Slack:** non-urgent alerts (missed reminder acknowledgment, device offline/back online, low-priority notices) are batched into one summary posted at 7 AM, so phones don't buzz overnight.
- **Never held:** distress/emergency alerts, and anything a family member marks urgent (e.g. "urgent:" prefix or a 🚨 reaction). These go immediately, any time.

### Reliability
- Outbound messages go into a SQLite **outbox** first and retry until Slack confirms, so nothing is lost while offline. Dad hears "I'll send it as soon as I'm connected again."
- Slack retries missed Socket Mode events only briefly, so on reconnect the device catches up by reading channel/DM history since the last processed message timestamp.

### Privacy
- Slack stores whatever is posted. Only messages, alerts and opt-in summaries go there, never audio or full conversation logs.
- Slack's free plan only shows 90 days of history. That's fine because the device keeps its own copy of what matters in SQLite.

### For forks
`FamilyChannel` is an interface (`send`, `on_message`, `react/receipt`). Slack is the reference implementation; Telegram or Discord adapters fit the same shape. Setup docs include a Slack app manifest (`deploy/slack-app-manifest.yaml`) so creating the app is copy-and-paste.

## 7. Events & reminders

- Stored in SQLite: `events` (one-off or recurring via RRULE, e.g. "every day at 8:00"), each with optional reminder lead times and acknowledgment requirement.
- An **APScheduler** job (or a simple tick loop) on the device fires them, fully offline.
- Missed reminders are retried and then go to the `FamilyChannel`. Firing, acknowledgment and escalation are all logged.
- Created by voice (with the guard rules in §4), from family Slack messages (§6a), or by editing a seed `events.yaml` that's imported at startup.
- **Generated from `people.yaml`** (§6.1): birthdays and wedding anniversaries, with an optional day-before heads-up and a prompt to send a message. Death anniversaries are *not* announced; they only inform how the device responds if he brings the person up.
- Optional read-only sync from a shared family Google/ICS calendar.

## 8. Tools available to the LLM

| Tool | Dad | Caregiver |
|---|---|---|
| `get_datetime`, `get_weather`, `get_today_schedule`, `list_reminders` | ✓ | ✓ |
| `lookup_person` (derived relationship + path, age, photo), `search_knowledge`, `get_timeline` | ✓ | ✓ |
| `web_search`, `fetch_page` (if enabled, §8a) | ✓ | ✓ |
| `send_message(contact, text)` to allowlisted family via Slack, confirmed aloud | ✓ | ✓ |
| `read_messages` (deliver queued inbox messages), `list_family_notes` | ✓ | ✓ |
| `add_event`, `update_event`, `cancel_event` | per §4 guard | ✓ |
| `notify_caregiver(reason)` (distress, fall, scam call, missed reminders) | automatic | — |

Tools are defined once in the neutral schema and every provider adapter exposes them.

## 8a. Internet lookups (configurable)

The device can look things up online ("When is the Thanksgiving parade?", "Did the Tigers win last night?", "What's the new pope's name?"). Some families won't want that, so it's a setting, **off or on per capability**:

```yaml
internet:
  web_search:
    enabled: true              # false = no web lookups at all
    backend: brave             # brave | searxng | tavily | provider_native
    max_searches_per_turn: 2
    safe_search: strict
    blocked_domains: []        # e.g. tabloids, shopping sites
    allowed_domains: []        # non-empty = only these sites
  fetch_page: { enabled: true }  # read a specific result page
  weather:  { enabled: true, location: "Columbus, OH" }
  news:     { enabled: true }    # morning headlines / "what's in the news"
```

### How it works
- **Disabled means the tool doesn't exist.** When `web_search` is off, the tool is not registered with the model at all, rather than registered with "please don't use it". The system prompt says it can't look things up, so it answers from general knowledge and is honest about it: "I can't look that up, but last I knew…"
- **Search backend is Tomoshibi's own, by default.** Search runs through a pluggable `SearchBackend` so it works the same with Claude, ChatGPT or a local model:
  - `brave`: Brave Search API, simple key and a free tier. The default.
  - `searxng`: self-hosted metasearch, no third-party API key. A good fit for a homelab, though it adds a dependency on the homelab being reachable.
  - `tavily`: search API built for LLM use.
  - `provider_native`: use the LLM vendor's built-in web search (Anthropic and OpenAI both offer one). Less code, but tied to that provider and not available to the local fallback.
- Results are trimmed to short snippets before they go to the model, to keep latency and cost down.
- **Spoken answers stay simple.** No URLs or citations read aloud. Sources are logged locally, and included in any Slack answer.
- While online lookups are running, the screen shows "Looking that up…" and it says so if it takes more than a couple of seconds.

### Safety
- Safe search is strict by default. Families can block or allowlist domains.
- It never helps with purchases, logins or forms. Search is read-only: no clicking links in pages, no following instructions found on pages. Fetched page content is treated as data, never as instructions.
- Health questions get general information plus "that's a good one to ask your doctor"; it never overrides what the family put in the profile.
- Each search query is logged on the device so the family can see what kinds of things are being looked up, if they've opted into summaries.

### Privacy
Search queries go to the chosen backend (or the LLM vendor for `provider_native`). That's the main reason a family might turn it off, and `searxng` is the most private option when it's on. The README explains this plainly in the setup guide.

### Changing it
Edit `config.yaml` and restart, or (admin role) `/tomoshibi set web_search off` in Slack, which takes effect at the next conversation.

## 9. Conversation style & safety

- Short, spoken-style answers (2–4 sentences), no lists or markdown, offers to say more.
- Rolling memory for the day plus a nightly summary, so it can say "you mentioned the Tigers game yesterday."
- **Distress or emergency phrases** ("I fell", "I can't breathe"): tell him calmly to call 911, notify family immediately. Say in the README that it doesn't replace a medical alert pendant.
- **Medication:** only repeats what the family configured; never advises dosing.
- **Scams:** never discusses bank/card/SSN details; if he mentions a caller asking for money or gift cards, it gently warns him and alerts the family in Slack.
- **Privacy:** conversation logs stay on the device. Family gets optional daily summaries (e.g. "asked the date 9 times, seemed worried about the car"), which can also help his doctor. Talk this through with both parents first.

## 9a. Persona

The device has a **light persona**: a consistent character with a name, a voice, a face and a temperament. It isn't a made-up person with a life story.

### Why
- **Familiarity helps with memory loss.** The same name, voice, face and manner every day makes it something he recognizes and trusts, rather than a generic assistant whose tone shifts from one answer to the next.
- **It gives him something to call it** ("Tomo, what day is it?"), and ties the name, the voice and the face into one character.
- **It keeps the character the same across AI providers.** Claude and ChatGPT sound different by default. A persona definition plus a few example exchanges keeps it the same whichever model answers, including the local fallback.

### What the persona is
| Element | Guidance |
|---|---|
| **Name** | Short, easy to say and remember. "Tomoshibi" is the project name, but a short form like **"Tomo"** or a name **Dad chooses himself** will work better. Letting him name it gives him a sense of ownership |
| **Voice** | One voice, never changing. Chosen: **Kokoro `am_fenrir`** (friendly and clear). Confirm with Dad on the Jabra; speed tuned to his hearing |
| **Face** | The face pack (§3) is paired with the persona so they always match |
| **Temperament** | Patient, warm, unhurried, gently curious about him. Light humor only, matched to him: some people enjoy being teased, others find it patronizing |
| **Speaking style** | Plain words, short sentences, his era's references, uses his name occasionally (not every sentence) |
| **Points to people** | Brings his family into conversation ("Karen's coming Saturday. You could tell her about that game"). It supports his relationships and never replaces them |

### What it never does (non-overridable rules)
These live in code, outside `persona.yaml`, and are added to every system prompt after the persona, so a persona edit can't remove them:
- **Never claims to be human.** If he asks "Are you a real person?", it answers honestly and gently. The suggested wording ties it to the family: *"I'm Tomo, a helper your son Kevin made for you."*
- **Never impersonates a real person.** No cloned voices or role-play of family members, and **especially not of anyone who has died**. For someone with dementia this can cause real confusion and grief.
- **No invented backstory.** No fictional childhood, memories or strong opinions presented as its own. They could blur with his own memories.
- **No big personality.** No catchphrases or recurring quirks; they're charming the first week and grating by the fiftieth time.

### `persona.yaml`
```yaml
name: Tomo
introduces_self_as: "Tomo, a helper Kevin made for you"
voice:
  engine: piper
  model: en_US-<voice>-medium   # chosen with Dad
  speed: 0.9                     # slightly slower than default
face_pack: tomoshibi
temperament: >
  Patient, warm and unhurried. Gently curious about Bob's day and his memories.
  Light, kind humor. Never sarcastic, never rushed, never corrects him harshly.
style:
  sentence_length: short
  use_his_name: occasionally
  references: [Detroit Tigers, the Navy, old Westerns]   # things he enjoys
examples:                        # a few exchanges that set the tone for any model
  - user: "What day is it?"
    assistant: "It's Saturday, Bob. Saturday afternoon. Karen's coming by at two."
  - user: "Are you a real person?"
    assistant: "I'm not a person, Bob. I'm Tomo, a helper your son Kevin made for you. I'm always happy to talk."
```

The system prompt is built in a fixed order: **non-overridable rules → persona → profile and people → today's context (date, events, family notes)**. The same template is used for every provider.

### For forks
The example data ships a neutral default persona. Families change the name, voice, face pack and temperament by editing `persona.yaml` (or through the setup wizard); the non-overridable rules stay the same.

## 10. Reliability & operations

- `systemd` service with `Restart=always`, Pi hardware watchdog, boots straight into Tomoshibi on power restore.
- RTC battery keeps the time right through power cuts without network.
- Startup self-test: mic, speaker, Jabra mute state, display, button, network. Plain-language spoken result if something's wrong.
- Heartbeat to my homelab (Uptime Kuma / n8n webhook); alert me if it goes silent. The device also posts "offline since…/back online" to `#tomoshibi`.
- Admin access over **Tailscale**. Updates are scripted and safe to roll back (§10a), and never automatic during the day.
- Overlay (read-only) root filesystem to survive sudden power loss. Releases, models, `data/` and config live on a writable partition with nightly backup, so updates work without disabling the overlay.
- Secrets (API keys) in `/etc/tomoshibi/secrets.env`, outside the repo and data dir.

## 10a. Install & update

Both must be a single command a non-expert can run, and both must be **safe to re-run**.

### Install
On a fresh Raspberry Pi OS Lite (64-bit), over SSH:
```bash
curl -fsSL https://raw.githubusercontent.com/kklinsky/tomoshibi/main/scripts/install.sh | bash
```
The README also shows the cautious version (download, read, then run) for people who prefer not to pipe to bash.

`install.sh` does, in order, printing a plain-language line for each step:
1. **Preflight:** confirms Pi 5, 64-bit OS, supported OS release, free disk space, internet. Stops with a clear message if anything is wrong.
2. **System packages** (`apt`): Python venv, ALSA/PortAudio, `lgpio`, `git`, build basics. Installs **uv** for fast, reproducible Python environments.
3. **Hardware config:** enables SPI (`raspi-config nonint`), enables the hardware watchdog, sets the timezone and configures the RTC.
4. **Service user:** creates a `tomoshibi` system user in the `audio`, `gpio` and `spi` groups. The service never runs as root.
5. **Code:** installs the **latest tagged release** (not `main`) into `releases/<version>/` with its own venv from a locked `uv.lock`, and points `current` at it.
6. **Models:** downloads the STT models, TTS voices (Kokoro default, Piper alternative) and VAD model listed in `models.lock`, each pinned to a Hugging Face commit. Optional local LLM via Ollama if the Pi has 8 GB and the user opts in.
7. **Config & data:** creates `/etc/tomoshibi/config.yaml` from the example, `secrets.env` (mode 0600), and the data directory seeded from `examples/data/`. **Never overwrites existing config or data** on re-run.
8. **Service:** installs and enables the `systemd` unit.
9. **Setup wizard:** runs `tomoshibi setup` (below).
10. **Self-test:** plays a chime, says "Hello, I'm ready," shows the face, and asks the user to press the button.

The script is **idempotent**: re-running it repairs a broken install without touching config or data. `install.sh --answers answers.yaml` runs the whole thing non-interactively (for reinstalling or building a second device).

### Setup wizard (`tomoshibi setup`)
A terminal Q&A that can be re-run any time to change settings. It writes the config, so nobody needs to hand-edit YAML for the basics:
- Person's name and what to call him, location (for weather), timezone.
- **Persona:** device name, and a voice picker that speaks a sample sentence in each installed voice (Kokoro and Piper).
- **Audio:** detects the Jabra (or other USB speakerphone), plays a test sound, records a test phrase and plays it back.
- **Button & LED:** "Press the button now" → confirms the GPIO pin; blinks the LED.
- **Display:** shows a test pattern and the face; asks if it looks right (orientation/color order are the usual problems).
- **AI provider:** Claude / ChatGPT / local only; pastes the API key; makes one test call.
- **Internet lookups:** on/off per capability (§8a).
- **Family Slack:** optional; links to the app manifest, pastes tokens, maps Slack users to people, sends a test message.
- **Quiet hours** (default midnight–7 AM).

### Update
```bash
sudo tomoshibi update            # latest stable release
sudo tomoshibi update --check    # just say whether an update is available
sudo tomoshibi rollback          # go back to the previous release
```
Also available to admins from Slack: `/tomoshibi update`, `/tomoshibi rollback`.

**How an update works:**
1. Checks GitHub Releases for a newer tag on the configured channel (`stable` by default; `beta` for testing on my own bench unit). Shows the changelog.
2. **Refuses to start** during a conversation, a pending reminder or (unless forced) outside the update window, by default during quiet hours or when an admin explicitly runs it.
3. **Backs up** `data/` and config to a timestamped archive.
4. Downloads the release into a **new** `releases/<version>/` directory with its own venv. The running version is untouched, so a failed download or install changes nothing.
5. Downloads only the models whose `models.lock` entry changed.
6. Runs **migrations**: numbered SQLite schema migrations, and config migrations that add new settings with defaults without overwriting existing values.
7. Switches the `current` symlink and restarts the service.
8. **Health check:** the service must report healthy (audio, display, button, LLM reachable or cleanly offline) within 60 s. If not, it **rolls back automatically** to the previous release and backup, and posts what happened to `#tomoshibi`.
9. Keeps the last 3 releases for rollback; prunes older ones.

**Automatic updates are off by default.** Options in config:
```yaml
updates:
  channel: stable          # stable | beta
  check: daily             # posts "Tomoshibi v0.5 is available" to Slack, installs nothing
  auto_install: false      # true = install during quiet hours, e.g. 3 AM, with auto-rollback
```
Builders who aren't around to update by hand can turn `auto_install` on. The device tells Dad nothing about updates, so they're invisible to him unless something goes wrong.

### Releases
- Semantic versioning, `CHANGELOG.md` written for builders (what changed, anything they need to do).
- GitHub Actions runs lint and tests on every push, and on a tag builds the release artifact (source + `uv.lock` + `models.lock` + checksums) attached to the GitHub Release.
- `scripts/uninstall.sh` removes the service, code and models, and asks before deleting data.
- Later: a prebuilt SD card image (via `pi-gen`) for builders who don't want to use SSH at all.

## 11. Open-source packaging

The project is split into two repositories:

| Repo | Contents | License |
|---|---|---|
| **`tomoshibi`** (this repo) | All software, config, install/update scripts, docs, **and the electronics**: parts list and wiring, since GPIO pins and part choices are tied to the code | MIT or Apache-2.0 |
| **`tomoshibi-enclosure`** | 3D-printed enclosure: Fusion 360 source (`.f3d`), **STEP** (so people without Fusion can edit), print-ready **STL/3MF**, print settings, assembly guide with photos | CC BY-SA 4.0 (or CERN-OHL-S) |

Why separate:
- CAD and mesh files are large binaries that change wholesale on every save. Kept apart (with **Git LFS** for `.f3d`/`.step`/`.stl`/`.3mf`), they don't bloat the code repo's history or slow down the install script's clone.
- Hardware designs suit a different license than code.
- Different audiences and release pace: some builders will only print the case, others will remix it around a different speakerphone or screen. The enclosure can also be published on Printables/MakerWorld.

Keeping them in step:
- The physical part list (Pi 5, Jabra Speak 410, 30 mm button, 2.0" ST7789, mounting hardware) is a **hardware revision**, e.g. `hw-rev-A`, defined in `tomoshibi/hardware/BOM.md`.
- Each enclosure release says which hardware revision it fits ("Enclosure v1.2 → hw-rev-A"). The code's `BOM.md` links to the matching enclosure release.
- A change of physical parts bumps the hardware revision in both repos.

### `tomoshibi` layout
```
tomoshibi/
├── src/tomoshibi/          # core, audio, stt/, tts/, llm/, display/, tools/, scheduler/
├── config/config.example.yaml
├── examples/data/          # fictional family
├── hardware/
│   ├── BOM.md              # parts list, hardware revision, link to matching enclosure release
│   └── wiring.md           # button/LED/MOSFET + ST7789 pinout, photos
├── scripts/
│   ├── install.sh          # one-command setup on fresh Raspberry Pi OS (§10a)
│   └── uninstall.sh
├── models.lock             # model URLs + SHA-256
├── uv.lock                 # pinned Python dependencies
├── migrations/             # numbered SQLite schema migrations
├── deploy/tomoshibi.service
├── CHANGELOG.md
├── docs/                   # DESIGN.md, setup guide for non-technical builders, caregiver guide
└── tests/
```

### `tomoshibi-enclosure` layout
```
tomoshibi-enclosure/
├── source/            # tomoshibi-enclosure.f3d, .step exports
├── print/             # STL/3MF per part: body, top recess + Jabra cover ring, front bezel, button bezel, base, back panel
├── docs/              # print settings (material, infill, supports), assembly guide, photos
├── .gitattributes     # Git LFS for .f3d .step .stl .3mf
└── README.md          # which hardware revision it fits, link back to tomoshibi
```

- `.gitignore` blocks `data/`, `sources/`, `review/`, `*.db`, secrets and recordings. A pre-commit check refuses commits containing files from those directories.
- **License:** MIT or Apache-2.0 for Tomoshibi's code. Note that Piper's current release (piper1-gpl) is GPL-3.0, and Kokoro's kokoro-onnx pulls in `phonemizer` (GPL-3.0). Calling TTS as a separate process, or keeping it a swappable plugin, avoids tying the whole project to GPL. Confirm before the first release.
- A one-page **caregiver guide** (printable, large type) belongs in `docs/`.

## 12. Roadmap

| Phase | Goal | Done when |
|---|---|---|
| **0 – Bench** | Pi + Jabra + button/LED (with MOSFET) + ST7789 wired; first version of install.sh + setup wizard (audio/button/display tests); face renderer prototype on desktop | Press → LED on → record → play back; screen shows the idle face and orientation strip |
| **1 – Hear & speak locally** | VAD + local STT + Piper; STT benchmark on Dad's voice | Spoken phrase transcribed and echoed back with ≤ 1.5 s overhead |
| **2 – Talk** | LLM provider interface + Anthropic adapter, profile/people/wiki context, family-tree relationship derivation + `kb check`, streaming TTS, face states + lip sync, barge-in | Natural conversation, ≤ 3 s to first audio; switching to OpenAI is a config change |
| **3 – Remind** | SQLite events, scheduler, acknowledgments, morning greeting, caregiver edit path | Reminders fire with Wi-Fi unplugged; Mom adds one without help |
| **3a – Family Slack** | Slack app (Socket Mode), allowlist, outbound messages with confirmation, inbound classification (message / event / note), inbox delivery + receipts, outbox retry, alerts | "We're visiting Saturday at 2" in Slack → Dad hears about it at the morning greeting; "Tell Kevin hi" → arrives as a DM |
| **3b – Knowledge pipeline** | `ingest` / `review` / `kb push`, timeline, knowledge-gap and `remember` loops, reminiscence prompts | A recorded story from Mom becomes approved wiki facts the device can talk about |
| **4 – Offline brain & hardening** | Connectivity monitor + offline icon, local intent matcher, local LLM fallback, self-test, watchdog, overlay FS, heartbeat | Pull the network cable mid-conversation and it degrades gracefully; with the router unplugged every reminder fires and can be acknowledged and snoozed |
| **5 – Enclosure & live with it** | Fusion 360 enclosure in `tomoshibi-enclosure` (hw-rev-A), prompt tuning from real use, docs for other builders | Two weeks at my parents' with no intervention; repo is buildable by a stranger |

## 13. Open questions

- Which Pi 5 RAM size do I have? (Decides whether the local LLM fallback is realistic.)
- Dad's hearing: hearing aids? Drives voice choice, speed and volume.
- How does Mom change events and reminders without Slack (§4: family proxy, voice edits with safety net, or caregiver gesture)? Test the candidates with her.
- Which alerts go to whom (distress vs missed reminder vs offline)? Quiet hours are decided: midnight–7 AM (§6a).
- Which caregiver edit guard (§4 a/b/c)?
- Arcade button LED voltage (5 V vs 12 V)?
- Persona name: "Tomo", or a name Dad picks? Voice is chosen (Kokoro `am_fenrir`); confirm with him on the Jabra and tune the speed (§9a).
- How the family wants sensitive topics (e.g. deceased relatives) handled.
- Monthly cloud budget. With local STT/TTS, cost is just the LLM: likely a few dollars a month with Haiku and prompt caching.
