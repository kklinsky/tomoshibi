"""The conversation loop (docs/DESIGN.md §4, use case 1).

press -> chime -> listen -> transcribe -> stream reply -> speak sentence by sentence ->
listen for a follow-up -> ... -> back to idle when nobody speaks.

For now a keyboard key stands in for the arcade button, and the face and button light
are shown as lines in the terminal.
"""

import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from tomoshibi import audio, intents, llm, models, paths, prompt, pronunciation
from tomoshibi import config as cfg
from tomoshibi import events as events_mod
from tomoshibi import stt as stt_mod
from tomoshibi import tts as tts_mod
from tomoshibi.events import Events
from tomoshibi.pronunciation import Pronouncer
from tomoshibi.sentences import SentenceSplitter
from tomoshibi.vad import Endpointer, SileroVAD
from tomoshibi.weather import US_STATES as _US

PRE_ROLL_FRAMES = 10  # keep ~0.3 s before speech was detected, so first syllables aren't lost
MAX_HISTORY = 24      # messages kept for context within the day
GOODBYE = re.compile(r"\b(that'?s all|goodbye|good night|bye|that will be all|never mind)\b", re.IGNORECASE)

SORRY_OFFLINE = "I'm sorry, I can't reach the internet right now. Please try me again in a little while."
SORRY_SETUP = "I'm sorry, something's wrong with my setup. Please ask the family to take a look."


def status(text: str) -> None:
    print(f"  [{text}]", flush=True)


