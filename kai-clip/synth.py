"""Procedural soundtrack for the KAI promo.

Reads the cue list exported from the page (window.SFX) and renders a 120 BPM
track with drums, bass, pad and arp plus the sound effects, all sample-synced
to the picture. Only depends on numpy.

    python3 synth.py sfx.json soundtrack.wav
"""
import json
import sys
import wave

import numpy as np

SR = 44100
BEAT = 0.5  # 120 BPM
rng = np.random.default_rng(7)


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tt(dur):
    return np.arange(int(dur * SR)) / SR


def lowpass_fft(x, fc, order=2):
    f = np.fft.rfftfreq(len(x), 1 / SR)
    h = 1 / (1 + (f / fc) ** (2 * order)) ** .5
    return np.fft.irfft(np.fft.rfft(x) * h, len(x))


def highpass_fft(x, fc, order=2):
    f = np.fft.rfftfreq(len(x), 1 / SR)
    h = 1 - 1 / (1 + (f / fc) ** (2 * order)) ** .5
    return np.fft.irfft(np.fft.rfft(x) * h, len(x))


def sweep_lowpass(x, fc):
    """One-pole lowpass with a per-sample cutoff array (used for risers/whooshes)."""
    a = 1 - np.exp(-2 * np.pi * np.asarray(fc) / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def saw(freq, t):
    ph = np.cumsum(np.broadcast_to(freq, t.shape)) / SR if np.ndim(freq) else freq * t
    return 2 * (ph % 1) - 1


class Mix:
    def __init__(self, dur):
        self.n = int(dur * SR) + SR
        self.dry = np.zeros((2, self.n))
        self.music = np.zeros((2, self.n))
        self.verb = np.zeros((2, self.n))

    def add(self, sig, t0, gain=1.0, pan=0.0, bus="dry", send=0.0):
        i = int(t0 * SR)
        if i >= self.n:
            return
        sig = sig[: self.n - i]
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        target = self.music if bus == "music" else self.dry
        target[0, i:i + len(sig)] += sig * gain * l * 1.41
        target[1, i:i + len(sig)] += sig * gain * r * 1.41
        if send:
            self.verb[0, i:i + len(sig)] += sig * gain * send * l
            self.verb[1, i:i + len(sig)] += sig * gain * send * r


# ---------------------------------------------------------------- instruments
def kick(gain=1.0):
    t = tt(.45)
    f = 45 + 110 * np.exp(-t * 28)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    click = rng.standard_normal(len(t)) * np.exp(-t * 400) * .3
    return (body + click) * gain


def clap():
    t = tt(.3)
    n = highpass_fft(rng.standard_normal(len(t)), 900)
    env = np.exp(-t * 18) + .6 * np.exp(-np.maximum(t - .012, 0) * 30) * (t > .012)
    return lowpass_fft(n * env, 6000) * .5


def hat(open_=False):
    t = tt(.25 if open_ else .06)
    n = highpass_fft(rng.standard_normal(len(t)), 7000)
    return n * np.exp(-t * (14 if open_ else 60)) * .25


def crash():
    t = tt(2.2)
    n = highpass_fft(rng.standard_normal(len(t)), 3500)
    return n * np.exp(-t * 2.2) * .35


def impact(soft=False):
    t = tt(2.0)
    boom = np.sin(2 * np.pi * np.cumsum(38 + 70 * np.exp(-t * 9)) / SR) * np.exp(-t * (3.2 if not soft else 5))
    noise = lowpass_fft(rng.standard_normal(len(t)), 900) * np.exp(-t * 6) * 1.4
    return (boom * 1.1 + noise) * (.55 if soft else 1.0)


def hit():
    t = tt(.6)
    tone = np.sin(2 * np.pi * np.cumsum(60 + 140 * np.exp(-t * 30)) / SR) * np.exp(-t * 9)
    snap = highpass_fft(rng.standard_normal(len(t)), 1500) * np.exp(-t * 35) * .5
    return tone + snap


def riser(dur):
    t = tt(dur)
    k = t / dur
    n = rng.standard_normal(len(t))
    swept = sweep_lowpass(n, 200 + 9000 * k ** 2)
    tone = saw(110 + 660 * k ** 2, t) * .15
    return (swept * .8 + lowpass_fft(tone, 3000)) * k ** 2


def whoosh(dur, soft=False):
    t = tt(dur + .15)
    k = np.clip(t / dur, 0, 1)
    env = np.sin(np.pi * k) ** 2 * (t <= dur) + (t > dur) * np.exp(-(t - dur) * 25) * 0
    fc = 400 + 5000 * np.sin(np.pi * k)
    return sweep_lowpass(rng.standard_normal(len(t)), fc) * env * (.5 if soft else 1.0) * 1.6


def fall(dur):
    t = tt(dur)
    f = 1400 * np.exp(-t / dur * 2.2)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / dur) * .25 + whoosh(dur)[: len(t)] * .5


