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

1. **One obvious action.** One lit arcade button on top. Press it, talk.
2. **Endless patience.** Repeated questions get the same warm, complete answer every time. It never says "you already asked that."
3. **It speaks first when it matters.** Reminders and the morning greeting happen without Dad having to ask.
4. **Local first.** Speech recognition, speech synthesis, reminders, the clock and the personal knowledge base all run on the Pi. Only the "big brain" (the LLM) needs the internet, and there's a local fallback for that too.
5. **Provider-agnostic.** Claude by default; ChatGPT, Ollama or anything else through a small adapter and a config change.
6. **Private by default.** Personal data lives in a data directory that is never committed. The public repo ships only example data.
7. **Fails gently.** When something is down it says so in plain words, and reminders still work.

## 3. Hardware

| Part | Notes |
|---|---|
| Raspberry Pi 5 | **8 GB recommended** if running a local fallback LLM; 4 GB is fine for STT/TTS only. Active cooler, official 27 W USB-C PSU, RTC battery. |
| Jabra Speak 410 (USB) | Full-duplex speakerphone with echo cancellation, good pickup across a room. Appears as a standard USB audio device. **Its touch buttons (mute, volume, call) are easy to hit by accident.** The enclosure should cover mute/call, or the software should detect mute and say "I'm muted, press the button with the line through it." |
| Arcade button with built-in LED | Input on a GPIO with internal pull-up. **Check the LED voltage:** most are 5 V or 12 V with an internal resistor. GPIO pins are 3.3 V / ~16 mA, so drive the LED through a small N-channel MOSFET or NPN transistor (5 V from the Pi header). Use PWM for a "thinking" pulse. |
| 2.0" 320×240 IPS TFT, ST7789 (Adafruit EYESPI) | SPI. Connect via an EYESPI adapter (e.g. EYESPI Pi Beret) or jumper wires to SPI0. The microSD slot on the breakout isn't needed. |
| 3D-printed enclosure (Fusion 360) | Lantern/lamp form to suit the name. Button on top, screen angled toward a seated person, Jabra seated with its grille unobstructed. Weighted base, cable strain relief, ventilation for the Pi. Source `.f3d` + `.step` + `.stl` go in `hardware/enclosure/`. |

### Screen: an animated face
The screen's main job is to give Tomoshibi a **friendly animated face**, so it feels like someone to talk to rather than a gadget. It never needs to be touched or navigated.

#### Face design guidelines
- **Simple and cartoon-like, not realistic.** Two large eyes and a simple mouth (think a friendly robot or a lantern character). Realistic human faces can be confusing or unsettling for someone with dementia, who may believe a real person is inside the device.
- **Calm.** Slow, smooth motion; no sudden jumps, flashing or fast colors. Soft warm palette on a dark background (less glare, readable across a room).
- **Consistent.** The same face every day. Expressions change, the character doesn't.
- **Expressive in a few clear ways** instead of many subtle ones.

#### Face states
| State | Face | Button LED |
|---|---|---|
| **Idle** | Relaxed, occasional blink, gentle "breathing", eyes drift slowly | off (or dim glow) |
| **Listening** | Eyes wide and attentive, slight lean/tilt, mouth closed | **on** |
| **Thinking / looking up** | Eyes glance up and to the side, small animated "…" | slow pulse |
| **Speaking** | Mouth moves in time with the voice | on, dim |
| **Happy** (greetings, good news, family messages) | Smiling eyes | — |
| **Concerned** (distress, he sounds upset) | Soft, sympathetic eyes; never alarmed-looking | — |
| **Reminder** | Gentle "ahem" look, then the reminder card (below) | slow pulse |
| **Sleeping** (quiet hours) | Eyes closed, dimmed screen; wakes with a stretch when the button is pressed | off |
| **Offline / problem** | Normal face plus a small, clear indicator in the corner; never a sad or broken face | — |

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

