"""Generates the widget's two alert sounds as small WAV files.

Synthesized here (bell-like sine tones with a soft decay), so there are no
third-party sound files to license.

usage: python make_sounds.py OUTPUT_FOLDER
  -> needs_you.wav  (rising two notes: attention)
  -> finished.wav   (soft three-note rising chime: done)
"""
import math
import os
import struct
import sys
import wave

RATE = 44100
VOLUME = 0.45


def bell(freq: float, start: float, length: float, total: float) -> list:
    """One note: a sine with a touch of its octave, quick attack, smooth decay."""
    out = [0.0] * int(total * RATE)
    first = int(start * RATE)
    for i in range(int(length * RATE)):
        n = first + i
        if n >= len(out):
            break
        t = i / RATE
        attack = min(1.0, t / 0.006)
        decay = math.exp(-t * 5.5)
        tone = math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(2 * math.pi * 2 * freq * t)
        out[n] += VOLUME * attack * decay * tone / 1.25
    return out


def mix(*tracks: list) -> list:
    n = max(len(t) for t in tracks)
    out = [0.0] * n
    for t in tracks:
        for i, v in enumerate(t):
            out[i] += v
    peak = max(1e-9, max(abs(v) for v in out))
    scale = min(1.0, 0.9 / peak)
    fade = int(0.02 * RATE)  # soft end, no click
    return [v * scale * (min(1.0, (n - i) / fade)) for i, v in enumerate(out)]


def save(path: str, samples: list) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(v * 32767)) for v in samples))


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    # Needs you: E5 then A5, a rising "ding-DING".
    total = 0.75
    save(os.path.join(out, "needs_you.wav"),
         mix(bell(659.25, 0.00, 0.6, total), bell(880.00, 0.16, 0.6, total)))
    # Finished: C5, E5, G5 rolled upward, the last one ringing.
    total = 1.1
    save(os.path.join(out, "finished.wav"),
         mix(bell(523.25, 0.00, 0.9, total), bell(659.25, 0.09, 0.9, total),
             bell(783.99, 0.18, 0.9, total)))
    print("wrote needs_you.wav and finished.wav to", out)


if __name__ == "__main__":
    main()