def pop(soft=False):
    t = tt(.12)
    f = 500 + 900 * (1 - np.exp(-t * 60))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 40) * (.35 if soft else .6)


def gulp():
    t = tt(.25)
    f = 300 * np.exp(-t * 9) + 70
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14) * .9


def suck(dur):
    t = tt(dur)
    k = t / dur
    n = sweep_lowpass(rng.standard_normal(len(t)), 300 + 6000 * k)
    tone = np.sin(2 * np.pi * np.cumsum(200 + 900 * k ** 1.5) / SR) * .2
    return (n * .7 + tone) * k ** 1.5


def click(v=1.0):
    t = tt(.03)
    n = highpass_fft(rng.standard_normal(len(t)), 2500) * np.exp(-t * 300)
    return (n * .35 + np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 400) * .15) * v


def tick(p=0):
    t = tt(.15)
    f = midi(84 + [0, 3, 7, 12, 15, 19][p % 6])
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 30) * .35


def count(dur):
    out = np.zeros(int((dur + .15) * SR))
    steps = 14
    for i in range(steps):
        s = tick(0)
        tt_ = tt(.08)
        s = np.sin(2 * np.pi * midi(76 + i) * tt_) * np.exp(-tt_ * 50) * .22
        j = int(dur * (i / steps) ** .8 * SR)
        out[j:j + len(s)] += s[: len(out) - j]
    return out


def ding():
    t = tt(1.6)
    f0 = midi(88)
    parts = [(1, 1), (2.01, .5), (3.0, .25), (4.2, .12)]
    return sum(a * np.sin(2 * np.pi * f0 * r * t) * np.exp(-t * (3 + r)) for r, a in parts) * .3


def blip():
    t = tt(.1)
    return np.sin(2 * np.pi * midi(91) * t) * np.exp(-t * 45) * .2


def sparkle():
    out = np.zeros(int(1.4 * SR))
    for i in range(18):
        t = tt(.18)
        s = np.sin(2 * np.pi * midi(rng.choice([88, 91, 93, 95, 98, 100])) * t) * np.exp(-t * 28) * .12
        j = int(rng.uniform(0, 1.1) * SR)
        out[j:j + len(s)] += s
    return out


def pluck(freq, dur=.18):
    t = tt(dur)
    s = saw(freq, t) * .5 + np.sin(2 * np.pi * freq * t)
    return lowpass_fft(s * np.exp(-t * 22), 3500) * .16


def pad_note(freq, dur):
    t = tt(dur)
    s = sum(saw(freq * d, t + rng.uniform(0, 1)) for d in (0.996, 1.0, 1.005))
    env = np.minimum(1, t / .25) * np.minimum(1, (dur - t) / .3)
    return lowpass_fft(s * env, 1600) * .036


def bass_note(freq, dur):
    t = tt(dur)
    s = saw(freq, t) * .6 + np.sin(2 * np.pi * freq * t)
    return lowpass_fft(s * np.exp(-t * 6) * np.minimum(1, t / .005), 420) * .34


# ---------------------------------------------------------------- arrangement
CHORDS = [[57, 60, 64], [53, 57, 60], [55, 60, 64], [55, 59, 62]]  # Am F C G (2 s each)
ROOTS = [45, 41, 48, 43]


