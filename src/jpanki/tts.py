"""Text-to-speech primitives, built on Microsoft Edge's neural voices.

Ported from minihongo's ``generate_audio.py``, which was much the more developed
of the two implementations — it had grown retry-with-backoff, a content-hash
cache, sample-rate normalisation, speech-aware volume levelling and multi-part
merging for dialogues. nihongo-it-anki's was a thin loop over tiers.

What is *not* here is either project's orchestration: minihongo has ten
content-type-specific generators (words, grammar, dialogues, haiku, stories…)
and nihongo-it-anki walks tier CSVs. Those know the schema, so they stay with
their project. This module knows how to turn a string into a well-formed MP3.

Requires the ``audio`` extra (``edge-tts``). ``ffmpeg`` is strongly recommended
but optional: Edge TTS returns usable MP3s at inconsistent sample rates and
loudness, and ffmpeg is what levels them. Without it, synthesis still works and
:func:`have_ffmpeg` reports false, so callers can warn rather than fail —
uneven audio is worse than even audio, but far better than no deck. Merging
clips genuinely needs it and raises without.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: The two voices both projects settled on.
VOICE_MALE = "ja-JP-KeitaNeural"
VOICE_FEMALE = "ja-JP-NanamiNeural"

#: Edge TTS output varies in loudness between requests, enough to be jarring in
#: a review session. Level to a fixed mean, measured over speech only.
TARGET_MEAN_DB = -20.0

#: Silence inserted between merged segments, e.g. between dialogue turns.
SILENCE_MS = 600

#: Edge TTS rate-limits; this delay between requests keeps it happy.
REQUEST_DELAY = 0.3

_ENCODE_ARGS = ["-ar", "48000", "-c:a", "libmp3lame", "-b:a", "128k"]


class TtsError(RuntimeError):
    """Synthesis failed after every retry."""


def have_ffmpeg() -> bool:
    """Whether ffmpeg is available for post-processing.

    Callers should check this and warn: without ffmpeg, clips keep Edge TTS's
    variable sample rate and loudness, which is audible across a review session
    but perfectly reviewable.
    """
    return shutil.which("ffmpeg") is not None


def _ffmpeg(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["ffmpeg", *args], capture_output=True, text=True, check=check)
    except FileNotFoundError:
        raise TtsError(
            "ffmpeg not found on PATH. It is required to normalise Edge TTS "
            "output to a consistent sample rate and loudness, and to merge "
            "clips. Install it, or pass postprocess=False to skip levelling."
        ) from None


def _speech_volume(path: Path) -> float | None:
    """Mean volume in dB, measured with leading and trailing silence trimmed.

    Measuring the whole file would let a long pause drag the mean down and make
    the levelling over-correct, so silence is stripped from both ends first —
    reversing the stream to reuse ``silenceremove``, which only trims the start.
    """
    trim = (
        "silenceremove=start_periods=1:start_silence=0.02:start_threshold=-60dB,"
        "areverse,"
        "silenceremove=start_periods=1:start_silence=0.02:start_threshold=-60dB,"
        "areverse,"
        "volumedetect"
    )
    result = _ffmpeg("-i", str(path), "-af", trim, "-f", "null", "-", check=False)
    match = re.search(r"mean_volume:\s*([-\d.]+)", result.stderr)
    return float(match.group(1)) if match else None


def normalize(path: Path, *, target_db: float = TARGET_MEAN_DB, passes: int = 2) -> None:
    """Level a clip's loudness towards ``target_db``.

    Two passes, because a single gain adjustment shifts which parts of the clip
    register as speech and the measurement moves with it. Stops early once
    within 1 dB, which is below the threshold of noticing.
    """
    for _ in range(passes):
        current = _speech_volume(path)
        if current is None:
            return
        adjust = target_db - current
        if abs(adjust) < 1:
            return
        tmp = path.with_suffix(path.suffix + ".tmp.mp3")
        _ffmpeg("-y", "-i", str(path), "-af", f"volume={adjust}dB", *_ENCODE_ARGS, str(tmp))
        os.replace(tmp, path)


@dataclass
class Job:
    """One clip to synthesise."""

    text: str
    output: Path
    voice: str = VOICE_MALE


class Synthesizer:
    """Synthesises clips, reusing identical ones.

    The cache matters more than it looks: vocabulary decks repeat short strings
    constantly across example sentences and headwords, and every duplicate is a
    network round-trip that also counts against the rate limit.
    """

    def __init__(
        self,
        *,
        delay: float = REQUEST_DELAY,
        retries: int = 3,
        postprocess: bool | None = None,
    ):
        self.delay = delay
        self.retries = retries
        #: Re-encode and level each clip. Defaults to whether ffmpeg is present,
        #: so a missing ffmpeg degrades quality rather than breaking the build.
        self.postprocess = have_ffmpeg() if postprocess is None else postprocess
        self._cache: dict[str, Path] = {}

    @staticmethod
    def _key(text: str, voice: str) -> str:
        return hashlib.sha256(f"{text}|{voice}".encode()).hexdigest()[:12]

    async def synthesize(self, text: str, voice: str, output: Path) -> Path:
        """Synthesise one clip, retrying with exponential backoff."""
        import edge_tts  # imported lazily so the library works without the extra

        if not text.strip():
            raise ValueError(f"refusing to synthesise empty text to {output}")

        key = self._key(text, voice)
        cached = self._cache.get(key)
        if cached is not None and cached.exists() and cached != output:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cached, output)
            return output

        output.parent.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                await edge_tts.Communicate(text, voice).save(str(output))
                if self.postprocess:
                    # Re-encode: Edge TTS's sample rate varies between requests.
                    tmp = output.with_suffix(output.suffix + ".raw.mp3")
                    _ffmpeg("-y", "-i", str(output), *_ENCODE_ARGS, str(tmp))
                    os.replace(tmp, output)
                    normalize(output)
                self._cache[key] = output
                await asyncio.sleep(self.delay)
                return output
            except Exception as error:  # noqa: BLE001 - retried, then re-raised
                last_error = error
                if attempt < self.retries - 1:
                    await asyncio.sleep(2 ** (attempt + 1))
        raise TtsError(f"failed to synthesise {output.name} after {self.retries} attempts: {last_error}")

    async def run(self, jobs: list[Job], *, force: bool = False, on_progress=None) -> list[Path]:
        """Synthesise many clips sequentially, skipping ones already present.

        Sequential on purpose: Edge TTS rate-limits aggressively enough that
        concurrency costs more in backoff than it saves in wall-clock.

        ``force=True`` regenerates existing files — needed after changing the
        text, since a stale clip is not detectable from its filename alone.
        """
        written: list[Path] = []
        for index, job in enumerate(jobs, start=1):
            if job.output.exists() and not force:
                if on_progress:
                    on_progress(index, len(jobs), job, True)
                continue
            await self.synthesize(job.text, job.voice, job.output)
            written.append(job.output)
            if on_progress:
                on_progress(index, len(jobs), job, False)
        return written


def merge(parts: list[Path], output: Path, *, silence_ms: int = SILENCE_MS) -> Path:
    """Concatenate clips with a gap between them, for dialogues and stories.

    Silence comes from ``anullsrc`` inputs interleaved between the real ones,
    then everything goes through a single ``concat``. Doing it in one ffmpeg
    invocation rather than pairwise avoids repeated MP3 re-encoding, which is
    lossy each time.
    """
    if not parts:
        raise ValueError("nothing to merge")
    output.parent.mkdir(parents=True, exist_ok=True)
    if len(parts) == 1:
        shutil.copy2(parts[0], output)
        return output

    count = len(parts)
    args: list[str] = ["-y"]
    for part in parts:
        args.extend(["-i", str(part)])
    silence = f"anullsrc=r=24000:cl=mono:d={silence_ms / 1000}"
    for _ in range(count - 1):
        args.extend(["-f", "lavfi", "-i", silence])

    # Interleave clip, silence, clip, silence, ..., clip.
    chain: list[str] = []
    for index in range(count):
        chain.append(f"[{index}:a]")
        if index < count - 1:
            chain.append(f"[{count + index}:a]")
    total = count + (count - 1)

    args.extend([
        "-filter_complex", f"{''.join(chain)}concat=n={total}:v=0:a=1[out]",
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(output),
    ])
    _ffmpeg(*args)
    return output


async def synthesize_all(jobs: list[Job], *, force: bool = False, on_progress=None) -> list[Path]:
    """Convenience wrapper: one-shot synthesis with a fresh cache."""
    return await Synthesizer().run(jobs, force=force, on_progress=on_progress)
