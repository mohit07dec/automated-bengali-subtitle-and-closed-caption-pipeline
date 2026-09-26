"""
Speaker Diarization Processor for Bengali Subtitle Pipeline
Implements:
1. Voice feature extraction (F0 pitch estimation, spectral centroid, energy RMS)
2. Acoustic clustering for stable speaker attribution (SPEAKER_01, SPEAKER_02)
3. Speaker identity preservation across scene transitions
"""

import os
import wave
import struct
import math
import numpy as np
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class DiarizationProcessor:
    """
    Speaker Diarization Processor using Acoustic Feature Clustering.
    Extracts fundamental frequency (F0), spectral brightness, and energy
    to cluster speech turns into stable speaker identities.
    """

    def __init__(self, config=None):
        self.config = config

    def _extract_voice_features(self, wav_path: str, start: float, duration: float) -> Dict[str, float]:
        """Extract vocal acoustic features from audio interval."""
        try:
            wf = wave.open(wav_path, 'rb')
            framerate = wf.getframerate()
            start_frame = int(start * framerate)
            n_frames = int(max(0.4, duration) * framerate)
            wf.setpos(min(start_frame, max(0, wf.getnframes() - 1)))
            audio_bytes = wf.readframes(n_frames)
            wf.close()

            if len(audio_bytes) < 160:
                return {'rms': 1000.0, 'brightness': 50.0, 'pitch_proxy': 150.0}

            samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
            if len(samples) < 100:
                return {'rms': 1000.0, 'brightness': 50.0, 'pitch_proxy': 150.0}

            # 1. RMS Energy
            rms = float(np.sqrt(np.mean(samples**2)))

            # 2. Spectral Brightness / Centroid approximation
            diff_sum = float(np.mean(np.abs(np.diff(samples))))

            # 3. Autocorrelation Pitch proxy (fundamental frequency estimation)
            corr = np.correlate(samples[:min(len(samples), 4000)], samples[:min(len(samples), 4000)], mode='full')
            corr = corr[len(corr)//2 :]
            # Search in speech pitch range: 80Hz - 400Hz (at 16kHz, lag 40 to 200)
            lag_min, lag_max = int(framerate / 400), int(framerate / 80)
            if len(corr) > lag_max:
                peak_lag = lag_min + np.argmax(corr[lag_min:lag_max])
                pitch_hz = float(framerate / max(1, peak_lag))
            else:
                pitch_hz = 150.0

            return {'rms': rms, 'brightness': diff_sum, 'pitch_proxy': pitch_hz}
        except Exception:
            return {'rms': 1000.0, 'brightness': 50.0, 'pitch_proxy': 150.0}

    def process(self, wav_path: str, asr_results: List[Any]) -> List[Any]:
        """
        Cluster ASR results into stable speaker IDs based on voice characteristics.
        """
        if not asr_results:
            return []

        logger.info(f"Diarization: Extracting voice features for {len(asr_results)} speech turns...")
        features = []

        for res in asr_results:
            st = getattr(res, 'start_time', 0.0)
            et = getattr(res, 'end_time', st + 1.5)
            dur = max(0.4, et - st)
            feat = self._extract_voice_features(wav_path, st, dur)
            features.append(feat)

        # Construct feature matrix X across pitch F0, spectral brightness, and RMS energy
        pitches = np.array([f['pitch_proxy'] for f in features], dtype=np.float32)
        brightness = np.array([f['brightness'] for f in features], dtype=np.float32)
        rms = np.array([f['rms'] for f in features], dtype=np.float32)

        def norm(v):
            std = float(np.std(v))
            return (v - np.mean(v)) / (std if std > 1e-4 else 1.0)

        p_norm = norm(pitches)
        b_norm = norm(brightness)
        r_norm = norm(rms)
        X = np.column_stack([p_norm * 1.5, b_norm, r_norm * 0.8])

        # If variance is very low, single speaker detected
        if float(np.std(pitches)) < 8.0 and float(np.std(brightness)) < 10.0:
            labels = np.zeros(len(asr_results), dtype=int)
        else:
            # Deterministic 2-Means acoustic clustering
            c1 = X[np.argmin(X[:, 0])]
            c2 = X[np.argmax(X[:, 0])]
            labels = np.zeros(len(X), dtype=int)
            for _ in range(20):
                d1 = np.sum((X - c1)**2, axis=1)
                d2 = np.sum((X - c2)**2, axis=1)
                new_labels = (d2 < d1).astype(int)
                if np.array_equal(labels, new_labels):
                    break
                labels = new_labels
                if np.sum(labels == 0) > 0:
                    c1 = X[labels == 0].mean(axis=0)
                if np.sum(labels == 1) > 0:
                    c2 = X[labels == 1].mean(axis=0)

        # Consistent first-speaker attribution: first speaking turn is SPEAKER_01
        first_cluster = labels[0] if len(labels) > 0 else 0
        for idx, res in enumerate(asr_results):
            spk = 'SPEAKER_01' if labels[idx] == first_cluster else 'SPEAKER_02'
            setattr(res, 'speaker_id', spk)

        # Smooth momentary 1-frame flips if duration < 1.0s between identical speakers
        for i in range(1, len(asr_results) - 1):
            prev_spk = getattr(asr_results[i-1], 'speaker_id')
            curr_spk = getattr(asr_results[i], 'speaker_id')
            next_spk = getattr(asr_results[i+1], 'speaker_id')
            dur = getattr(asr_results[i], 'end_time') - getattr(asr_results[i], 'start_time')

            if prev_spk == next_spk and curr_spk != prev_spk and dur < 0.9:
                setattr(asr_results[i], 'speaker_id', prev_spk)

        logger.info(f"Diarization: Attribution complete for {len(asr_results)} speech turns")
        return asr_results