def chord_at(t):
    return int(t // 2) % 4


def arrange(mix, dur):
    drums = [(1.0, 4.45, "full"), (5.25, 9.75, "half"), (10.0, 12.42, "full"), (12.75, 14.0, "full")]
    kick_times = []
    for a, b, mode in drums:
        k = int(np.ceil(a / BEAT - 1e-6))
        while k * BEAT < b - 1e-6:
            t = k * BEAT
            if mode == "full" or k % 2 == 0:
                mix.add(kick(), t, .95)
                kick_times.append(t)
            if (mode == "full" and k % 2 == 1) or (mode == "half" and k % 4 == 2):
                mix.add(clap(), t, .8, pan=.05, send=.25)
            for off, g in ((.25, 1.0),) if mode == "full" else ((.125, .5), (.25, .8), (.375, .5)):
                if t + off < b:
                    mix.add(hat(), t + off, .8 * g, pan=.3)
            if mode == "full":
                mix.add(hat(), t, .35, pan=-.3)
            k += 1
        # bass in eighths
        k = int(np.ceil(a / (BEAT / 2) - 1e-6))
        while k * BEAT / 2 < b - 1e-6:
            t = k * BEAT / 2
            root = ROOTS[chord_at(t)]
            mix.add(bass_note(midi(root + (12 if k % 4 == 3 else 0)), .24), t, .9 if mode == "full" else .65, bus="music")
            k += 1

    # arp in sixteenths during chat + modes
    for a, b, g in ((5.25, 9.75, .8), (10.0, 12.42, 1.0)):
        k = int(np.ceil(a / (BEAT / 4)))
        while k * BEAT / 4 < b:
            t = k * BEAT / 4
            notes = CHORDS[chord_at(t)]
            n = notes[[0, 1, 2, 1][k % 4]] + 12 + (12 if k % 8 >= 4 else 0)
            mix.add(pluck(midi(n)), t, g, pan=.35 * np.sin(k), bus="music", send=.35)
            k += 1

    # pad: whole piece, chord per 2 s bar; swell in the intro, held C major at the end
    for bar in range(int(np.ceil(13.5 / 2))):
        t0, t1 = bar * 2, min(bar * 2 + 2.05, 13.55)
        g = .6 if bar == 0 else 1.0
        for i, n in enumerate(CHORDS[bar % 4]):
            mix.add(pad_note(midi(n), t1 - t0), t0, g, pan=(i - 1) * .5, bus="music", send=.4)
    for i, n in enumerate([48, 55, 60, 64, 67]):
        mix.add(pad_note(midi(n), dur - 13.5 + .3), 13.5, 1.3, pan=(i - 2) * .3, bus="music", send=.6)
    for i, n in enumerate([36, 48]):
        mix.add(bass_note(midi(n), 1.4), 13.5, .8, bus="music")
    return kick_times


def sfx(mix, cues):
    for c in cues:
        t, ty = c["t"], c["type"]
        if ty == "riser":
            mix.add(riser(c["dur"]), t, .55, send=.3)
        elif ty == "impact":
            mix.add(impact(c.get("soft", False)), t, .9 if not c.get("soft") else .7, send=.3)
            mix.add(crash(), t, .5 if not c.get("soft") else .25, send=.3)
        elif ty == "hit":
            mix.add(hit(), t, .75, send=.2)
            if c.get("crash"):
                mix.add(crash(), t, .45, send=.3)
        elif ty == "whoosh":
            mix.add(whoosh(c["dur"], c.get("soft", False)), t, .35, pan=-.2, send=.2)
        elif ty == "fall":
            mix.add(fall(c["dur"]), t, .6, send=.2)
        elif ty == "pop":
            mix.add(pop(c.get("soft", False)), t, 1.0, pan=.15, send=.3)
        elif ty == "gulp":
            mix.add(gulp(), t, .9)
        elif ty == "suck":
            mix.add(suck(c["dur"]), t, .45, send=.2)
        elif ty == "click":
            mix.add(click(c.get("v", 1)), t, .9, pan=.25)
        elif ty == "tick":
            mix.add(tick(c.get("p", 0)), t, .9, pan=.2, send=.4)
        elif ty == "count":
            mix.add(count(c["dur"]), t, 1.0, pan=.2, send=.3)
        elif ty == "ding":
            mix.add(ding(), t, 1.0, send=.6)
        elif ty == "blip":
            mix.add(blip(), t, 1.0, pan=-.2, send=.5)
        elif ty == "sparkle":
            mix.add(sparkle(), t, 1.0, pan=.1, send=.7)


def reverb(x):
    t = tt(1.8)
    out = np.zeros_like(x)
    for ch in range(2):
        ir = lowpass_fft(rng.standard_normal(len(t)), 5000) * np.exp(-t * 3.2)
        ir[: int(.012 * SR)] = 0
        n = len(x[ch]) + len(ir)
        y = np.fft.irfft(np.fft.rfft(x[ch], n) * np.fft.rfft(ir, n), n)[: len(x[ch])]
        out[ch] = y
    return out * .08


def main():
    data = json.load(open(sys.argv[1]))
    dur = data["duration"]
    mix = Mix(dur)
    kicks = arrange(mix, dur)
    sfx(mix, data["cues"])

    # sidechain duck on the music bus
    duck = np.ones(mix.n)
    tax = np.arange(mix.n) / SR
    for k in kicks:
        i = int(k * SR)
        seg = tax[i:i + int(.3 * SR)] - k
        duck[i:i + len(seg)] = np.minimum(duck[i:i + len(seg)], 1 - .55 * np.exp(-seg * 12))
    out = mix.dry + mix.music * duck + reverb(mix.verb)

    out = out[:, : int(dur * SR)]
    out = np.tanh(out * .8)
    out *= .9 / np.max(np.abs(out))
    fade = int(.35 * SR)
    out[:, -fade:] *= np.linspace(1, 0, fade)
    pcm = (out.T * 32767).astype("<i2")
    with wave.open(sys.argv[2], "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", sys.argv[2])


if __name__ == "__main__":
    main()
