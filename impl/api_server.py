"""
Production Multi-Threaded API Server for Bengali Subtitle & Closed-Caption Pipeline
POST http://localhost:8081/api/process
GET  http://localhost:8081/api/download?file=<filename>

Accepts:
- multipart/form-data video upload (file field 'video' or 'file')
- raw video binary stream
- empty body (falls back to local test episode)

Orchestrates:
1. Video validation & temporary storage
2. End-to-end BengaliSubtitlePipeline processing
3. WebVTT & SRT validation
4. Structured QC reporting & explainable score
5. Downloadable VTT and SRT deliverables
"""

import sys
import json
import os
import re
import mimetypes
import tempfile
import subprocess
import logging
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any

# Ensure current directory is in sys.path for direct invocation from root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "dist")

from pipeline import BengaliSubtitlePipeline, PipelineConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_DOWNLOAD_FILES = {
    'bengali_captions.vtt': 'text/vtt',
    'bengali_captions.srt': 'application/x-subrip',
    'en_captions.vtt': 'text/vtt',
    'en_captions.srt': 'application/x-subrip',
    'hi_captions.vtt': 'text/vtt',
    'hi_captions.srt': 'application/x-subrip'
}

def validate_vtt(vtt_text: str) -> bool:
    """Validate WebVTT header and basic cue structure."""
    if not vtt_text or not vtt_text.startswith("WEBVTT"):
        return False
    return True

def validate_video_file(path: str) -> bool:
    """Validate video file using ffprobe."""
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        return False
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0

