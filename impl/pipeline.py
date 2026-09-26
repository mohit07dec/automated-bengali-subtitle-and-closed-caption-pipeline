"""
Main Pipeline Orchestrator for Bengali Subtitle & Closed-Caption Pipeline
Orchestrates:
1. Audio extraction & multi-feature acoustic classification (speech, music, silence)
2. Visual shot-change detection via FFmpeg
3. Concurrent Bengali ASR (Google Speech API bn-BD/bn-IN + Unicode verification)
4. Acoustic voice feature speaker diarization (SPEAKER_01, SPEAKER_02)
5. Broadcast caption formatting (CPS <= 20, max 42 chars/line, shot snapping, non-speech integration)
6. Multilingual translation (Bengali -> English, Bengali -> Hindi)
7. Semantic & Multi-dimensional QC Engine producing ranked review queue and explainable score
8. Export of all 6 deliverables: VTT and SRT for Bengali, English, and Hindi
"""

import os
import json
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict

from vad import VADProcessor
from asr import ASRProcessor
from diarization import DiarizationProcessor
from caption import CaptionGenerator
from qc import QCReporter, QCReport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PipelineConfig:
    """Pipeline Configuration"""
    asr_language: str = "bn"
    output_format: str = "both"  # "webvtt", "srt", "both"
    generate_translations: bool = True
    enable_qc: bool = True

class BengaliSubtitlePipeline:
    """
    End-to-End Bengali Broadcast Subtitle & Diarization Pipeline.
    """

    def __init__(self, config: PipelineConfig = None):
        self.config = config or PipelineConfig()
        self.vad_processor = VADProcessor(self.config)
        self.asr_processor = ASRProcessor(self.config)
        self.diarization_processor = DiarizationProcessor(self.config)
        self.caption_generator = CaptionGenerator(self.config)
        self.qc_reporter = QCReporter(self.config)

    def process_video(self, video_path: str, output_dir: str, max_duration: int = 180) -> Dict[str, Any]:
        """
        Execute full pipeline on input video.
        """
        logger.info(f"=== Starting Pipeline for Video: {video_path} ===")
        os.makedirs(output_dir, exist_ok=True)

        source_dur = self.vad_processor.get_video_duration(video_path)
        processed_dur = min(source_dur, max_duration) if max_duration > 0 and source_dur > 0 else source_dur

        # 1. Audio Extraction
        wav_path = os.path.join(output_dir, "extracted_audio.wav")
        if not self.vad_processor.extract_wav(video_path, wav_path, max_duration=max_duration):
            raise RuntimeError(f"FFmpeg audio extraction failed for {video_path}")

        try:
            # 2. Shot Change Detection (Scene Cuts)
            shot_times = self.vad_processor.detect_shot_changes(video_path, max_duration=max_duration)

            # 3. Audio Event Classification (Speech, Music, Silence)
            speech_segments, non_speech_events = self.vad_processor.process_audio(wav_path)

            # 4. Bengali ASR (Unicode script verification & code-switching)
            asr_results = self.asr_processor.process(wav_path, speech_segments)

            # 5. Acoustic Speaker Diarization
            diarized_results = self.diarization_processor.process(wav_path, asr_results)

            # 6. Broadcast Cue Assembly & Formatting (CPS, Shot Snapping, Music Cues)
            cues = self.caption_generator.build_cues(
                diarized_results,
                non_speech_events=non_speech_events,
                shot_times=shot_times
            )

            # 7. Concurrent Multilingual Translation & 6-Track Export (VTT + SRT)
            file_paths, bn_cues, en_cues, hi_cues = self.caption_generator.generate_all_tracks(cues, output_dir)

            # Extract silence regions and music regions for QC hallucination validation
            silence_regions = [s for s in speech_segments if s.get('type') == 'silence']
            silence_regions.extend(non_speech_events)

            # 8. Semantic & Multi-dimensional QC Engine with Full-Video Coverage
            qc_report = self.qc_reporter.analyze(
                bn_cues,
                en_cues=en_cues,
                hi_cues=hi_cues,
                silence_regions=silence_regions,
                shot_times=shot_times,
                source_duration=source_dur,
                processed_duration=processed_dur
            )

            # Read VTT outputs for frontend consumption
            vtt_bn = open(file_paths['bengali_vtt'], encoding='utf-8').read()
            vtt_en = open(file_paths['english_vtt'], encoding='utf-8').read()
            vtt_hi = open(file_paths['hindi_vtt'], encoding='utf-8').read()

            result = {
                "vtt_bengali": vtt_bn,
                "vtt_english": vtt_en,
                "vtt_hindi": vtt_hi,
                "caption_files": file_paths,
                "qc_report": asdict(qc_report),
                "qcIssues": qc_report.issues,
                "score": int(round(qc_report.overall_quality_score)),
                "total_cues": len(bn_cues),
                "detected_speakers": sorted(list(set(c['speaker'] for c in bn_cues))),
                "non_speech_count": len(non_speech_events),
                "source_duration": qc_report.source_duration,
                "processed_duration": qc_report.processed_duration,
                "coverage_ratio": qc_report.coverage_ratio,
                "coverage_score": qc_report.coverage_score
            }

            logger.info(f"=== Pipeline Finished! Cues: {len(bn_cues)}, QC Issues: {len(qc_report.issues)}, Score: {result['score']}/100 ===")
            return result

        finally:
            if os.path.exists(wav_path):
                try:
                    os.unlink(wav_path)
                except Exception:
                    pass