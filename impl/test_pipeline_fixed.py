#!/usr/bin/env python3
"""
Test script for Bengali Subtitle Pipeline
Demonstrates the complete pipeline with QC reporting
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dataclasses import dataclass
from pipeline import BengaliSubtitlePipeline, PipelineConfig
from vad import VADProcessor
from asr import ASRProcessor
from diarization import DiarizationProcessor
from alignment import AlignmentProcessor
from caption import CaptionGenerator
from qc import QCReporter, QCReport, QCConfig

def test_vad_processor():
    """Test VAD processor"""
    print("Testing VAD Processor...")
    config = PipelineConfig()
    vad_processor = VADProcessor(config)

    # Test with dummy audio path
    speech_segments = vad_processor.process("dummy_audio.wav")
    print(f"✓ VAD Processor: Found {len(speech_segments)} speech segments")
    return True

def test_asr_processor():
    """Test ASR processor"""
    print("Testing ASR Processor...")
    config = PipelineConfig()
    asr_processor = ASRProcessor(config)

    # Test with dummy speech segments
    dummy_segments = [{'start': 0.0, 'end': 5.0}, {'start': 6.0, 'end': 10.0}]
    asr_results = asr_processor.process(dummy_segments)
    print(f"✓ ASR Processor: Generated {len(asr_results)} ASR results")
    return True

def test_diarization_processor():
    """Test diarization processor"""
    print("Testing Diarization Processor...")
    config = PipelineConfig()
    diarization_processor = DiarizationProcessor(config)

    # Test with dummy audio path
    diarization_result = diarization_processor.process("dummy_audio.wav")
    print(f"✓ Diarization Processor: Found {len(diarization_result.speaker_ids)} speakers")
    return True

def test_alignment_processor():
    """Test alignment processor"""
    print("Testing Alignment Processor...")
    config = PipelineConfig()
    alignment_processor = AlignmentProcessor(config)

    # Test with dummy inputs
    dummy_asr_results = [type('ASRResult', (), {'text': 'হ্যালো dunia', 'confidence': 0.8, 'word_timestamps': []})()]
    alignment_result = alignment_processor.process("dummy_audio.wav", dummy_asr_results)
    print(f"✓ Alignment Processor: Alignment score {alignment_result.alignment_score:.3f}")
    return True

def test_caption_generator():
    """Test caption generator"""
    print("Testing Caption Generator...")
    config = PipelineConfig()
    caption_generator = CaptionGenerator(config)

    # Test with dummy inputs
    dummy_asr_results = [type('ASRResult', (), {'text': 'হ্যালো Dunia', 'confidence': 0.8, 'word_timestamps': []})()]
    dummy_diarization = type('DiarizationResult', (), {
        'segments': [{'start': 0.0, 'end': 5.0, 'speaker_id': 'SPEAKER_01', 'confidence': 0.9}],
        'speaker_ids': ['SPEAKER_01'],
        'speaker_confidence': {'SPEAKER_01': 0.9}
    })()
    dummy_alignment = type('AlignmentResult', (), {
        'word_alignments': [{'word': 'হ্যালো', 'start': 0.0, 'end': 1.0, 'confidence': 0.8, 'speaker_id': 'SPEAKER_01'}],
        'alignment_score': 0.8,
        'average_word_error': 0.2
    })()

    captions = caption_generator.generate_captions(dummy_asr_results, dummy_diarization, dummy_alignment)
    print(f"✓ Caption Generator: Generated {len(captions)} caption cues")
    return True

def test_qc_reporter():
    """Test QC reporter"""
    print("Testing QC Reporter...")
    qc_config = QCConfig()
    qc_reporter = QCReporter(qc_config)

    # Test with dummy inputs
    dummy_asr_results = [type('ASRResult', (), {'text': 'হ্যালো Dunia', 'confidence': 0.8, 'word_timestamps': []})()]
    dummy_diarization = type('DiarizationResult', (), {
        'segments': [{'start': 0.0, 'end': 5.0, 'speaker_id': 'SPEAKER_01', 'confidence': 0.9}],
        'speaker_ids': ['SPEAKER_01'],
        'speaker_confidence': {'SPEAKER_01': 0.9}
    })()
    dummy_alignment = type('AlignmentResult', (), {
        'word_alignments': [{'word': 'হ্যালো', 'start': 0.0, 'end': 1.0, 'confidence': 0.8, 'speaker_id': 'SPEAKER_01'}],
        'alignment_score': 0.8,
        'average_word_error': 0.2
    })()
    dummy_vad_segments = [{'start': 0.0, 'end': 5.0, 'speech_probability': 0.9}]

    qc_report = qc_reporter.generate_report(
        asr_results=dummy_asr_results,
        diarization_result=dummy_diarization,
        alignment_result=dummy_alignment,
        vad_segments=dummy_vad_segments,
        audio_duration=10.0
    )

    print(f"✓ QC Reporter: Overall quality score {qc_report.overall_quality_score:.3f}")
    print(f"✓ QC Reporter: Passes quality gate: {qc_report.passes_quality_gate}")
    return True

def test_pipeline_integration():
    """Test complete pipeline integration"""
    print("Testing Pipeline Integration...")
    config = PipelineConfig()
    pipeline = BengaliSubtitlePipeline(config)

    # Test that all components are initialized
    assert pipeline.vad_processor is not None
    assert pipeline.asr_processor is not None
    assert pipeline.diarization_processor is not None
    assert pipeline.alignment_processor is not None
    assert pipeline.caption_generator is not None
    assert pipeline.qc_reporter is not None

    print("✓ Pipeline Integration: All components initialized")
    return True

def main():
    """Run all tests"""
    print("Bengali Subtitle Pipeline Component Tests")
    print("=" * 50)

    tests = [
        test_vad_processor,
        test_asr_processor,
        test_diarization_processor,
        test_alignment_processor,
        test_caption_generator,
        test_qc_reporter,
        test_pipeline_integration
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: FAILED - {e}")

    print("=" * 50)
    print(f"Tests Passed: {passed}/{total}")

    if passed == total:
        print("🎉 All tests passed! Pipeline is ready for use.")
        return 0
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())