### Dad
1. **Press the button** → chime, LED on, the face looks up attentively.
2. Speak. The turn ends after ~1.5 s of silence (voice-activity detection, tuned generously for slower speech) or on a second press.
3. LED pulses and the face shows "thinking" → the answer is spoken while the face's mouth moves with the voice.
4. **Pressing during an answer stops it** and starts listening again (barge-in).
5. Optional follow-up window: listen for a few seconds after an answer without another press. Off by default; turn on if it suits Dad.

No wake word in v1. They false-trigger on TV audio and are one more thing to remember. Wake word support (openWakeWord) can be added later as an option, never as a replacement for the button.

**Reminders:** chime, LED slow-pulses, text on screen, spoken message. Press to acknowledge. If there's no acknowledgment it repeats twice over 15 min, then alerts the family in Slack (configurable).

**Morning greeting:** at a set time or on the first press of the day: "Good morning, Bob. It's Saturday, October 17th. It's sunny and 58 degrees. Karen is visiting at 2 o'clock."

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
| `TextToSpeech` | **Piper** (fast on a Pi 5, many voices) | Kokoro-82M (more natural, slower; benchmark on Pi 5) |
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
| Local TTS, first sentence | ≤ 0.4 s |

Stream the LLM output, split it into sentences, and synthesize and play sentence by sentence so speech starts before the full answer exists.

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

## 6. Personal knowledge base

Human-editable files, so family members can update them with any text editor and forks can see exactly what to fill in.

```
data/                      ← gitignored; real personal data lives only here
├── profile.yaml           # name, what to call him, hometown, routines, preferences,
│                          # topics he enjoys / topics to avoid, how to handle distress
├── people.yaml            # one entry per person
├── people/photos/         # karen.jpg …  (shown on screen)
├── wiki/                  # free-form Markdown: life story, career, places, pets,
│   ├── life-story.md      #   "where things are kept", medical context the family
│   └── ...                #   chooses to share
└── tomoshibi.db           # SQLite: events, reminders, acks, conversation log
examples/data/             ← committed; fictional sample family for forks/tests
```

`people.yaml` example:
```yaml
- name: Karen
  relationship: daughter
  aliases: [Karen, "my daughter"]
  photo: people/photos/karen.jpg
  notes: Lives in Columbus. Visits on Saturdays. Married to Mike; kids Emma (12) and Leo (9).
  sensitive: false
- name: Ruth
  relationship: sister
  deceased: 2023-04-10
  guidance: >
    If he asks for Ruth, don't announce her death abruptly. Talk warmly about her
    and gently redirect. (The family decides this wording.)
```

**How it reaches the LLM:**
- `profile.yaml` + `people.yaml` go into the system prompt every time (small and cached).
- `wiki/` goes in whole while it's small. Once it outgrows a few thousand words it moves behind a `search_knowledge(query)` tool backed by local SQLite FTS5 (keyword search). Local embeddings are a later option if keyword search proves insufficient.
- The same files feed the offline direct-lookup path.

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
| **Command** | `/tomoshibi status`, `notes`, `cancel <event>` | Device health, active notes, event management (caregiver role). |

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
- Optional read-only sync from a shared family Google/ICS calendar.

## 8. Tools available to the LLM

| Tool | Dad | Caregiver |
|---|---|---|
| `get_datetime`, `get_weather`, `get_today_schedule`, `list_reminders` | ✓ | ✓ |
| `lookup_person`, `search_knowledge` | ✓ | ✓ |
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

## 10. Reliability & operations

- `systemd` service with `Restart=always`, Pi hardware watchdog, boots straight into Tomoshibi on power restore.
- RTC battery keeps the time right through power cuts without network.
- Startup self-test: mic, speaker, Jabra mute state, display, button, network. Plain-language spoken result if something's wrong.
- Heartbeat to my homelab (Uptime Kuma / n8n webhook); alert me if it goes silent. The device also posts "offline since…/back online" to `#tomoshibi`.
- Admin access over **Tailscale**. Updates only when I trigger them, never automatically during the day.
- Overlay (read-only) root filesystem to survive sudden power loss; `data/` on a writable partition with nightly backup.
- Secrets (API keys) in `/etc/tomoshibi/secrets.env`, outside the repo and data dir.

