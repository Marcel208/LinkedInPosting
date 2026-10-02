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


def groove(mix, a, b, mode, chord, kick_times, gain=1.0):
    """Drums + eighth-note bass between a and b. mode: full | half | build."""
    k = int(np.ceil(a / BEAT - 1e-6))
    while k * BEAT < b - 1e-6:
        t = k * BEAT
        if mode in ("full", "build") or k % 2 == 0:
            mix.add(kick(), t, .95 * gain)
            kick_times.append(t)
        if (mode == "full" and k % 2 == 1) or (mode == "half" and k % 4 == 2):
            mix.add(clap(), t, .8 * gain, pan=.05, send=.25)
        for off, g in ((.25, 1.0),) if mode != "half" else ((.125, .5), (.25, .8), (.375, .5)):
            if t + off < b:
                mix.add(hat(), t + off, .8 * g * gain, pan=.3)
        if mode == "full":
            mix.add(hat(), t, .35 * gain, pan=-.3)
        k += 1
    if mode == "build":   # snare roll that doubles in speed towards b
        t, step = a, BEAT / 2
        while t < b - 1e-6:
            mix.add(clap(), t, (.3 + .6 * (t - a) / (b - a)) * gain, pan=.05, send=.2)
            t += step
            if t > a + (b - a) / 2:
                step = BEAT / 4
            if t > a + (b - a) * .8:
                step = BEAT / 8
    k = int(np.ceil(a / (BEAT / 2) - 1e-6))
    while k * BEAT / 2 < b - 1e-6:
        t = k * BEAT / 2
        root = ROOTS[chord(t)]
        mix.add(bass_note(midi(root + (12 if k % 4 == 3 else 0)), .24), t, (.9 if mode != "half" else .65) * gain, bus="music")
        k += 1


def arrange(mix, dur):
    kick_times = []
    for a, b, mode in [(1.0, 4.45, "full"), (5.25, 9.75, "half"), (10.0, 12.42, "full"), (12.75, 14.0, "full")]:
        groove(mix, a, b, mode, chord_at, kick_times)
    kicks = kick_times

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
    return kicks



# ---------------------------------------------------------------- galaxy style
def braam(dur, up=False):
    t = tt(dur)
    k = t / dur
    f0 = midi(33)
    s = sum(saw(f0 * m * d, t + rng.uniform(0, 1)) for m in (1, 1.5, 2) for d in (.995, 1.004)) / 4
    if up:
        s = s + saw(midi(45) * (1 + .06 * k), t) * .4
    s = sweep_lowpass(s, 120 + 1600 * np.exp(-k * 3) * np.minimum(1, t / .12))
    env = np.minimum(1, t / .08) * np.exp(-k * 1.6) * np.minimum(1, (dur - t) / .2)
    return np.tanh(s * env * 3) * .55


def timpani():
    t = tt(.9)
    f = 95 + 40 * np.exp(-t * 30)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5) + lowpass_fft(rng.standard_normal(len(t)), 600) * np.exp(-t * 25) * .4) * .7


def choir_note(freq, dur):
    t = tt(dur)
    vib = 1 + .006 * np.sin(2 * np.pi * 5.2 * t)
    s = sum(saw(freq * d * vib, t + rng.uniform(0, 1)) for d in (.993, 1.0, 1.008))
    spec = np.fft.rfft(s)
    f = np.fft.rfftfreq(len(s), 1 / SR)
    form = sum(a * np.exp(-((f - fc) / bw) ** 2) for fc, bw, a in ((730, 90, 1), (1090, 110, .5), (2440, 160, .25)))
    s = np.fft.irfft(spec * form, len(s))
    env = np.minimum(1, t / .5) * np.minimum(1, (dur - t) / .6)
    return s * env * .09


def laser():
    t = tt(.28)
    f = 3200 * np.exp(-t * 14) + 180
    ph = np.cumsum(f) / SR
    s = np.sign(np.sin(2 * np.pi * ph)) * .4 + np.sin(2 * np.pi * ph * 1.5)
    return lowpass_fft(s * np.exp(-t * 7), 7000) * .3


def explode():
    t = tt(1.6)
    n = sweep_lowpass(rng.standard_normal(len(t)), 5000 * np.exp(-t * 3) + 150)
    boom = np.sin(2 * np.pi * np.cumsum(30 + 90 * np.exp(-t * 7)) / SR) * np.exp(-t * 3.5)
    return np.tanh((n * np.exp(-t * 2.5) * 1.6 + boom * 1.2) * 1.5) * .8


def coin(p=0):
    out = np.zeros(int(.4 * SR))
    for j, (m, d) in enumerate(((83 + p * 2, .07), (88 + p * 2, .3))):
        t = tt(d)
        s = np.sign(np.sin(2 * np.pi * midi(m) * t)) * np.exp(-t * (6 if j else 30)) * .12
        i = int(j * .07 * SR)
        out[i:i + len(s)] += s
    return out


def airhorn():
    out = np.zeros(int(1.4 * SR))
    for start, d in ((0, .13), (.17, .13), (.34, .9)):
        t = tt(d)
        f = np.array([466.16, 587.33, 698.46])[:, None] * (1 + .03 * np.minimum(1, t / .05))
        s = sum(np.sign(np.sin(2 * np.pi * fi * t)) for fi in f) / 3
        s = lowpass_fft(np.tanh(s * 2), 3800) * np.minimum(1, t / .01) * np.minimum(1, (d - t) / .03)
        i = int(start * SR)
        out[i:i + len(s)] += s * .45
    return out


