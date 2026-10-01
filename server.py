#!/usr/bin/env python3
"""Local-only editor server: media ingest, Qwen voice cloning, FFmpeg export."""
import base64
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from workflow import download_h3, edit_plan, h3_status, start_h3

ROOT = Path(__file__).resolve().parent
WORK = Path(os.environ.get("TD_EDITOR_WORK", ROOT / ".work"))
WORK.mkdir(exist_ok=True)
TOKEN_FILE = Path(os.environ.get("QWEN3_TTS_TOKEN_FILE", str(Path.home() / ".config/qwen3-tts-lan-api/api-token")))
TTS_URL = os.environ.get("QWEN3_TTS_URL", "http://127.0.0.1:18791/v1/services/base-local3060/audio/speech")
PORT = int(os.environ.get("TD_EDITOR_PORT", "18792"))
MAX_UPLOAD = 2 * 1024**3


def media_path(media_id):
    if not isinstance(media_id, str) or not media_id.isalnum():
        raise ValueError("잘못된 미디어 ID")
    matches = list(WORK.glob(media_id + ".*"))
    if len(matches) != 1:
        raise ValueError("미디어를 찾을 수 없습니다")
    return matches[0]


def probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return float(json.loads(result.stdout)["format"]["duration"])


def has_audio(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return bool(result.stdout.strip())


def run(args):
    subprocess.run(args, check=True, capture_output=True, text=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            body = (ROOT / "index.html").read_bytes()
            kind = "text/html; charset=utf-8"
        elif self.path == "/style.css":
            body = (ROOT / "style.css").read_bytes()
            kind = "text/css; charset=utf-8"
        elif self.path == "/editor.js":
            body = (ROOT / "editor.js").read_bytes()
            kind = "text/javascript; charset=utf-8"
        elif self.path == "/simple.js":
            body = (ROOT / "simple.js").read_bytes()
            kind = "text/javascript; charset=utf-8"
        elif self.path == "/simple.css":
            body = (ROOT / "simple.css").read_bytes()
            kind = "text/css; charset=utf-8"
        elif self.path == "/advanced":
            body = (ROOT / "advanced.html").read_bytes()
            kind = "text/html; charset=utf-8"
        elif self.path.startswith("/media/"):
            try:
                path = media_path(self.path.removeprefix("/media/"))
                kind = "video/mp4" if path.suffix == ".mp4" else "audio/wav"
            except ValueError as exc:
                return self.reply(404, {"error": str(exc)})
            size = path.stat().st_size
            byte_range = self.headers.get("Range")
            if byte_range:
                try:
                    start_text, end_text = byte_range.removeprefix("bytes=").split("-", 1)
                    start = int(start_text)
                    end = min(size - 1, int(end_text) if end_text else size - 1)
                    if start < 0 or end < start or start >= size:
                        raise ValueError("invalid range")
                except ValueError:
                    return self.reply(416, {"error": "invalid range"})
            else:
                start, end = 0, size - 1
            self.send_response(206 if byte_range else 200)
            self.send_header("Content-Type", kind)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if byte_range:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as source:
                source.seek(start)
                left = end - start + 1
                while left:
                    chunk = source.read(min(left, 1024 * 1024))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            return
        else:
            return self.reply(404, {"error": "not_found"})
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > MAX_UPLOAD:
                raise ValueError("요청 크기가 올바르지 않습니다")
            if self.path == "/api/upload":
                suffix = ".mp4"
                media_id = uuid.uuid4().hex
                path = WORK / (media_id + suffix)
                with path.open("wb") as out:
                    left = size
                    while left:
                        chunk = self.rfile.read(min(left, 1024 * 1024))
                        if not chunk:
                            raise ValueError("업로드가 중단되었습니다")
                        out.write(chunk)
                        left -= len(chunk)
                try:
                    duration = probe(path)
                except Exception:
                    path.unlink(missing_ok=True)
                    raise ValueError("읽을 수 있는 영상이 아닙니다")
                return self.reply(200, {"id": media_id, "duration": duration, "url": "/media/" + media_id})
            payload = json.loads(self.rfile.read(size))
            if self.path == "/api/tts":
                return self.tts(payload)
            if self.path == "/api/h3/generate":
                task_id = start_h3(str(payload.get("key", "")), str(payload.get("prompt", "")), payload.get("image"), payload.get("duration"))
                return self.reply(200, {"taskId": task_id})
            if self.path == "/api/h3/status":
                result = h3_status(str(payload.get("key", "")), str(payload.get("taskId", "")))
                if result["status"] == "succeeded":
                    media_id = uuid.uuid4().hex
                    path = WORK / (media_id + ".mp4")
                    try:
                        download_h3(result["url"], path)
                        duration = probe(path)
                    except Exception:
                        path.unlink(missing_ok=True)
                        raise
                    result["clip"] = {"id": media_id, "url": "/media/" + media_id, "duration": duration}
                return self.reply(200, result)
            if self.path == "/api/ai/edit":
                plan = edit_plan(str(payload.get("key", "")), str(payload.get("instruction", "")), payload.get("clips", []), media_path)
                return self.reply(200, plan)
            if self.path == "/api/export":
                return self.export(payload)
            self.reply(404, {"error": "not_found"})
        except (ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError, urllib.error.URLError, TimeoutError) as exc:
            detail = exc.stderr[-500:] if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
            self.reply(400, {"error": detail})

    def tts(self, data):
        text = str(data["text"]).strip()
        ref_text = str(data["refText"]).strip()
        start, end = float(data["refStart"]), float(data["refEnd"])
        source = media_path(data["refId"])
        if not text or not ref_text or start < 0 or end - start < 1 or end - start > 30 or end > probe(source):
            raise ValueError("참조 음성 1~30초와 해당 구간의 대본을 입력하세요")
        with tempfile.TemporaryDirectory(dir=WORK) as temp:
            wav = Path(temp) / "reference.wav"
            run(["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(end-start), "-vn", "-ac", "1", "-ar", "24000", str(wav)])
            request = urllib.request.Request(TTS_URL, data=json.dumps({"input": text, "language": "Korean", "ref_audio": "data:audio/wav;base64," + base64.b64encode(wav.read_bytes()).decode(), "ref_text": ref_text, "response_format": "wav"}, ensure_ascii=False).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN_FILE.read_text().strip()}, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=900) as response:
                    audio = response.read()
            except urllib.error.HTTPError as exc:
                raise ValueError("TTS 요청 실패: " + exc.read().decode(errors="replace")[:300]) from exc
        if audio[:4] != b"RIFF":
            raise ValueError("TTS 응답이 WAV가 아닙니다")
        media_id = uuid.uuid4().hex
        path = WORK / (media_id + ".wav")
        path.write_bytes(audio)
        self.reply(200, {"id": media_id, "url": "/media/" + media_id, "duration": probe(path)})

    def export(self, data):
        clips = data["clips"]
        if not clips or len(clips) > 100:
            raise ValueError("영상 클립을 추가하세요")
        total = sum(float(item["end"] if "end" in item else item["duration"]) - float(item.get("start", 0)) for item in clips)
        if total > 3600:
            raise ValueError("최대 길이는 1시간입니다")
        export_id = uuid.uuid4().hex
        output = WORK / (export_id + ".mp4")
        args = ["ffmpeg", "-y"]
        for clip in clips:
            args += ["-i", str(media_path(clip["id"]))]
        speech = data.get("speech", [])
        for item in speech:
            args += ["-i", str(media_path(item["id"]))]
        filters = []
        offset = 0.0
        for i, clip in enumerate(clips):
            source_start = float(clip.get("start", 0))
            source_end = float(clip["end"] if "end" in clip else clip["duration"])
            duration = source_end - source_start
            if source_start < 0 or duration <= 0 or source_end > probe(media_path(clip["id"])) + 0.05:
                raise ValueError("영상 자르기 범위가 잘못되었습니다")
            filters.append(f"[{i}:v]trim=start={source_start}:end={source_end},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}]")
            mutes = []
            for interval in data.get("mutes", []):
                a = max(0, float(interval["start"]) - offset)
                b = min(duration, float(interval["end"]) - offset)
                if b > a:
                    mutes.append(f"volume=enable='between(t,{a},{b})':volume=0")
            audio_filters = ",".join(mutes)
            if has_audio(media_path(clip["id"])):
                filters.append(f"[{i}:a]atrim=start={source_start}:end={source_end},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo{',' + audio_filters if audio_filters else ''}[a{i}]")
            else:
                filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration},asetpts=PTS-STARTPTS[a{i}]")
            offset += duration
        filters.append("".join(f"[v{i}][a{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=1[v][base]")
        audio_inputs = "[base]"
        for j, item in enumerate(speech):
            start = float(item["start"])
            if start < 0 or start >= total:
                raise ValueError("TTS 시작 위치가 영상 밖입니다")
            filters.append(f"[{len(clips)+j}:a]atrim=duration={total-start},adelay={int(start*1000)}|{int(start*1000)},aresample=48000,aformat=channel_layouts=stereo[s{j}]")
            audio_inputs += f"[s{j}]"
        if speech:
            filters.append(audio_inputs + f"amix=inputs={len(speech)+1}:duration=first:normalize=0[aout]")
        args += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[aout]" if speech else "[base]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-movflags", "+faststart", str(output)]
        run(args)
        self.reply(200, {"url": "/media/" + export_id})


if __name__ == "__main__":
    print(f"Editor: http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