## 11. Open-source packaging

```
tomoshibi/
├── src/tomoshibi/          # core, audio, stt/, tts/, llm/, display/, tools/, scheduler/
├── config/config.example.yaml
├── examples/data/          # fictional family
├── hardware/
│   ├── BOM.md              # parts list with links
│   ├── wiring.md           # button/LED/MOSFET + ST7789 pinout, photos
│   └── enclosure/          # .f3d, .step, .stl, print settings
├── scripts/install.sh      # one-command setup on fresh Raspberry Pi OS
├── deploy/tomoshibi.service
├── docs/                   # DESIGN.md, setup guide for non-technical builders, caregiver guide
└── tests/
```

- `.gitignore` blocks `data/`, `*.db`, secrets and recordings. A pre-commit check refuses commits containing files from `data/`.
- **License:** MIT or Apache-2.0 for Tomoshibi's code. Note that Piper's current release (piper1-gpl) is GPL-3.0. Calling it as a separate process, or keeping TTS a swappable plugin, avoids tying the whole project to GPL. Confirm before the first release.
- A one-page **caregiver guide** (printable, large type) belongs in `docs/`.

## 12. Roadmap

| Phase | Goal | Done when |
|---|---|---|
| **0 – Bench** | Pi + Jabra + button/LED (with MOSFET) + ST7789 wired; install script; face renderer prototype on desktop | Press → LED on → record → play back; screen shows the idle face and orientation strip |
| **1 – Hear & speak locally** | VAD + local STT + Piper; STT benchmark on Dad's voice | Spoken phrase transcribed and echoed back with ≤ 1.5 s overhead |
| **2 – Talk** | LLM provider interface + Anthropic adapter, profile/people/wiki context, streaming TTS, face states + lip sync, barge-in | Natural conversation, ≤ 3 s to first audio; switching to OpenAI is a config change |
| **3 – Remind** | SQLite events, scheduler, acknowledgments, morning greeting, caregiver edit path | Reminders fire with Wi-Fi unplugged; Mom adds one without help |
| **3a – Family Slack** | Slack app (Socket Mode), allowlist, outbound messages with confirmation, inbound classification (message / event / note), inbox delivery + receipts, outbox retry, alerts | "We're visiting Saturday at 2" in Slack → Dad hears about it at the morning greeting; "Tell Kevin hi" → arrives as a DM |
| **4 – Offline brain & hardening** | Local LLM fallback, self-test, watchdog, overlay FS, heartbeat | Pull the network cable mid-conversation and it degrades gracefully |
| **5 – Enclosure & live with it** | Fusion 360 enclosure, prompt tuning from real use, docs for other builders | Two weeks at my parents' with no intervention; repo is buildable by a stranger |

## 13. Open questions

- Which Pi 5 RAM size do I have? (Decides whether the local LLM fallback is realistic.)
- Dad's hearing: hearing aids? Drives voice choice, speed and volume.
- How does Mom change events and reminders without Slack (§4: family proxy, voice edits with safety net, or caregiver gesture)? Test the candidates with her.
- Which alerts go to whom (distress vs missed reminder vs offline)? Quiet hours are decided: midnight–7 AM (§6a).
- Which caregiver edit guard (§4 a/b/c)?
- Arcade button LED voltage (5 V vs 12 V)?
- Names/wording: what Dad calls the device, and how the family wants sensitive topics (e.g. deceased relatives) handled.
- Monthly cloud budget. With local STT/TTS, cost is just the LLM: likely a few dollars a month with Haiku and prompt caching.
