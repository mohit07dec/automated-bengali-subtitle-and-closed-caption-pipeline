"""
Broadcast Caption Generator & Multilingual Timed Text Processor
Implements:
1. Broadcast timed-text standards (CPS <= 20, max 42 chars/line, 2 lines max)
2. Shot-boundary alignment (snapping cues away from hard scene cuts)
3. Non-speech event integration ([MUSIC] merged sensibly, not overlapping speech)
4. Real dynamic translation to English (en-US) and Hindi (hi-IN)
5. Export of all 6 deliverable tracks: VTT and SRT for BN, EN, HI
"""

import os
import re
import json
import logging
import urllib.request
import urllib.parse
import concurrent.futures
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

_TRANSLATE_CACHE = {}

def translate_api(text: str, target_lang: str) -> str:
    """
    Translate text using robust multi-provider translation (Google GTX + MyMemory fallback)
    target_lang: 'en' or 'hi'
    """
    if not text.strip() or text.startswith("["):
        if text.strip() == "[MUSIC]":
            return "[MUSIC]" if target_lang == "en" else "[संगीत]"
        return text

    cache_key = (text.strip(), target_lang)
    if cache_key in _TRANSLATE_CACHE:
        return _TRANSLATE_CACHE[cache_key]

    CLIENT_POOLS = ["dict-chrome-ex", "tw-ob", "it", "gtx"]
    for cl in CLIENT_POOLS:
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client={cl}&sl=bn&tl={target_lang}&dt=t&q={urllib.parse.quote(text.strip())}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data and isinstance(data, list) and len(data) > 0 and data[0]:
                    trans = "".join([segment[0] for segment in data[0] if segment and segment[0]]).strip()
                    trans = re.sub(r'<[^>]+>', '', trans).strip()
                    trans = trans.replace('&quot;', '"').replace('&amp;', '&').replace('&#39;', "'").replace('&apos;', "'")
                    if trans and trans.lower() != text.strip().lower():
                        _TRANSLATE_CACHE[cache_key] = trans
                        return trans
        except Exception as e:
            logger.debug(f"Translation client '{cl}' error for '{text[:20]}' -> {target_lang}: {e}")

    # Fallback to MyMemory
    try:
        url_mm = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text.strip())}&langpair=bn|{target_lang}"
        req = urllib.request.Request(url_mm, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            trans = data.get("responseData", {}).get("translatedText", "").strip()
            trans = re.sub(r'<[^>]+>', '', trans).strip()
            trans = trans.replace('&quot;', '"').replace('&amp;', '&').replace('&#39;', "'").replace('&apos;', "'")
            if trans and not trans.startswith("PLEASE SELECT") and not trans.startswith("MYMEMORY WARNING") and trans.lower() != text.strip().lower():
                _TRANSLATE_CACHE[cache_key] = trans
                return trans
    except Exception as e:
        logger.debug(f"MyMemory translation error for '{text[:20]}' -> {target_lang}: {e}")

    # Explicit failure marker instead of returning raw Bengali text
    return "[Translation Unavailable]"

class CaptionGenerator:
    """
    Caption Generator & Multilingual Translator.
    Enforces broadcast constraints, scene boundary alignments, and multilingual exports.
    """

    def __init__(self, config=None):
        self.config = config

    def _format_time_vtt(self, seconds: float) -> str:
        """Format seconds to WebVTT timestamp HH:MM:SS.mmm"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        sec = int(s)
        ms = int(round((s - sec) * 1000))
        if ms >= 1000:
            sec += 1
            ms = 0
        return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"

    def _format_time_srt(self, seconds: float) -> str:
        """Format seconds to SRT timestamp HH:MM:SS,mmm"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        sec = int(s)
        ms = int(round((s - sec) * 1000))
        if ms >= 1000:
            sec += 1
            ms = 0
        return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

    def build_cues(self,
                   asr_results: List[Any],
                   non_speech_events: List[Dict[str, Any]] = None,
                   shot_times: List[float] = None) -> List[Dict[str, Any]]:
        """
        Assemble and format broadcast-compliant subtitle cues.
        """
        cues = []
        non_speech_events = non_speech_events or []
        shot_times = shot_times or []

        # 1. Process Dialogue Cues
        for res in asr_results:
            text = getattr(res, 'text', '').strip()
            if not text:
                continue

            st = getattr(res, 'start_time', 0.0)
            et = getattr(res, 'end_time', st + 1.5)
            spk = getattr(res, 'speaker_id', 'SPEAKER_01')
            conf = getattr(res, 'confidence', 0.85)

            # Enforce minimum display duration & CPS limit (<= 20)
            dur = max(1.0, et - st)
            cps = len(text) / dur
            if cps > 20.0:
                dur = len(text) / 20.0
                et = st + dur

            # Handle long utterances (> 6s): split into natural broadcast chunks (3-6s)
            word_ts = getattr(res, 'word_timestamps', [])
            if dur > 6.0 and word_ts and len(word_ts) >= 6:
                # Group words into ~3.5s - 5.0s chunks
                chunk_words = []
                chunk_st = st
                for w_idx, w_obj in enumerate(word_ts):
                    chunk_words.append(w_obj['word'])
                    w_end = w_obj['end']
                    is_last = (w_idx == len(word_ts) - 1)
                    chunk_dur = w_end - chunk_st

                    if chunk_dur >= 3.5 or is_last:
                        sub_text = " ".join(chunk_words)
                        # Format line wraps
                        sub_lines = []
                        c_line = ""
                        for sw in sub_text.split():
                            if len(c_line) + len(sw) + 1 <= 42:
                                c_line = f"{c_line} {sw}".strip()
                            else:
                                sub_lines.append(c_line)
                                c_line = sw
                        if c_line:
                            sub_lines.append(c_line)
                        f_text = "\n".join(sub_lines[:2])

                        cues.append({
                            'start_time': round(chunk_st, 3),
                            'end_time': round(w_end, 3),
                            'speaker': spk,
                            'text': f_text,
                            'raw_text': sub_text,
                            'confidence': conf,
                            'type': 'dialogue'
                        })
                        chunk_words = []
                        chunk_st = w_end
                continue

            # Snap away from shot changes if within 250ms of a cut
            for cut in shot_times:
                if abs(et - cut) < 0.25:
                    et = cut - 0.05
                    break
                elif abs(st - cut) < 0.25:
                    st = cut + 0.05
                    break

            # Line wrapping: max 42 chars per line, max 2 lines
            words = text.split()
            lines = []
            curr_line = ""
            for w in words:
                if len(curr_line) + len(w) + 1 <= 42:
                    curr_line = f"{curr_line} {w}".strip()
                else:
                    lines.append(curr_line)
                    curr_line = w
            if curr_line:
                lines.append(curr_line)

            formatted_text = "\n".join(lines[:2])

            cues.append({
                'start_time': round(st, 3),
                'end_time': round(et, 3),
                'speaker': spk,
                'text': formatted_text,
                'raw_text': text,
                'confidence': conf,
                'type': 'dialogue'
            })

        # 2. Add Non-speech (Music) Cues where there is no dialogue overlap
        for ns in non_speech_events:
            nst, net = ns['start'], ns['end']
            # Check overlap with any dialogue cue
            has_overlap = any(
                not (net <= c['start_time'] or nst >= c['end_time'])
                for c in cues
            )
            if not has_overlap and (net - nst) >= 1.5:
                cues.append({
                    'start_time': round(nst, 3),
                    'end_time': round(net, 3),
                    'speaker': 'MUSIC',
                    'text': ns.get('event', '[MUSIC]'),
                    'raw_text': ns.get('event', '[MUSIC]'),
                    'confidence': 0.90,
                    'type': 'non_speech'
                })

        # Sort all cues by start_time
        cues.sort(key=lambda x: x['start_time'])

        # Ensure no overlapping cue boundaries
        for i in range(len(cues) - 1):
            if cues[i]['end_time'] > cues[i+1]['start_time']:
                cues[i]['end_time'] = round(max(cues[i]['start_time'] + 0.5, cues[i+1]['start_time'] - 0.05), 3)

        return cues

    def generate_all_tracks(self, cues: List[Dict[str, Any]], output_dir: str) -> Tuple[Dict[str, str], List[Dict], List[Dict], List[Dict]]:
        """
        Generate all 6 subtitle tracks (VTT + SRT for Bengali, English, Hindi) concurrently.
        """
        os.makedirs(output_dir, exist_ok=True)
        bn_cues = cues

        logger.info(f"Caption: Generating translations for {len(bn_cues)} cues...")

        def translate_single_cue(c):
            raw = c['raw_text']
            en_text = translate_api(raw, 'en')
            hi_text = translate_api(raw, 'hi')

            c_en = c.copy()
            c_en['text'] = en_text

            c_hi = c.copy()
            c_hi['text'] = hi_text

            return c_en, c_hi

        en_cues = []
        hi_cues = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            translations = list(executor.map(translate_single_cue, bn_cues))

        for c_en, c_hi in translations:
            en_cues.append(c_en)
            hi_cues.append(c_hi)

        file_paths = {}

        # 1. Bengali VTT & SRT
        bn_vtt = os.path.join(output_dir, "bengali_captions.vtt")
        self._write_vtt(bn_cues, bn_vtt)
        file_paths['bengali_vtt'] = bn_vtt

        bn_srt = os.path.join(output_dir, "bengali_captions.srt")
        self._write_srt(bn_cues, bn_srt)
        file_paths['bengali_srt'] = bn_srt

        # 2. English VTT & SRT
        en_vtt = os.path.join(output_dir, "en_captions.vtt")
        self._write_vtt(en_cues, en_vtt)
        file_paths['english_vtt'] = en_vtt

        en_srt = os.path.join(output_dir, "en_captions.srt")
        self._write_srt(en_cues, en_srt)
        file_paths['english_srt'] = en_srt

        # 3. Hindi VTT & SRT
        hi_vtt = os.path.join(output_dir, "hi_captions.vtt")
        self._write_vtt(hi_cues, hi_vtt)
        file_paths['hindi_vtt'] = hi_vtt

        hi_srt = os.path.join(output_dir, "hi_captions.srt")
        self._write_srt(hi_cues, hi_srt)
        file_paths['hindi_srt'] = hi_srt

        return file_paths, bn_cues, en_cues, hi_cues

    def _write_vtt(self, cues: List[Dict[str, Any]], path: str):
        """Write WebVTT with standard voice tags"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n")
            for c in cues:
                st = self._format_time_vtt(c['start_time'])
                et = self._format_time_vtt(c['end_time'])
                spk = c['speaker']
                txt = c['text']
                f.write(f"{st} --> {et}\n")
                f.write(f"<v {spk}>{txt}</v>\n\n")

    def _write_srt(self, cues: List[Dict[str, Any]], path: str):
        """Write SRT file"""
        with open(path, 'w', encoding='utf-8') as f:
            for idx, c in enumerate(cues, 1):
                st = self._format_time_srt(c['start_time'])
                et = self._format_time_srt(c['end_time'])
                spk = c['speaker']
                txt = c['text'].replace('\n', ' ')
                f.write(f"{idx}\n")
                f.write(f"{st} --> {et}\n")
                f.write(f"[{spk}] {txt}\n\n")