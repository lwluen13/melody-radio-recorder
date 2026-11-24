#!/usr/bin/env python3
"""
Record Melody FM from 10:00 to 11:00 Singapore time, turn it into text, and send the
transcript to Google Drive. Made to run on GitHub Actions.

Transcript lines look like "[hh:mm:ss] text". The time is the offset from 10:00
Singapore time, so 00:34:50 means about 10:34:50.

Normal run:   python cloud_record.py
Test run:     python cloud_record.py --test-minutes 2
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")
BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def log(*a):
    print(*a, flush=True)


def fmt(sec):
    sec = max(0, int(sec))
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"


def http_get(url, timeout=25, tries=3):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2)
    raise last


# --------------------------------------------------------------- HLS parsing
def parse_playlist(text, base_url):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines or not lines[0].startswith("#EXTM3U"):
        raise ValueError("The link did not return an HLS playlist.")
    variants = []
    for i, l in enumerate(lines):
        if l.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
            m = re.search(r"BANDWIDTH=(\d+)", l)
            variants.append((int(m.group(1)) if m else 0,
                             urllib.parse.urljoin(base_url, lines[i + 1])))
    if variants:
        return {"variants": variants}

    seq, target, dur, pdt, last_end = 0, 6.0, None, None, None
    segs = []
    for l in lines:
        if l.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            seq = int(l.split(":", 1)[1])
        elif l.startswith("#EXT-X-TARGETDURATION:"):
            target = float(l.split(":", 1)[1])
        elif l.startswith("#EXTINF:"):
            dur = float(l.split(":", 1)[1].split(",")[0])
        elif l.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            try:
                pdt = dt.datetime.fromisoformat(l.split(":", 1)[1].strip().replace("Z", "+00:00"))
            except ValueError:
                pdt = None
        elif l.startswith("#"):
            continue
        else:
            d = dur if dur is not None else target
            seg_pdt = pdt if pdt is not None else last_end
            segs.append({"seq": seq + len(segs), "url": urllib.parse.urljoin(base_url, l),
                         "dur": d, "pdt": seg_pdt})
            last_end = seg_pdt + dt.timedelta(seconds=d) if seg_pdt else None
            pdt, dur = None, None
    return {"segments": segs, "target": target}


# ----------------------------------------------------------------- recording
def record_hls(win_start, win_end, raw_path):
    """Download segments until the window ends. Skips repeated segments."""
    hard_end = win_end + dt.timedelta(seconds=120)
    media_url = CFG["stream_url"]
    seen_seq, seen_hash = set(), set()
    manifest, kept = [], []
    pdt_known = False
    last_pdt_end = None
    total = 0.0
    first_wall = None
    fails = 0

    with open(raw_path, "wb") as f:
        while True:
            now = dt.datetime.now(SGT)
            if now >= hard_end:
                break
            if pdt_known:
                if last_pdt_end is not None and last_pdt_end >= win_end:
                    break
            elif now >= win_end:
                break
            try:
                pl = parse_playlist(http_get(media_url).decode("utf-8", "ignore"), media_url)
                fails = 0
            except Exception as e:  # noqa: BLE001
                fails += 1
                log(f"Playlist problem ({type(e).__name__}), try {fails}")
                if fails >= 10 and not kept:
                    raise
                time.sleep(3)
                continue
            if "variants" in pl:
                media_url = min(pl["variants"])[1]  # lowest bandwidth is enough for speech
                continue

            for s in pl["segments"]:
                entry = {"seq": s["seq"], "dur": s["dur"],
                         "pdt": s["pdt"].astimezone(SGT).isoformat() if s["pdt"] else None}
                if s["seq"] in seen_seq:
                    continue
                seen_seq.add(s["seq"])
                if s["pdt"]:
                    pdt_known = True
                    seg_end = s["pdt"] + dt.timedelta(seconds=s["dur"])
                    if seg_end <= win_start:
                        entry["action"] = "before_window"
                        manifest.append(entry)
                        continue
                    if s["pdt"] >= win_end:
                        last_pdt_end = seg_end
                        entry["action"] = "after_window"
                        manifest.append(entry)
                        continue
                try:
                    data = http_get(s["url"])
                except Exception as e:  # noqa: BLE001
                    entry["action"] = f"download_failed_{type(e).__name__}"
                    manifest.append(entry)
                    continue
                h = hashlib.sha1(data).hexdigest()
                entry["bytes"], entry["sha1"] = len(data), h[:10]
                if h in seen_hash:
                    entry["action"] = "duplicate_content"
                    manifest.append(entry)
                    continue
                seen_hash.add(h)
                f.write(data)
                if first_wall is None:
                    first_wall = dt.datetime.now(SGT)
                entry["action"] = "kept"
                manifest.append(entry)
                kept.append(s)
                total += s["dur"]
                if s["pdt"]:
                    last_pdt_end = s["pdt"] + dt.timedelta(seconds=s["dur"])
            time.sleep(max(1.0, pl.get("target", 6.0) / 2))

    audio_start = None
    if kept:
        audio_start = kept[0]["pdt"].astimezone(SGT) if kept[0]["pdt"] else first_wall
    actions = {}
    for m in manifest:
        actions[m["action"]] = actions.get(m["action"], 0) + 1
    summary = {"pdt_in_playlist": pdt_known, "kept_segments": len(kept),
               "kept_audio_seconds": round(total, 1), "actions": actions,
               "audio_start": audio_start.isoformat() if audio_start else None,
               "window_start": win_start.isoformat(), "window_end": win_end.isoformat()}
    (WORK / "manifest.json").write_text(
        json.dumps({"summary": summary, "segments": manifest}, indent=1), encoding="utf-8")
    log("Recording summary:", json.dumps(summary))
    return audio_start, total


def to_mp3(raw, out):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("ffmpeg not found on this machine.")
    r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-vn", "-ac", "1",
                        "-c:a", "libmp3lame", "-b:a", "64k", str(out)])
    if r.returncode != 0 or not out.exists() or out.stat().st_size < 1000:
        sys.exit("Could not convert the recording to mp3.")


# --------------------------------------------------------------- transcribing
def load_audio(path):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-vn",
                        "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], stdout=subprocess.PIPE)
    if r.returncode != 0 or not r.stdout:
        sys.exit("Could not read the audio file.")
    return np.frombuffer(r.stdout, dtype=np.float32)


def transcribe(mp3, base_offset):
    from faster_whisper import WhisperModel
    log(f"Loading model '{CFG['whisper_model']}'...")
    model = WhisperModel(CFG["whisper_model"], device="cpu", compute_type="int8",
                         cpu_threads=os.cpu_count() or 2)
    audio = load_audio(mp3)
    log(f"Audio length: {len(audio) / 16000 / 60:.1f} minutes. Transcribing...")
    kwargs = dict(language=CFG.get("language"), vad_filter=True, beam_size=5,
                  condition_on_previous_text=False)
    if CFG.get("initial_prompt"):
        kwargs["initial_prompt"] = CFG["initial_prompt"]
    if CFG.get("language") is None:
        kwargs["multilingual"] = True
    try:
        segments, _ = model.transcribe(audio, **kwargs)
    except TypeError:
        kwargs.pop("multilingual", None)
        segments, _ = model.transcribe(audio, **kwargs)
    lines, n = [], 0
    for s in segments:
        text = s.text.strip()
        if text:
            lines.append(f"[{fmt(base_offset + s.start)}] {text}")
        n += 1
        if n % 40 == 0:
            log(f"  ...{int(s.end // 60)} min done")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ uploading
def upload(name, content):
    url = os.environ.get("APPS_SCRIPT_URL", "").strip()
    secret = os.environ.get("APPS_SCRIPT_SECRET", "").strip()
    if not url or not secret:
        log("Upload secrets are not set, so nothing was uploaded.")
        return False
    import requests
    for _ in range(3):
        try:
            r = requests.post(url, data=json.dumps({"secret": secret, "name": name,
                                                    "content": content}).encode("utf-8"),
                              headers={"Content-Type": "text/plain;charset=utf-8"}, timeout=90)
            j = r.json()
            if j.get("ok"):
                log(f"Uploaded {name} to Google Drive.")
                return True
            log("Upload was refused:", j.get("error"))
        except Exception as e:  # noqa: BLE001
            log(f"Upload problem: {type(e).__name__}")
        time.sleep(5)
    return False


# ----------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-minutes", type=float, default=0)
    ap.add_argument("--skip-transcribe", action="store_true")
    args = ap.parse_args()

    now = dt.datetime.now(SGT)
    ten = dt.datetime.combine(now.date(), dt.time(10, 0), SGT)
    if args.test_minutes > 0:
        win_start = now
        win_end = now + dt.timedelta(minutes=args.test_minutes)
        name = f"test-cloud-{now.date()}.txt"
    else:
        win_start, win_end = ten, ten + dt.timedelta(hours=1)
        name = f"{now.date()}.txt"
        if now >= win_end:
            sys.exit("It is already past 11:00 Singapore time. Nothing to record.")
        wait = (win_start - now).total_seconds()
        if wait > 10800:
            sys.exit("Started more than three hours before 10:00. Stopping.")
        if wait > 0:
            log(f"Waiting {int(wait)} seconds until 10:00 Singapore time...")
            time.sleep(wait)
        else:
            log(f"Started {int(-wait)} seconds after 10:00. Recording from now.")

    raw = WORK / "stream.raw"
    mp3 = WORK / "recording.mp3"
    audio_start, total = record_hls(win_start, win_end, raw)
    if audio_start is None or total < 5:
        sys.exit("No audio was recorded. The stream may be blocked or down.")
    expected = (win_end - win_start).total_seconds()
    if args.test_minutes <= 0 and total < expected * 0.8:
        log(f"WARNING: only {total / 60:.1f} of {expected / 60:.1f} minutes were recorded.")

    to_mp3(raw, mp3)
    raw.unlink(missing_ok=True)
    base_offset = 0.0 if args.test_minutes > 0 else (audio_start - ten).total_seconds()
    log(f"Audio starts {base_offset:.0f} seconds after 10:00.")

    if args.skip_transcribe:
        log("Skipping transcription (test).")
        return
    text = transcribe(mp3, base_offset)
    (WORK / name).write_text(text, encoding="utf-8")
    log(f"Transcript has {text.count(chr(10))} lines.")
    if not upload(name, text):
        sys.exit("The transcript could not be uploaded to Google Drive.")


if __name__ == "__main__":
    main()
