"""Command-line entry point: `tomoshibi <command>`."""

import argparse
import time
from pathlib import Path

from tomoshibi import __version__, models, paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tomoshibi", description="Tomoshibi voice companion")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--lock", type=Path, help="path to models.lock")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check the device setup")

    models_cmd = sub.add_parser("models", help="manage downloaded models")
    models_sub = models_cmd.add_subparsers(dest="models_command", required=True)
    models_sub.add_parser("fetch", help="download any models in models.lock that are missing")
    models_sub.add_parser("list", help="show models and whether they are downloaded")

    say = sub.add_parser("say", help="speak text with the local TTS voice into a WAV file")
    say.add_argument("text")
    say.add_argument("--out", type=Path, default=Path("say.wav"))
    say.add_argument("--speed", type=float, default=1.0, help="length scale; >1.0 is slower")

    transcribe = sub.add_parser("transcribe", help="transcribe a WAV file with local STT")
    transcribe.add_argument("wav", type=Path)
    transcribe.add_argument("--model", help="STT model name from models.lock")

    bench = sub.add_parser("bench", help="benchmarks")
    bench_sub = bench.add_subparsers(dest="bench_command", required=True)
    bench_speech = bench_sub.add_parser("speech", help="TTS -> STT round trip with timings")
    bench_speech.add_argument("--stt", action="append", help="STT model name (repeatable)")

    args = parser.parse_args(argv)
    lock_path = args.lock or paths.default_models_lock()

    if args.command == "doctor":
        from tomoshibi import doctor

        return doctor.run(lock_path)

    specs = models.load_lock(lock_path)

    if args.command == "models":
        if args.models_command == "list":
            for spec in specs:
                state = "present" if spec.is_present() else "missing"
                print(f"{spec.name:32} {spec.kind:4} {state:8} {spec.repo}@{spec.revision[:10]}")
            return 0
        for spec in specs:
            if spec.is_present():
                print(f"{spec.name}: already present")
                continue
            print(f"{spec.name}: downloading {spec.repo}@{spec.revision[:10]} ...")
            models.fetch(spec)
            print(f"{spec.name}: done")
        return 0

    if args.command == "say":
        from tomoshibi.tts import PiperTTS

        spec = models.first_of_kind(specs, "tts")
        t0 = time.perf_counter()
        PiperTTS(models.piper_model_path(spec), length_scale=args.speed).synthesize_to_wav(
            args.text, args.out
        )
        print(f"Wrote {args.out} in {time.perf_counter() - t0:.2f} s")
        return 0

    if args.command == "transcribe":
        from tomoshibi import stt

        spec = models.find(specs, args.model) if args.model else models.first_of_kind(specs, "stt")
        t0 = time.perf_counter()
        text = stt.load(spec).transcribe(args.wav)
        print(text)
        print(f"({spec.name}, {time.perf_counter() - t0:.2f} s including model load)")
        return 0

    if args.command == "bench":
        from tomoshibi import bench as bench_mod

        bench_mod.run(specs, stt_names=args.stt)
        return 0

    parser.error(f"unknown command {args.command}")
    return 2
