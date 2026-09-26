"""
VAD & Audio-Visual Preprocessor for Bengali Subtitle Pipeline
Implements:
1. 16kHz mono audio extraction from video
2. Multi-feature acoustic event classification (Speech, Music, Silence, Ambient)
3. Shot-boundary scene change detection using FFmpeg
"""

import os
import subprocess
import logging
import wave
import struct
import math
import numpy as np
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class VADProcessor:
    """
    Acoustic Event Detector & Video Scene Preprocessor.
    Detects speech turns, music intervals, silence, and visual shot boundaries.
    """

    def __init__(self, config=None):
        self.config = config
    def get_video_duration(self, video_path: str) -> float:
        """Get exact duration in seconds from media file using ffprobe."""
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return float(r.stdout.strip())
        except Exception:
            return 0.0

    def extract_wav(self, video_path: str, out_wav: str, max_duration: int = 180) -> bool:
        """Extract 16kHz mono 16-bit WAV from video."""
        cmd = ["ffmpeg", "-y", "-ss", "0", "-i", video_path]
        if max_duration > 0:
            cmd.extend(["-t", str(max_duration)])
        cmd.extend(["-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", out_wav])
        r = subprocess.run(cmd, capture_output=True)
        return r.returncode == 0 and os.path.exists(out_wav)

    def detect_shot_changes(self, video_path: str, max_duration: int = 180) -> List[float]:
        """
        Detect visual shot changes (scene cuts) using FFmpeg scene filter.
        Returns list of timestamps in seconds.
        """
        shot_times = []
        cmd = ["ffmpeg", "-ss", "0", "-i", video_path]
        if max_duration > 0:
            cmd.extend(["-t", str(max_duration)])
        cmd.extend(["-filter:v", "select='gt(scene,0.32)',showinfo", "-f", "null", "-"])
        
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            for line in p.stderr.splitlines():
                if "showinfo" in line and "pts_time:" in line:
                    parts = line.split("pts_time:")
                    if len(parts) > 1:
                        time_str = parts[1].split()[0]
                        try:
                            shot_times.append(float(time_str))
                        except ValueError:
                            pass
        except Exception as e:
            logger.warning(f"Shot change detection non-critical timeout/failure: {e}")

        logger.info(f"Detected {len(shot_times)} shot changes in video")
        return shot_times

    def process_audio(self, wav_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Classify audio into speech segments, music regions, and silence.
        Returns:
            speech_segments: List of speech chunks for ASR
            non_speech_events: List of music/sound events for captioning
        """
        if not os.path.exists(wav_path):
            return [], []

        try:
            wf = wave.open(wav_path, 'rb')
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            audio_bytes = wf.readframes(n_frames)
            wf.close()
            samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        except Exception as e:
            logger.error(f"Error reading WAV: {e}")
            return [], []

        # 400ms analysis window, 200ms hop
        win_size = int(framerate * 0.4)
        hop_size = int(framerate * 0.2)

        classified_frames = []
        for idx in range(0, len(samples) - win_size, hop_size):
            t_start = idx / framerate
            t_end = (idx + win_size) / framerate
            chunk = samples[idx : idx + win_size]

            # 1. RMS Energy
            rms = np.sqrt(np.mean(chunk**2))
            if rms < 55.0:
                classified_frames.append((t_start, t_end, 'silence', rms, 0.0))
                continue

            # 2. Zero-crossing rate
            zcr = np.mean(np.abs(np.diff(np.sign(chunk)))) / 2.0

            # 3. FFT Spectral features
            fft = np.abs(np.fft.rfft(chunk * np.hanning(len(chunk)))) + 1e-10
            sf = np.exp(np.mean(np.log(fft))) / np.mean(fft)  # spectral flatness

            freqs = np.fft.rfftfreq(len(chunk), 1.0 / framerate)
            vocal_mask = (freqs >= 300) & (freqs <= 3400)
            vocal_ratio = np.sum(fft[vocal_mask]) / np.sum(fft)

            # Classify:
            # Speech: concentrated vocal energy, dynamic ZCR, substantial volume
            # Music: low spectral flatness (strong harmonics/tonal peaks), bass/synth
            # Ambient/Noise: high spectral flatness, broadband
            if vocal_ratio >= 0.50 and zcr >= 0.04 and rms > 280.0:
                classified_frames.append((t_start, t_end, 'speech', rms, vocal_ratio))
            elif sf < 0.20 and rms > 120.0:
                classified_frames.append((t_start, t_end, 'music', rms, sf))
            else:
                classified_frames.append((t_start, t_end, 'ambient', rms, sf))

        # Merge contiguous frames of same type
        raw_regions = []
        curr_type = None
        curr_start = 0.0
        curr_rms_sum = 0.0
        curr_count = 0

        for t0, t1, label, rms_val, feat in classified_frames:
            if label != curr_type:
                if curr_type and (t0 - curr_start) >= 0.5:
                    raw_regions.append({
                        'start': round(curr_start, 3),
                        'end': round(t0, 3),
                        'duration': round(t0 - curr_start, 3),
                        'type': curr_type,
                        'rms': round(curr_rms_sum / max(1, curr_count), 1)
                    })
                curr_type = label
                curr_start = t0
                curr_rms_sum = rms_val
                curr_count = 1
            else:
                curr_rms_sum += rms_val
                curr_count += 1

        if curr_type and classified_frames:
            raw_regions.append({
                'start': round(curr_start, 3),
                'end': round(classified_frames[-1][1], 3),
                'duration': round(classified_frames[-1][1] - curr_start, 3),
                'type': curr_type,
                'rms': round(curr_rms_sum / max(1, curr_count), 1)
            })

        # Separate speech segments and non-speech events
        speech_segments = []
        non_speech_events = []

        for r in raw_regions:
            if r['type'] == 'speech':
                # Pad speech start and end slightly for natural boundary
                start = max(0.0, r['start'] - 0.15)
                end = r['end'] + 0.15
                speech_segments.append({
                    'start': round(start, 3),
                    'end': round(end, 3),
                    'duration': round(end - start, 3),
                    'type': 'speech',
                    'rms': r['rms']
                })
            elif r['type'] == 'music' and r['duration'] >= 1.5:
                non_speech_events.append({
                    'start': r['start'],
                    'end': r['end'],
                    'duration': r['duration'],
                    'event': '[MUSIC]'
                })

        # Merge nearby speech segments if gap < 0.4s
        merged_speech = []
        for s in speech_segments:
            if merged_speech and s['start'] - merged_speech[-1]['end'] < 0.4:
                merged_speech[-1]['end'] = s['end']
                merged_speech[-1]['duration'] = round(s['end'] - merged_speech[-1]['start'], 3)
            else:
                merged_speech.append(s)

        # Merge nearby music segments if gap < 1.0s
        merged_music = []
        for m in non_speech_events:
            if merged_music and m['start'] - merged_music[-1]['end'] < 1.0:
                merged_music[-1]['end'] = m['end']
                merged_music[-1]['duration'] = round(m['end'] - merged_music[-1]['start'], 3)
            else:
                merged_music.append(m)

        logger.info(f"VAD: {len(merged_speech)} speech segments, {len(merged_music)} music events")
        return merged_speech, merged_music