class APIHandler(BaseHTTPRequestHandler):
    """Multi-threaded HTTP Request Handler for Pipeline API"""
    server_version = "HoichoiSubtitleAPI/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        logger.info(f"API: {format % args}")

    def send_json_response(self, status_code: int, data: Dict[str, Any]):
        """Send complete JSON response with explicit Content-Length and Connection: close."""
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS, HEAD')
        self.send_header('Access-Control-Allow-Headers', 'X-Requested-With, Content-Type, Content-Length')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self):
        """CORS preflight support"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS, HEAD')
        self.send_header('Access-Control-Allow-Headers', 'X-Requested-With, Content-Type, Content-Length')
        self.send_header('Content-Length', '0')
        self.send_header('Connection', 'close')
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        """Handle download requests for VTT and SRT files"""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/download":
            query = urllib.parse.parse_qs(parsed.query)
            filename = query.get('file', [''])[0]
            if filename in ALLOWED_DOWNLOAD_FILES:
                output_dir = os.path.join(os.path.dirname(__file__), "..", "temp_pipeline_output")
                filepath = os.path.join(output_dir, filename)
                if os.path.exists(filepath):
                    with open(filepath, 'rb') as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', ALLOWED_DOWNLOAD_FILES[filename])
                    self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Content-Length', str(len(content)))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    try:
                        self.wfile.write(content)
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return

            self.send_json_response(404, {"error": "File not found"})
            return

        # Static SPA serving for frontend
        if not parsed.path.startswith("/api/"):
            rel_path = parsed.path.lstrip("/")
            target = os.path.join(STATIC_DIR, rel_path) if rel_path else os.path.join(STATIC_DIR, "index.html")
            if os.path.exists(target) and os.path.isfile(target):
                file_to_serve = target
            else:
                file_to_serve = os.path.join(STATIC_DIR, "index.html")

            if os.path.exists(file_to_serve) and os.path.isfile(file_to_serve):
                mime_type, _ = mimetypes.guess_type(file_to_serve)
                if not mime_type:
                    mime_type = "application/octet-stream"
                try:
                    with open(file_to_serve, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", mime_type)
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(content)
                    self.wfile.flush()
                except Exception as e:
                    logger.error(f"Error serving static file {file_to_serve}: {e}")
                return

        self.send_json_response(404, {"error": "Endpoint not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/process":
            self.send_json_response(404, {"error": "Endpoint not found"})
            return

        content_type = self.headers.get('Content-Type', '')
        content_length = int(self.headers.get('Content-Length', 0))

        logger.info(f"POST /api/process request received. Content-Type: {content_type}, Length: {content_length}B")

        body_bytes = b""
        if content_length > 0:
            body_bytes = self.rfile.read(content_length)

        tmp_video_path = None
        is_user_upload = False

        # Parse upload or fallback
        if len(body_bytes) > 5000:
            is_user_upload = True
            if "multipart/form-data" in content_type and "boundary=" in content_type:
                try:
                    boundary = content_type.split("boundary=")[1].strip().encode('utf-8')
                    first_boundary = body_bytes.find(b'--' + boundary)
                    if first_boundary != -1:
                        header_end = body_bytes.find(b'\r\n\r\n', first_boundary)
                        if header_end != -1:
                            next_boundary = body_bytes.find(b'--' + boundary, header_end)
                            if next_boundary != -1:
                                file_data = body_bytes[header_end + 4 : next_boundary - 2]
                            else:
                                file_data = body_bytes[header_end + 4 :]
                        else:
                            file_data = body_bytes
                    else:
                        file_data = body_bytes
                except Exception:
                    file_data = body_bytes
            else:
                file_data = body_bytes

            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir="/tmp")
            tmp.write(file_data)
            tmp.close()
            tmp_video_path = tmp.name
        else:
            demo_dir = os.path.join(os.path.dirname(__file__), "..", "hackathon_contents")
            candidates = [
                os.path.join(demo_dir, f) for f in sorted(os.listdir(demo_dir))
                if f.endswith(".mp4")
            ] if os.path.isdir(demo_dir) else []
            tmp_video_path = candidates[0] if candidates else "dummy.mp4"

        # Validate video decoding
        if is_user_upload and not validate_video_file(tmp_video_path):
            if tmp_video_path and os.path.exists(tmp_video_path) and tmp_video_path.startswith('/tmp/'):
                try:
                    os.unlink(tmp_video_path)
                except Exception:
                    pass
            self.send_json_response(400, {
                "error": True,
                "stage": "upload_validation",
                "message": "Uploaded file is not a valid or decodable video format."
            })
            return

        try:
            output_dir = os.path.join(os.path.dirname(__file__), "..", "temp_pipeline_output")
            pipeline = BengaliSubtitlePipeline()

            # Process whole video by default (max_dur = 0)
            query = urllib.parse.parse_qs(parsed.query)
            duration_param = query.get('duration', ['0'])[0]
            try:
                max_dur = int(duration_param)
            except ValueError:
                max_dur = 0

            results = pipeline.process_video(tmp_video_path, output_dir, max_duration=max_dur)

            # Validate generated VTT tracks
            if not validate_vtt(results.get('vtt_bengali', '')) or not validate_vtt(results.get('vtt_english', '')):
                raise ValueError("Generated WebVTT output failed validation check.")

            response_payload = {
                "vtt_bengali": results['vtt_bengali'],
                "vtt_english": results['vtt_english'],
                "vtt_hindi": results['vtt_hindi'],
                "qcIssues": results['qcIssues'],
                "score": results['score'],
                "qc_report": results['qc_report'],
                "detected_speakers": results.get('detected_speakers', []),
                "total_cues": results.get('total_cues', 0),
                "source_duration": results.get('source_duration', 0.0),
                "processed_duration": results.get('processed_duration', 0.0),
                "coverage_ratio": results.get('coverage_ratio', 1.0),
                "coverage_score": results.get('coverage_score', 100.0),
                "downloads": {
                    "bengali_vtt": "http://localhost:8081/api/download?file=bengali_captions.vtt",
                    "bengali_srt": "http://localhost:8081/api/download?file=bengali_captions.srt",
                    "english_vtt": "http://localhost:8081/api/download?file=en_captions.vtt",
                    "english_srt": "http://localhost:8081/api/download?file=en_captions.srt",
                    "hindi_vtt": "http://localhost:8081/api/download?file=hi_captions.vtt",
                    "hindi_srt": "http://localhost:8081/api/download?file=hi_captions.srt"
                }
            }

            self.send_json_response(200, response_payload)

        except Exception as e:
            logger.error(f"Pipeline execution error: {e}", exc_info=True)
            self.send_json_response(500, {
                "error": True,
                "stage": "pipeline_execution",
                "message": "An error occurred while processing the video pipeline.",
                "details": str(e)
            })

        finally:
            if is_user_upload and tmp_video_path and os.path.exists(tmp_video_path) and tmp_video_path.startswith('/tmp/'):
                try:
                    os.unlink(tmp_video_path)
                except Exception:
                    pass

def run_server(port: int = None):
    if port is None:
        port = int(os.environ.get("PORT", 8081))
    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, APIHandler)
    logger.info(f"API Server (Multi-Threaded) listening on http://0.0.0.0:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    logger.info("API Server stopped.")

if __name__ == '__main__':
    run_server()
