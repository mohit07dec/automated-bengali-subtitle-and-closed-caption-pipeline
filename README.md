# Automated Bengali Subtitle & Closed-Caption Pipeline with Speaker Diarization

> An end-to-end, AI-native broadcast subtitle and closed-captioning pipeline engineered specifically for Bengali OTT content. Ingests raw video/audio and produces production-grade Bengali captions, multi-speaker attribution, synchronized English and Hindi translations, non-speech event tags, and reference-free automated QC validation.

---

## 1. System Architecture

```
                       ┌──────────────────────────────┐
                       │     Input Video / Audio      │
                       │   (MP4, MKV, WAV, WebM)      │
                       └──────────────┬───────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
   ┌──────────────────────┐                       ┌──────────────────────┐
   │ 16kHz PCM Extraction │                       │ Visual Shot Detection│
   │  (FFmpeg Audio VAD)  │                       │  (Scene-Cut Filter)  │
   └──────────┬───────────┘                       └──────────┬───────────┘
              │                                              │
              ▼                                              │
   ┌──────────────────────────────────────────┐              │
   │  Acoustic VAD & Spectral Analysis        │              │
   │  - Log RMS Energy Thresholding           │              │
   │  - Zero Crossing Rate (ZCR)              │              │
   │  - Spectral Flatness Measure (SFM)       │              │
   │  - Vocal Band Ratio (300 Hz – 3400 Hz)   │              │
   └──────────────────┬───────────────────────┘              │
                      │                                      │
                      ▼                                      │
   ┌──────────────────────────────────────────┐              │
   │  Concurrent Bengali Speech Recognition   │              │
   │  - Dual-locale Google Indic (bn-BD/bn-IN)│              │
   │  - Bengali Unicode validation (U+0980)   │              │
   │  - Preserves natural code-switching      │              │
   └──────────────────┬───────────────────────┘              │
                      │                                      │
                      ▼                                      │
   ┌──────────────────────────────────────────┐              │
   │  Unsupervised Acoustic Diarization       │              │
   │  - Autocorrelation F0 Pitch Estimation   │              │
   │  - Spectral Centroid (Timbre Brightness) │              │
   │  - Multivariate K-Means Clustering       │              │
   │  - Temporal Flip Smoothing               │              │
   └──────────────────┬───────────────────────┘              │
                      │                                      │
                      ▼                                      │
   ┌──────────────────────────────────────────┐              │
   │  Broadcast Caption Segmentation & Timing │◄─────────────┘
   │  - Max 42 chars/line, Max 2 lines        │ (Snaps cue bounds to
   │  - Reading speed limit: CPS <= 20        │  visual shot cuts)
   │  - Non-speech tagging ([MUSIC], [SILENCE])
   └──────────────────┬───────────────────────┘
                      │
                      ▼
   ┌──────────────────────────────────────────┐
   │  Concurrent Subtitle Translation         │
   │  - Multi-client endpoint pool rotation   │
   │  - Robust fallback mechanisms            │
   │  - Explicit [Translation Unavailable]    │
   └──────────────────┬───────────────────────┘
                      │
                      ▼
   ┌──────────────────────────────────────────┐
   │  6-Factor Reference-Free QC Engine       │
   │  1. ASR Bengali Script Density           │
   │  2. Language & Phonetic Marker Filtering │
   │  3. Music/Silence Hallucination Detector │
   │  4. CPS & Temporal Overlap Validation    │
   │  5. Diarization Switch Rate Stability    │
   │  6. Full-Video Coverage Integrity        │
   └──────────────────┬───────────────────────┘
                      │
                      ▼
   ┌──────────────────────────────────────────────────────────┐
   │                  Export Deliverables                     │
   │  • Bengali: bengali_captions.vtt / .srt                 │
   │  • English: en_captions.vtt / .srt                       │
   │  • Hindi:   hi_captions.vtt / .srt                       │
   │  • Interactive Web UI with Synced Playback & QC Queue    │
   └──────────────────────────────────────────────────────────┘
```

---

## 2. Key Technical Innovations

### A. Bengali-Centric Acoustic VAD & Speech Filtering
Standard off-the-shelf Voice Activity Detectors often fail on Indian OTT content due to rich background music, ambient Foley, and dramatic dynamics. Our VAD implementation combines:
- **Band-Limited Vocal Energy:** Evaluates energy concentrated in the telephone-speech band ($300\text{--}3400\text{ Hz}$) relative to broad spectrum energy.
- **Spectral Flatness & Zero Crossing Rate (ZCR):** Discriminates tonal background music and instrumental interludes from high-variance speech formants.
- **Scene-Cut Boundary Snapping:** Extracts shot transitions via FFmpeg scene-change filters (`select='gt(scene,0.3)'`) to ensure caption cues never awkwardly straddle cuts.