class Conversation:
    def __init__(self, conf: dict, lock_path: Path, typed: bool = False,
                 stt_name: str | None = None, tts_name: str | None = None):
        self.conf = conf
        self.typed = typed
        specs = models.load_lock(lock_path)
        device = cfg.get(conf, "audio.device", audio.DEFAULT_DEVICE)
        self.end_silence = cfg.seconds(cfg.get(conf, "conversation.end_of_speech_silence"), 1.5)
        self.follow_up = cfg.seconds(cfg.get(conf, "conversation.follow_up_window"), 10)
        self.first_wait = cfg.seconds(cfg.get(conf, "conversation.first_listen_window"), 8)

        tts_spec = models.find(specs, tts_name or cfg.get(conf, "speech.tts_model")) \
            if (tts_name or cfg.get(conf, "speech.tts_model")) else models.first_of_kind(specs, "tts")
        status(f"loading voice {tts_spec.name}")
        self.tts = tts_mod.load(tts_spec, length_scale=float(cfg.get(conf, "speech.tts_speed", 1.1)),
                                voice=cfg.get(conf, "speech.tts_voice"))
        self.speaker = audio.Speaker(device)
        if not typed:
            stt_spec = models.find(specs, stt_name or cfg.get(conf, "speech.stt_model")) \
                if (stt_name or cfg.get(conf, "speech.stt_model")) else models.first_of_kind(specs, "stt")
            status(f"loading speech recognition {stt_spec.name}")
            self.stt = stt_mod.load(stt_spec)
            vad_spec = models.first_of_kind(specs, "vad")
            self.vad = SileroVAD(vad_spec.local_dir() / vad_spec.files[0])
            self.device = device

        cfg.load_secrets()
        self.provider = llm.from_config(conf)
        self.events = Events(paths.data_dir())
        self.reminder_listen = cfg.seconds(cfg.get(conf, "reminders.listen_window"), 30)
        self.reminder_tune = self._load_tune(cfg.get(conf, "reminders.tune", "station"))
        self._last_talk_day = None
        self._data_stamp = None
        self._reload_data()
        self.tools, self.web_search = self._lookups(conf)
        if self.tools or self.web_search:
            status("lookups on: " + ", ".join([t.name for t in self.tools]
                                              + (["web_search"] if self.web_search else [])))
        self.history: list[dict] = []
        self.pressed = threading.Event()

    def _lookups(self, conf: dict):
        """Weather and web search, each only if switched on in config (docs/DESIGN.md §8a)."""
        profile = prompt._yaml(paths.data_dir() / "profile.yaml")
        home = cfg.get(conf, "internet.weather.location") or profile.get("location") or ""
        tools = []
        from tomoshibi.volume import Volume

        volume = Volume(cfg.get(conf, "audio.device", audio.DEFAULT_DEVICE),
                        int(cfg.get(conf, "audio.volume_floor_percent", 25)))
        try:
            volume.restore()
            tools.append(volume.tool())
        except (OSError, subprocess.CalledProcessError, AttributeError) as e:  # no mixer: no tool
            status(f"volume control unavailable: {e}")
        if cfg.get(conf, "internet.weather.enabled", False):
            from tomoshibi.weather import Weather

            tools.append(Weather(home, cfg.get(conf, "internet.weather.units", "fahrenheit")).tool())
        web = None
        if cfg.get(conf, "internet.web_search.enabled", False) and hasattr(self.provider, "web_search_tool"):
            city, _, region = home.partition(",")
            location = {k: v for k, v in {"city": city.strip(), "region": region.strip(),
                                          "country": "US" if region.strip().upper() in _US else None,
                                          "timezone": profile.get("timezone")}.items() if v}
            web = self.provider.web_search_tool(
                max_uses=int(cfg.get(conf, "internet.web_search.max_searches_per_turn", 2)),
                user_location=location or None,
                allowed_domains=cfg.get(conf, "internet.web_search.allowed_domains") or None,
                blocked_domains=cfg.get(conf, "internet.web_search.blocked_domains") or None,
            )
        return tools, web

    # --- the button -------------------------------------------------------------------
    def press(self) -> None:
        self.pressed.set()

    def start_button(self) -> None:
        from tomoshibi.keys import KeyButton

        button = KeyButton(self.press)
        if button.devices:
            status(f"press Space or Enter on the keyboard to talk ({len(button.devices)} keyboard(s))")
        # Enter in this terminal works too, which helps over SSH.
        threading.Thread(target=self._stdin_button, daemon=True).start()

    def _stdin_button(self) -> None:
        for _ in sys.stdin:
            self.press()

    # --- main loop --------------------------------------------------------------------
    def run(self) -> None:
        if self.typed:
            self._run_typed()
            return
        self.start_button()
        status("idle: face relaxed, light off")
        while True:
            if self.pressed.wait(timeout=10):
                self.pressed.clear()
                self.session()
                status("idle: face relaxed, light off")
            if self.give_due_reminders():
                status("idle: face relaxed, light off")

    def _run_typed(self) -> None:
        status("type a question and press Enter (Ctrl-D to quit)")
        for line in sys.stdin:
            text = line.strip()
            if text:
                self.respond(text)

    def session(self, first_text: str = "", note: str = "") -> None:
        if not first_text:
            self.speaker.play(audio.chime(), 24_000)
            self.speaker.finish()
            self.speaker.wait()
        wait = self.first_wait
        while True:
            text, first_text = (first_text or self.listen(wait)), ""
            if not text:
                status("no reply: settling back to idle")
                return
            interrupted = self.respond(text, note)
            note = ""
            if GOODBYE.search(text) and not interrupted:
                return
            wait = self.follow_up

    # --- reminders (docs/DESIGN.md §4, use case 2) ------------------------------------------
    def give_due_reminders(self) -> bool:
        """Give any reminders that are due, then listen for a reply. Returns True if any were
        given. Reminders use fixed words, local speech and the local reply matcher, so they
        work with no internet; only a reply that's a new question goes to the AI."""
        self._reload_data()
        now = datetime.now()
        due = self.events.due(now)
        if not due:
            return False
        words = [events_mod.reminder_words(r, self.person, now) for r in due]
        status("reminder: face wakes and looks up")
        print("  reminder: " + " ".join(words), flush=True)
        self.speaker.play(*self.reminder_tune)
        for sentence in words:
            self._speak(sentence, [])
        self.speaker.finish()
        self.speaker.wait()
        reply = self.listen(self.reminder_listen)
        if not reply:
            for r in due:
                if self.events.record(r, "attempted", now) == "missed":
                    status(f"missed: {r.occurrence.event.title} (would alert the family; Slack isn't built yet)")
                else:
                    status(f"no reply: will remind again in {events_mod.RETRY_MINUTES} minutes")
            return True
        kind, minutes = intents.reminder_reply(reply)
        if kind == "snooze":
            for r in due:
                self.events.record(r, "snoozed", now, minutes)
            self._say_now(f"All right, I'll remind you again in {minutes} minutes.")
            return True
        for r in due:
            self.events.record(r, "acknowledged", now)
        if kind == "ack":
            self._say_now("Okay.")
            return True
        # Something else: carry on as a conversation, with the reminder in mind.
        self.session(first_text=reply, note="You just gave this reminder: " + " ".join(words))
        return True

    def _load_tune(self, setting: str) -> tuple[np.ndarray, int]:
        """The sound before a reminder: the built-in station tune, the short press chime,
        or a family's own WAV file in their data folder (e.g. "sounds/our-tune.wav")."""
        if setting in (None, "", "station"):
            return audio.station_tune(), 24_000
        if setting == "chime":
            return audio.chime(), 24_000
        try:
            return audio.load_tune(paths.data_dir() / setting)
        except (OSError, ValueError, EOFError) as e:
            status(f"reminder tune {setting!r} couldn't be loaded ({e}); using the station tune")
            return audio.station_tune(), 24_000

    def _say_now(self, sentence: str) -> None:
        self._speak(sentence, [])
        self.speaker.finish()
        self.speaker.wait()

    # --- listening --------------------------------------------------------------------
    def listen(self, wait: float) -> str:
        status(f"listening: face attentive, light ON (up to {wait:.0f} s for speech)")
        self.pressed.clear()
        self.vad.reset()
        ep = Endpointer(end_silence=self.end_silence, wait_for_speech=wait)
        frames: list[np.ndarray] = []
        recent: list[np.ndarray] = []
        with audio.Microphone(self.device) as mic:
            while True:
                frame = mic.read()
                state = ep.update(self.vad.probability(frame))
                if state == "waiting":
                    recent = (recent + [frame])[-PRE_ROLL_FRAMES:]
                elif state == "speaking":
                    if not frames:
                        frames = list(recent)
                    frames.append(frame)
                    if self.pressed.is_set():  # a second press ends the turn
                        self.pressed.clear()
                        break
                elif state in ("done", "timeout"):
                    break
        if not frames:
            return ""
        status("thinking: face looks up, light off")
        t0 = time.perf_counter()
        text = self.stt.transcribe(np.concatenate(frames))
        print(f"  you: {text}   (heard in {time.perf_counter() - t0:.2f} s)", flush=True)
        return text

    # --- answering --------------------------------------------------------------------
    def _data_files(self) -> list[Path]:
        data = paths.data_dir()
        files = [data / n for n in ("persona.yaml", "profile.yaml", "people.yaml", "pronunciations.yaml")]
        return files + [data / "events.yaml"] + sorted((data / "wiki").glob("*.md"))

    def _reload_data(self) -> None:
        """(Re)read the family's files when any of them changed, so edits made while Tomo is
        running (the pronunciation tester, a new wiki page) apply from the next answer."""
        stamp = tuple((str(f), f.stat().st_mtime_ns) for f in self._data_files() if f.exists())
        if stamp == self._data_stamp:
            return
        if self._data_stamp is not None:
            status("family data changed: reloading")
        self._data_stamp = stamp
        self.stable = prompt.stable_prompt(paths.data_dir(), self.conf)
        self.pronouncer = Pronouncer(pronunciation.load(paths.data_dir()))
        profile = prompt._yaml(paths.data_dir() / "profile.yaml")
        self.person = str(profile.get("call_him") or profile.get("name") or "")
        self.people = (prompt._yaml(paths.data_dir() / "people.yaml").get("people")) or []
        self.event_tools = events_mod.tools(self.events, self.people, self.person)

    def _volatile(self, note: str = "") -> str:
        """The part of the prompt that changes: date and time, today's and tomorrow's plans,
        and a nudge to greet on the first conversation of the day."""
        now = datetime.now()
        parts = [prompt.today_context(now), events_mod.schedule_text(self.events, self.people, self.person, now)]
        if self._last_talk_day != now.date() and now.hour >= 5:  # no "good morning" at 1 AM
            self._last_talk_day = now.date()
            part = "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening"
            parts.append(f"This is your first conversation with {self.person or 'them'} today. Before "
                         f"answering, give a short good-{part} greeting with the day and date, and "
                         "mention today's plans if there are any.")
        if note:
            parts.append(note)
        return "\n\n".join(parts)

    def respond(self, text: str, note: str = "") -> bool:
        """Stream and speak the reply. Returns True if the button interrupted it."""
        self._reload_data()
        self.history.append({"role": "user", "content": text})
        self.pressed.clear()
        t0 = time.perf_counter()
        first_token = first_audio = None
        spoken: list[str] = []
        splitter = SentenceSplitter()
        interrupted = False
        try:
            for delta in self.provider.stream_reply(self.stable, self._volatile(note), self.history,
                                                    tools=self.tools + self.event_tools,
                                                    web_search=self.web_search):
                if first_token is None:
                    first_token = time.perf_counter() - t0
                for sentence in splitter.feed(delta):
                    self._speak(sentence, spoken)
                    first_audio = first_audio or time.perf_counter() - t0
                if self.pressed.is_set():
                    interrupted = True
                    break
            if not interrupted:
                for sentence in splitter.flush():
                    self._speak(sentence, spoken)
                    first_audio = first_audio or time.perf_counter() - t0
        except llm.ProviderError as e:
            print(f"  (AI service problem: {e.kind}: {e})", flush=True)
            self.history.pop()
            self._speak(SORRY_SETUP if e.kind == "auth" else SORRY_OFFLINE, [])
            self.speaker.finish()
            self.speaker.wait()
            return False

        self.speaker.finish()
        while self.speaker.busy and not interrupted:
            if self.pressed.wait(0.05):
                interrupted = True
        if interrupted:
            self.speaker.stop()
            self.speaker.wait()
            status("interrupted by the button")
        reply = " ".join(spoken).strip() or "(no reply)"
        turn = getattr(self.provider, "last_turn", None)
        if turn and not interrupted:
            self.history.extend(turn)  # includes any lookups, so later turns know how it knew
        else:
            self.history.append({"role": "assistant", "content": reply})
        del self.history[:-MAX_HISTORY]
        # The history must start with something the person said, not a tool result.
        while self.history and not (self.history[0]["role"] == "user"
                                    and isinstance(self.history[0]["content"], str)):
            self.history.pop(0)
        print(f"  tomo: {reply}", flush=True)
        if first_token is not None:
            print(f"  (first words from AI {first_token:.2f} s, first audio queued {first_audio or 0:.2f} s)",
                  flush=True)
        return interrupted

    def _speak(self, sentence: str, spoken: list[str]) -> None:
        if not sentence or self.pressed.is_set():
            return
        if not self.speaker.busy:
            status("speaking: mouth moving, light off")
        pcm, rate = self._synthesize(sentence)
        self.speaker.play(pcm, rate)
        spoken.append(sentence)

    def _synthesize(self, sentence: str) -> tuple[np.ndarray, int]:
        return self.tts.synthesize(self.pronouncer.apply(sentence))