def firework(p=0):
    out = np.zeros(int(1.9 * SR))
    t = tt(.35)
    whistle = np.sin(2 * np.pi * np.cumsum(900 + 2200 * t / .35) / SR) * (t / .35) * .08
    out[:len(t)] += whistle
    b = impact(soft=True)[: int(1.2 * SR)] * .5
    out[int(.35 * SR):int(.35 * SR) + len(b)] += b
    for _ in range(40):
        c = click(rng.uniform(.4, 1))
        i = int((.45 + rng.uniform(0, 1.2)) * SR)
        out[i:i + len(c)] += c * .7
    return out


GCHORDS = [[57, 60, 64], [53, 57, 60], [55, 60, 64], [55, 59, 62]]


def arrange_galaxy(mix, dur):
    kicks = []
    # drone under the trailer
    t = tt(4.4)
    drone = lowpass_fft(saw(midi(33), t) + saw(midi(33) * 1.005, t + .3), 160) * np.minimum(1, t / 1.5) * np.minimum(1, (4.4 - t) / .2)
    mix.add(drone, 0, .35, bus="music")
    # choir for the arrival: Am F C G
    for (a, b, ch) in ((4.3, 5.3, 0), (5.3, 6.3, 1), (6.3, 7.0, 2), (7.0, 8.05, 3)):
        for i, n in enumerate(GCHORDS[ch] + [GCHORDS[ch][0] + 12]):
            mix.add(choir_note(midi(n), b - a + .3), a, 1.0, pan=(i - 1.5) * .35, bus="music", send=.8)
        for i, n in enumerate(GCHORDS[ch]):
            mix.add(pad_note(midi(n), b - a + .1), a, 1.4, pan=(i - 1) * .5, bus="music", send=.5)
        mix.add(braam(b - a + .2), a, .35, send=.3)
    # drop + build + finale grooves (chords per 2 s bar from 8.0)
    gchord = lambda t: int((t - 8.0) // 2) % 4 if t < 13 else int((t - 13.0) // 1) % 4
    groove(mix, 8.0, 11.0, "full", gchord, kicks, 1.05)
    groove(mix, 11.0, 13.0, "build", gchord, kicks, .9)
    groove(mix, 13.0, 16.5, "full", gchord, kicks, 1.0)
    for a, b, g in ((8.0, 11.0, 1.0), (11.0, 13.0, .7), (13.0, 16.5, 1.0)):
        k = int(np.ceil(a / (BEAT / 4)))
        while k * BEAT / 4 < b:
            t0 = k * BEAT / 4
            notes = GCHORDS[gchord(t0)]
            n = notes[[0, 1, 2, 1][k % 4]] + 12 + (12 if k % 8 >= 4 else 0)
            mix.add(pluck(midi(n)), t0, g, pan=.35 * np.sin(k), bus="music", send=.35)
            k += 1
    for a in np.arange(8.0, 16.5, 1.0 if True else 2):
        ch = GCHORDS[gchord(a + .01)]
        for i, n in enumerate(ch):
            mix.add(pad_note(midi(n), 1.05), a, 1.2, pan=(i - 1) * .5, bus="music", send=.4)
    # final chord ring-out
    for i, n in enumerate([45, 52, 57, 60, 64, 69]):
        mix.add(pad_note(midi(n), dur - 16.5), 16.5, 1.6, pan=(i - 2.5) * .3, bus="music", send=.7)
        mix.add(choir_note(midi(n + 12), dur - 16.5), 16.5, .9, pan=(i - 2.5) * .3, bus="music", send=.8)
    mix.add(bass_note(midi(33), 1.5), 16.5, 1.0, bus="music")
    mix.add(crash(), 16.5, .5, send=.4)
    return kicks


def sfx(mix, cues):
    for c in cues:
        t, ty = c["t"], c["type"]
        if ty == "riser":
            mix.add(riser(c["dur"]), t, .55, send=.3)
        elif ty == "impact":
            mix.add(impact(c.get("soft", False)), t, .9 if not c.get("soft") else .7, send=.3)
            mix.add(crash(), t, .5 if not c.get("soft") else .25, send=.3)
        elif ty == "hit":
            mix.add(hit(), t, .9 if c.get("big") else .75, send=.2)
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
        elif ty == "braam":
            mix.add(braam(c["dur"], c.get("up", False)), t, .9, send=.4)
        elif ty == "roll":
            n = 14
            for j in range(n):
                tj = t + c["dur"] * (j / n) ** .7
                mix.add(timpani(), tj, .35 + .6 * j / n, send=.3)
        elif ty == "choir":
            pass  # handled by the arrangement
        elif ty == "laser":
            mix.add(laser(), t, .9, pan=.3, send=.2)
        elif ty == "explode":
            mix.add(explode(), t, .85, pan=.35, send=.3)
        elif ty == "coin":
            mix.add(coin(c.get("p", 0)), t, 1.0, pan=.3, send=.3)
        elif ty == "airhorn":
            mix.add(airhorn(), t, .8, send=.3)
        elif ty == "glasses":
            mix.add(hit(), t, .6)
            mix.add(sparkle(), t + .05, .7, send=.6)
        elif ty == "firework":
            mix.add(firework(c.get("p", 0)), t, .8, pan=(-.5 if c.get("p", 0) % 2 == 0 else .5), send=.4)
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
    kicks = arrange_galaxy(mix, dur) if data.get("style") == "galaxy" else arrange(mix, dur)
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