### B. Pure-NumPy Multivariate Diarization
Rather than bundling multi-gigabyte heavy frameworks with restrictive licensing, the diarization module computes acoustic feature vectors directly from the extracted audio:
1. **$F_0$ Pitch Proxy:** Autocorrelation of band-passed signal frames to estimate fundamental pitch contours.
2. **Spectral Centroid:** Computes the frequency center-of-mass to distinguish vocal tract brightness and timbre differences.
3. **Log RMS Energy:** Dynamic energy distribution per speech segment.
4. **Multivariate Clustering:** K-Means clustering with temporal flip smoothing to prevent unnatural ping-pong speaker alternations between adjacent sub-second words.

### C. Broadcast Subtitle Formatting (EBU-TT / Netflix Compliance)
Raw transcription text is unsuitable for broadcast display. The caption generator enforces strict subtitle standards:
- **Character Count:** Maximum 42 characters per line, maximum 2 lines per subtitle cue.
- **Reading Speed:** Maximum 20 Characters Per Second (CPS). Any segment exceeding CPS is dynamically split or elongated to guarantee readability.
- **Natural Syntactic Breaks:** Splits on punctuation marks, conjunctions, and clause boundaries rather than arbitrary character slicing.

### D. Resilient Multi-Client Translation
Bengali speech is translated into both English and Hindi subtitle tracks. To guard against rate limits and transient connection drops:
- Rotates across a distributed pool of translation client endpoints (`dict-chrome-ex`, `tw-ob`, `it`, `gtx`).
- Employs exponential backoff and alternate API fallbacks.
- **Honest Error Handling:** Never silently duplicates raw Bengali text into English/Hindi tracks. In the event of an upstream translation failure, the segment is explicitly marked with `[Translation Unavailable]`.

### E. 6-Factor Reference-Free Automated QC Engine
Without requiring human-annotated ground-truth transcripts, the system validates output quality across six objective dimensions:
1. **ASR Script Density:** Verifies high proportion of valid Bengali Unicode (`\u0980`–`\u09FF`) and penalizes empty or blank cues.
2. **Language & Phonetic Purity:** Catches cross-lingual transliteration artifacts (e.g. Hindi grammar markers mistakenly transcribed in Bengali script like `হে`, `সাকতে`, `গায়রে`).
3. **Hallucination Detection:** Flags captions that overlap with acoustic silence or non-speech musical passages.
4. **Broadcast Timing & Formatting:** Detects negative timestamps, cue overlaps, short flashes ($< 0.8\text{s}$), or excessive CPS ($> 20$).
5. **Diarization Stability:** Penalizes erratic speaker oscillations across short intervals.
6. **Full-Video Coverage:** Verifies captions span the full timeline of the media file.

---

## 3. Repository Structure

```
├── impl/
│   ├── api_server.py             # Multi-threaded HTTP server (port 8081)
│   ├── pipeline.py               # Master pipeline orchestrator
│   ├── vad.py                    # Audio extraction, visual scene-cuts, acoustic VAD
│   ├── asr.py                    # Bengali speech recognition engine & phonetic checks
│   ├── diarization.py            # Feature extraction & multivariate speaker clustering
│   ├── caption.py                # Broadcast segmentation, CPS limits & translation
│   ├── qc.py                     # 6-factor reference-free automated QC engine
│   └── test_pipeline_regression.py # 21-point automated regression test suite
├── app/                          # Modern React 19 + TypeScript + Vite frontend
│   ├── src/
│   │   ├── App.tsx               # Interactive player, transcript sync, QC review queue
│   │   └── components/ui/        # Modular UI components
│   ├── package.json
│   └── vite.config.ts
├── requirements.txt              # Production Python dependencies
├── .gitignore                    # Excludes media, cache, virtualenvs & temporary files
└── README.md                     # Technical architecture and documentation
```

---

## 4. Getting Started

### Prerequisites
- **Python:** 3.9+
- **Node.js:** 18+ (for the demo UI)
- **FFmpeg & FFprobe:** Installed and available in your system `PATH`
  ```bash
  # Debian/Ubuntu
  sudo apt-get update && sudo apt-get install -y ffmpeg
  ```

