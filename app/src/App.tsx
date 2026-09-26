import { useState, useRef, useEffect } from 'react';
import { Play, Pause, Upload, CheckCircle, Download, Music, ShieldAlert, Video } from 'lucide-react';

export default function App() {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const activeLineRef = useRef<HTMLDivElement>(null);

  const [processing, setProcessing] = useState(false);
  const [processingStage, setProcessingStage] = useState<string>('');
  const [lang, setLang] = useState<'bengali' | 'english' | 'hindi'>('bengali');

  const [vttData, setVttData] = useState<{ bengali: string; english: string; hindi: string } | null>(null);
  const [qcIssues, setQcIssues] = useState<any[]>([]);
  const [score, setScore] = useState<number | null>(null);
  const [qcReport, setQcReport] = useState<any>(null);
  const [detectedSpeakers, setDetectedSpeakers] = useState<string[]>([]);
  const [downloads, setDownloads] = useState<Record<string, string>>({});

  const [captions, setCaptions] = useState<any[]>([]);
  const [currentTime, setCurrentTime] = useState(0);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setVideoFile(file);
      setVideoUrl(URL.createObjectURL(file));
      setVttData(null);
      setQcIssues([]);
      setScore(null);
      setQcReport(null);
      setDetectedSpeakers([]);
      setDownloads({});
      setCaptions([]);
    }
  };

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) videoRef.current.pause();
      else videoRef.current.play();
    }
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onTime = () => setCurrentTime(video.currentTime);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);

    video.addEventListener('timeupdate', onTime);
    video.addEventListener('play', onPlay);
    video.addEventListener('pause', onPause);

    return () => {
      video.removeEventListener('timeupdate', onTime);
      video.removeEventListener('play', onPlay);
      video.removeEventListener('pause', onPause);
    };
  }, [videoUrl]);

  // Auto-scroll active cue into view
  useEffect(() => {
    if (activeLineRef.current && transcriptRef.current) {
      activeLineRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [currentTime]);

  // Parse VTT and rebuild captions array on language or VTT change
  useEffect(() => {
    if (!vttData) return;
    const vttStr = vttData[lang];
    if (!vttStr) return;

    const parseTime = (t: string) => {
      const p = t.trim().split(':');
      if (p.length === 3) {
        return parseFloat(p[0]) * 3600 + parseFloat(p[1]) * 60 + parseFloat(p[2]);
      }
      return parseFloat(p[0]) * 60 + parseFloat(p[1]);
    };

    const parsed = vttStr
      .trim()
      .split(/\r?\n\r?\n/)
      .slice(1)
      .map((block: string) => {
        const lines = block.split(/\r?\n/);
        if (lines.length < 2) return null;
        const timeRange = lines[0].split(' --> ');
        if (timeRange.length !== 2) return null;

        let speaker = 'SPEAKER';
        let text = lines.slice(1).join(' ').trim();

        const vMatch = text.match(/^<v ([^>]+)>(.*?)<\/v>$/s);
        if (vMatch) {
          speaker = vMatch[1];
          text = vMatch[2].trim();
        }

        if (!text) return null;
        return {
          startTime: parseTime(timeRange[0]),
          endTime: parseTime(timeRange[1]),
          startStr: timeRange[0].trim().replace(/^00:/, ''),
          endStr: timeRange[1].trim().replace(/^00:/, ''),
          speaker,
          text,
        };
      })
      .filter(Boolean);

    setCaptions(parsed);
  }, [lang, vttData]);

  const processVideo = async () => {
    setProcessing(true);
    setProcessingStage('Uploading video & extracting audio...');

    try {
      const formData = new FormData();
      if (videoFile) {
        formData.append('video', videoFile);
      }

      setProcessingStage('Classifying audio, running Bengali ASR & Diarization...');
      const res = await fetch('/api/process', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.message || `Server returned ${res.status}`);
      }

      setProcessingStage('Translating subtitles & running semantic QC...');
      const data = await res.json();

      setVttData({
        bengali: data.vtt_bengali,
        english: data.vtt_english,
        hindi: data.vtt_hindi,
      });
      setQcIssues(data.qcIssues || []);
      setScore(data.score ?? null);
      setQcReport(data.qc_report ?? null);
      setDetectedSpeakers(data.detected_speakers || []);
      setDownloads(data.downloads || {});
    } catch (err: any) {
      alert(`Pipeline Processing Error: ${err.message || err}`);
    } finally {
      setProcessing(false);
      setProcessingStage('');
    }
  };

  const seekTo = (timeStr: string) => {
    if (!videoRef.current) return;
    const p = timeStr.trim().split(':');
    let s = 0;
    if (p.length === 3) {
      s = parseFloat(p[0]) * 3600 + parseFloat(p[1]) * 60 + parseFloat(p[2]);
    } else if (p.length === 2) {
      s = parseFloat(p[0]) * 60 + parseFloat(p[1]);
    }
    videoRef.current.currentTime = s;
    videoRef.current.play();
  };

  const fmtTime = (s: number) => {
    const m = Math.floor(s / 60).toString().padStart(2, '0');
    const sec = (s % 60).toFixed(2).padStart(5, '0');
    return `${m}:${sec}`;
  };

  // Find currently active cue
  const activeCue = captions.find(
    (c) => currentTime >= c.startTime && currentTime <= c.endTime
  );

  return (
    <div className="h-screen bg-slate-50 text-slate-900 flex flex-col font-sans overflow-hidden">
      {/* ── Top Header ── */}
      <header className="flex-none h-16 border-b border-slate-200 bg-white flex items-center justify-between px-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-red-600 flex items-center justify-center text-white font-black text-lg shadow-sm">
            হ
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-slate-900 flex items-center gap-2">
              Hoichoi Subtitle &amp; Closed-Caption Pipeline
              <span className="px-2 py-0.5 text-[10px] font-semibold bg-red-50 text-red-700 rounded-full border border-red-200">
                Broadcast AI
              </span>
            </h1>
            <p className="text-[11px] text-slate-500">
              Bengali ASR • Speaker Diarization • Audio Events • Multi-Language • Semantic QC
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <input
              type="file"
              accept="video/*"
              onChange={handleFileUpload}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
            <button className="px-3 py-1.5 text-xs font-medium border border-slate-300 rounded-md bg-white hover:bg-slate-50 text-slate-700 flex items-center gap-1.5 shadow-sm transition-colors">
              <Upload className="w-3.5 h-3.5 text-slate-500" />
              {videoFile ? videoFile.name.substring(0, 20) : 'Choose Video'}
            </button>
          </div>

          <button
            onClick={processVideo}
            disabled={processing}
            className="px-4 py-1.5 text-xs font-semibold bg-red-600 hover:bg-red-700 text-white rounded-md shadow-sm disabled:opacity-50 transition-colors flex items-center gap-1.5"
          >
            {processing ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Processing...
              </>
            ) : (
              'Run Pipeline'
            )}
          </button>
        </div>
      </header>

      {/* ── Processing Stage Banner ── */}
      {processing && (
        <div className="bg-red-50 border-b border-red-200 px-6 py-2 flex items-center gap-2 text-xs font-medium text-red-800 animate-pulse">
          <span className="w-2 h-2 rounded-full bg-red-600 animate-ping" />
          {processingStage}
        </div>
      )}

      {/* ── Main Workspace: 2-Column Split ── */}
      <div className="flex-grow flex overflow-hidden">
        {/* ══ LEFT: Video Player + QC Report (62%) ══ */}
        <div className="flex flex-col border-r border-slate-200 bg-white" style={{ width: '62%' }}>
          {/* Video Container */}
          <div className="relative bg-black flex items-center justify-center" style={{ height: '360px' }}>
            {videoUrl ? (
              <video
                ref={videoRef}
                src={videoUrl}
                className="w-full h-full object-contain"
                crossOrigin="anonymous"
              />
            ) : (
              <div className="text-center text-slate-500 flex flex-col items-center gap-2">
                <Video className="w-10 h-10 stroke-1 text-slate-600" />
                <p className="text-xs">Select a video or click Run Pipeline to process test episode</p>
              </div>
            )}

            {/* In-Video Active Subtitle Overlay */}
            {activeCue && (
              <div className="absolute bottom-6 inset-x-8 text-center pointer-events-none">
                <span className="inline-block bg-black/85 text-white text-sm font-medium px-3.5 py-1.5 rounded shadow-lg backdrop-blur-sm max-w-xl">
                  {activeCue.speaker !== 'MUSIC' && (
                    <span className="text-amber-300 font-mono text-xs mr-2 font-bold">
                      [{activeCue.speaker}]
                    </span>
                  )}
                  {activeCue.text}
                </span>
              </div>
            )}
          </div>

          {/* Controls Bar */}
          <div className="h-12 border-t border-b border-slate-200 bg-slate-50 px-4 flex items-center gap-3">
            <button
              onClick={togglePlay}
              disabled={!videoUrl}
              className="w-8 h-8 rounded-full bg-slate-900 text-white flex items-center justify-center hover:bg-slate-700 disabled:opacity-30 shadow-sm transition-colors"
            >
              {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 ml-0.5" />}
            </button>
            <span className="font-mono text-xs text-slate-600">{fmtTime(currentTime)}</span>

            {/* Language Switcher */}
            {vttData && (
              <div className="ml-auto flex items-center gap-1.5 bg-slate-200 p-0.5 rounded-md">
                {(['bengali', 'english', 'hindi'] as const).map((l) => (
                  <button
                    key={l}
                    onClick={() => setLang(l)}
                    className={`px-3 py-1 text-xs font-semibold rounded transition-colors ${
                      lang === l
                        ? 'bg-white text-slate-900 shadow-sm'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {l === 'bengali' ? 'বাংলা' : l === 'hindi' ? 'हिन्दी' : 'English'}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* ── QC Report Panel ── */}
          <div className="flex-grow overflow-y-auto p-5 bg-white">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-slate-700" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                  Quality Control &amp; Verification
                </h2>
              </div>
              {score !== null && (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-medium text-slate-500">Quality Score:</span>
                  <span
                    className={`px-2.5 py-0.5 rounded-full font-mono text-xs font-bold ${
                      score >= 85
                        ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                        : score >= 65
                        ? 'bg-amber-100 text-amber-800 border border-amber-300'
                        : 'bg-red-100 text-red-800 border border-red-300'
                    }`}
                  >
                    {score} / 100
                  </span>
                </div>
              )}
            </div>

            {/* Score Breakdown Metrics (6 Dimensions) */}
            {qcReport && (
              <div className="py-3 border-b border-slate-100">
                <div className="grid grid-cols-6 gap-2">
                  <div className="bg-slate-50 p-2 rounded border border-slate-200">
                    <div className="text-[9px] text-slate-500 uppercase font-semibold">ASR Accuracy</div>
                    <div className="text-xs font-bold text-slate-800 font-mono">{qcReport.asr_score}%</div>
                  </div>
                  <div className="bg-slate-50 p-2 rounded border border-slate-200">
                    <div className="text-[9px] text-slate-500 uppercase font-semibold">Timing / CPS</div>
                    <div className="text-xs font-bold text-slate-800 font-mono">{qcReport.timing_score}%</div>
                  </div>
                  <div className="bg-slate-50 p-2 rounded border border-slate-200">
                    <div className="text-[9px] text-slate-500 uppercase font-semibold">Translation</div>
                    <div className="text-xs font-bold text-slate-800 font-mono">{qcReport.translation_score}%</div>
                  </div>
                  <div className="bg-slate-50 p-2 rounded border border-slate-200">
                    <div className="text-[9px] text-slate-500 uppercase font-semibold">Diarization</div>
                    <div className="text-xs font-bold text-slate-800 font-mono">{qcReport.diarization_score}%</div>
                  </div>
                  <div className="bg-slate-50 p-2 rounded border border-slate-200">
                    <div className="text-[9px] text-slate-500 uppercase font-semibold">Non-Speech</div>
                    <div className="text-xs font-bold text-slate-800 font-mono">{qcReport.non_speech_score}%</div>
                  </div>
                  <div className="bg-slate-50 p-2 rounded border border-slate-200">
                    <div className="text-[9px] text-slate-500 uppercase font-semibold">Coverage</div>
                    <div className="text-xs font-bold text-slate-800 font-mono">{qcReport.coverage_score ?? 100}%</div>
                  </div>
                </div>

                {qcReport.source_duration > 0 && (
                  <div className="mt-2 text-[10px] text-slate-500 flex items-center justify-between font-mono bg-slate-50 px-2 py-1 rounded border border-slate-200">
                    <span>Source Duration: {Math.floor(qcReport.source_duration / 60)}m {Math.floor(qcReport.source_duration % 60)}s</span>
                    <span>Processed: {Math.floor(qcReport.processed_duration / 60)}m {Math.floor(qcReport.processed_duration % 60)}s</span>
                    <span className="font-bold text-emerald-700">Coverage: {Math.round(qcReport.coverage_ratio * 100)}%</span>
                  </div>
                )}
              </div>
            )}

            {/* Speaker Information */}
            {detectedSpeakers.length > 0 && (
              <div className="py-2.5 border-b border-slate-100 flex items-center gap-2">
                <span className="text-[11px] font-semibold text-slate-500">Attributed Speakers:</span>
                <div className="flex gap-1.5">
                  {detectedSpeakers.map((spk) => (
                    <span
                      key={spk}
                      className="px-2 py-0.5 text-[10px] font-mono font-bold bg-indigo-50 text-indigo-700 rounded border border-indigo-200"
                    >
                      {spk}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Deliverable Downloads Bar */}
            {Object.keys(downloads).length > 0 && (
              <div className="py-3 border-b border-slate-200">
                <div className="text-[11px] font-semibold text-slate-600 mb-1.5 flex items-center gap-1.5">
                  <Download className="w-3.5 h-3.5" /> Subtitle Deliverables (WebVTT &amp; SRT):
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="flex gap-1">
                    <a
                      href={downloads.bengali_vtt}
                      download="bengali_captions.vtt"
                      className="flex-1 text-center py-1 text-[10px] font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded border border-slate-300"
                    >
                      বাংলা VTT
                    </a>
                    <a
                      href={downloads.bengali_srt}
                      download="bengali_captions.srt"
                      className="flex-1 text-center py-1 text-[10px] font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded border border-slate-300"
                    >
                      বাংলা SRT
                    </a>
                  </div>
                  <div className="flex gap-1">
                    <a
                      href={downloads.english_vtt}
                      download="en_captions.vtt"
                      className="flex-1 text-center py-1 text-[10px] font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded border border-slate-300"
                    >
                      EN VTT
                    </a>
                    <a
                      href={downloads.english_srt}
                      download="en_captions.srt"
                      className="flex-1 text-center py-1 text-[10px] font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded border border-slate-300"
                    >
                      EN SRT
                    </a>
                  </div>
                  <div className="flex gap-1">
                    <a
                      href={downloads.hindi_vtt}
                      download="hi_captions.vtt"
                      className="flex-1 text-center py-1 text-[10px] font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded border border-slate-300"
                    >
                      हिन्दी VTT
                    </a>
                    <a
                      href={downloads.hindi_srt}
                      download="hi_captions.srt"
                      className="flex-1 text-center py-1 text-[10px] font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded border border-slate-300"
                    >
                      हिन्दी SRT
                    </a>
                  </div>
                </div>
              </div>
            )}

            {/* Ranked Review Queue */}
            <div className="mt-3">
              <div className="text-xs font-bold text-slate-700 uppercase mb-2">
                Ranked Review Queue ({qcIssues.length} items)
              </div>

              {vttData && qcIssues.length === 0 && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-md text-emerald-800 text-xs flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 text-emerald-600" />
                  All broadcast timing and language verification checks passed with zero errors.
                </div>
              )}

              <div className="space-y-2">
                {qcIssues.map((issue, idx) => (
                  <div
                    key={idx}
                    onClick={() => seekTo(issue.time)}
                    className="p-3 bg-slate-50 border border-slate-200 hover:border-slate-400 rounded-md cursor-pointer transition-colors shadow-xs"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-[11px] font-bold text-slate-700">
                        {idx + 1}. {issue.time}
                      </span>
                      <span
                        className={`text-[9px] uppercase font-bold px-2 py-0.5 rounded-full ${
                          issue.severity === 'critical'
                            ? 'bg-rose-100 text-rose-800 border border-rose-300'
                            : issue.severity === 'high'
                            ? 'bg-red-100 text-red-800 border border-red-300'
                            : issue.severity === 'medium'
                            ? 'bg-amber-100 text-amber-800 border border-amber-300'
                            : 'bg-slate-200 text-slate-700'
                        }`}
                      >
                        {issue.severity} • {issue.type}
                      </span>
                    </div>
                    <div className="text-xs font-semibold text-slate-900 mb-0.5">{issue.description}</div>
                    <div className="text-[11px] text-slate-500 font-mono mb-1">{issue.evidence}</div>
                    <div className="text-[10px] text-indigo-700 font-medium">
                      Action: {issue.suggested_action}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ══ RIGHT: Live Transcript Timeline (38%) ══ */}
        <div className="flex flex-col bg-slate-100" style={{ width: '38%' }}>
          <div className="h-12 border-b border-slate-200 bg-white px-5 flex items-center justify-between shadow-xs">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-700">
              Live Transcript Timeline
            </h2>
            {vttData && (
              <span className="text-[10px] font-mono text-slate-500 uppercase font-semibold">
                {lang === 'bengali' ? 'বাংলা' : lang === 'hindi' ? 'हिन्दी' : 'English'}
              </span>
            )}
          </div>

          <div ref={transcriptRef} className="flex-grow overflow-y-auto p-4 space-y-2">
            {captions.map((cue, idx) => {
              const isActive = currentTime >= cue.startTime && currentTime <= cue.endTime;
              const isMusic = cue.speaker === 'MUSIC' || cue.text.includes('[MUSIC]');

              return (
                <div
                  key={idx}
                  ref={isActive ? activeLineRef : undefined}
                  onClick={() => seekTo(cue.startStr)}
                  className={`p-3 rounded-lg border transition-all cursor-pointer ${
                    isActive
                      ? 'bg-white border-red-500 shadow-md ring-2 ring-red-100'
                      : 'bg-white/80 border-slate-200 hover:bg-white hover:border-slate-300 shadow-xs'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-mono text-[10px] text-slate-400 font-medium">
                      {cue.startStr} - {cue.endStr}
                    </span>

                    {isMusic ? (
                      <span className="flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                        <Music className="w-3 h-3" /> MUSIC
                      </span>
                    ) : (
                      <span
                        className={`text-[10px] font-bold font-mono px-2 py-0.5 rounded ${
                          cue.speaker === 'SPEAKER_01'
                            ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        }`}
                      >
                        {cue.speaker}
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-slate-800 font-medium leading-relaxed">
                    {cue.text}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