### 1. Backend Setup
```bash
# Clone the repository
git clone https://github.com/mohit07dec/automated-bengali-subtitle-and-closed-caption-pipeline.git
cd automated-bengali-subtitle-and-closed-caption-pipeline

# Install Python dependencies
pip install -r requirements.txt

# Start the multi-threaded API server
python3 impl/api_server.py
# Server starts listening on http://localhost:8081
```

### 2. Frontend Setup
```bash
# Open a new terminal in the repository root
cd app

# Install Node dependencies
npm install

# Start the development server
npm run dev -- --host 0.0.0.0 --port 3000
# Accessible at http://localhost:3000
```

---

## 5. Verification & Testing

The repository includes a comprehensive 21-point automated test suite verifying every component against the hackathon criteria:

```bash
python3 impl/test_pipeline_regression.py
```

### Verified Test Categories:
- **ASR & Script Integrity:** Bengali script presence, Unicode compliance, code-switching preservation.
- **Timing & Formatting:** Strict $CPS \le 20$, minimum/maximum cue durations, monotonic timestamps.
- **Zero Cue Overlaps:** Guarantees no two subtitle cues collide or overlap in time.
- **Speaker Attribution:** Validates speaker tag generation (`<v SPEAKER_01>`, `<v SPEAKER_02>`).
- **Translation Tracks:** Verifies valid WebVTT/SRT outputs for English and Hindi.
- **QC Scoring & Queue:** Verifies 0–100 score bounds, issue categorization, and review queue ordering.

---

## 6. API Reference

### Process Video
`POST http://localhost:8081/api/process`

**Request Body:**
- `multipart/form-data` with a `video` or `file` field containing the video file.
- Or raw binary stream with `Content-Type: video/mp4`.

**Response (JSON):**
```json
{
  "status": "success",
  "vtt_bengali": "WEBVTT\n\n00:00:20.309 --> 00:00:21.989\n<v SPEAKER_02>ভীষণ মায়ার এই শহর</v>\n...",
  "vtt_english": "WEBVTT\n\n00:00:20.309 --> 00:00:21.989\n<v SPEAKER_02>This city of great affection</v>\n...",
  "vtt_hindi": "WEBVTT\n\n00:00:20.309 --> 00:00:21.989\n<v SPEAKER_02>बहुत स्नेह का यह शहर</v>\n...",
  "srt_bengali": "1\n00:00:20,309 --> 00:00:21,989\nভীষণ মায়ার এই শহর\n...",
  "qc_report": {
    "overall_score": 92.4,
    "metrics": {
      "asr_quality_score": 95.0,
      "timing_cps_score": 98.2,
      "translation_score": 91.0,
      "diarization_score": 88.5,
      "non_speech_score": 90.0,
      "coverage_score": 95.0
    },
    "ranked_issues": [
      {
        "severity": "medium",
        "category": "cps_exceeded",
        "timestamp_start": 41.58,
        "timestamp_end": 43.08,
        "message": "Cue reading speed 21.2 CPS exceeds recommended threshold"
      }
    ]
  },
  "downloads": {
    "bengali_vtt": "/api/download?file=bengali_captions.vtt",
    "bengali_srt": "/api/download?file=bengali_captions.srt",
    "english_vtt": "/api/download?file=en_captions.vtt",
    "english_srt": "/api/download?file=en_captions.srt",
    "hindi_vtt": "/api/download?file=hi_captions.vtt",
    "hindi_srt": "/api/download?file=hi_captions.srt"
  }
}
```

### Download Deliverable
`GET http://localhost:8081/api/download?file=<filename>`
- Allowed filenames: `bengali_captions.vtt`, `bengali_captions.srt`, `en_captions.vtt`, `en_captions.srt`, `hi_captions.vtt`, `hi_captions.srt`.

---

## 7. Engineering Tradeoffs & Known Limitations

- **Reference-Free Evaluation (No Ground Truth Transcripts):** Official Word Error Rate (WER) cannot be mathematically computed without human ground-truth benchmark transcripts for the source episodes. Our QC engine uses multi-factor acoustic, phonetic, and language model heuristics to assess confidence objectively.
- **External Translation Quotas:** Under extreme concurrent load, third-party translation endpoints may throttle requests. The pipeline handles this gracefully via client pool rotation and fallback tags rather than failing the entire subtitle run.
- **Complex Overlapping Speech:** In scenes where three or more actors speak simultaneously over loud musical score, unsupervised 2-means clustering will partition speakers by dominant energy, which may group peripheral voices into the nearest dominant speaker cluster.

---

## 8. License
Developed for the **Hoichoi AI Builders Hackathon 2026**.
