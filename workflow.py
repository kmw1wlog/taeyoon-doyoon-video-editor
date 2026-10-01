"""MiniMax H3 generation and OpenAI edit-plan adapters for the local editor."""
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

MINIMAX_BASE = os.environ.get("MINIMAX_API_BASE", "https://api.minimax.io").rstrip("/")
OPENAI_MODEL = os.environ.get("OPENAI_EDIT_MODEL", "gpt-5")


def request_json(url, key, payload=None):
    headers = {"Authorization": f"Bearer {key}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None, headers=headers, method="POST" if payload is not None else "GET")
    cooldown = 3
    for attempt in range(8):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            message = error.read().decode(errors="replace")[:500]
            if error.code not in (429, 503) or attempt == 7:
                raise ValueError(f"API 오류 {error.code}: {message}") from error
            retry_after = error.headers.get("Retry-After", "")
            delay = min(120, int(retry_after) if retry_after.isdigit() else cooldown)
            time.sleep(delay)
            cooldown = min(60, cooldown * 2)


def start_h3(key, prompt, image, duration):
    if not key or not prompt.strip():
        raise ValueError("MiniMax API 키와 H3 프롬프트를 입력하세요")
    if not isinstance(duration, int) or not 4 <= duration <= 15:
        raise ValueError("H3 길이는 4~15초입니다")
    if not isinstance(image, str) or not image.startswith(("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,")) or len(image) > 42_000_000:
        raise ValueError("30MB 이하의 JPG, PNG, WEBP 시작 사진을 넣으세요")
    payload = {"model": "MiniMax-H3", "content": [{"type": "text", "text": prompt.strip()}, {"type": "image_url", "image_url": {"url": image}, "role": "first_frame"}], "resolution": "768P", "duration": duration, "ratio": "adaptive"}
    result = request_json(MINIMAX_BASE + "/v2/video_generation", key, payload)
    task_id = str(result.get("task_id", ""))
    if not task_id:
        raise ValueError("MiniMax가 작업 ID를 반환하지 않았습니다")
    return task_id


def h3_status(key, task_id):
    if not key or not task_id.isdigit():
        raise ValueError("API 키 또는 작업 ID가 올바르지 않습니다")
    result = request_json(MINIMAX_BASE + "/v2/query/video_generation/" + task_id, key)
    task = result.get("task") or {}
    return {"status": task.get("status", "unknown"), "url": (task.get("content") or {}).get("url"), "error": (task.get("error") or {}).get("message", "")}


def download_h3(url, output):
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("MiniMax 결과 주소가 올바르지 않습니다")
    request = urllib.request.Request(url, headers={"User-Agent": "TaeyoonDoyoonEditor/1.0"})
    cooldown = 3
    for attempt in range(8):
        try:
            with urllib.request.urlopen(request, timeout=180) as response, output.open("wb") as target:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        return
                    target.write(chunk)
                    if target.tell() > 2 * 1024**3:
                        raise ValueError("결과 영상 크기 제한 초과")
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503) or attempt == 7:
                raise
            retry_after = error.headers.get("Retry-After", "")
            time.sleep(min(120, int(retry_after) if retry_after.isdigit() else cooldown))
            cooldown = min(60, cooldown * 2)


def frame_data_uri(path):
    frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(path), "-frames:v", "1", "-vf", "scale=640:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-"], capture_output=True, check=True).stdout
    return "data:image/jpeg;base64," + base64.b64encode(frame).decode()


def edit_plan(key, instruction, clips, media_path):
    if not key or not instruction.strip() or not clips or len(clips) > 30:
        raise ValueError("OpenAI API 키, 편집 지시와 완성 영상을 확인하세요")
    content = [{"type": "input_text", "text": "아래 클립으로 실제 영상 편집안을 만드세요. 가능한 작업: 클립 순서 변경, 클립 앞뒤 자르기, 결과물의 특정 시간대 원본 음성 음소거. 영상에 실제로 없는 내용은 가정하지 마세요. 음성을 들을 수 없으므로 대사 내용은 프롬프트와 사용자 지시만 근거로 판단하세요. 불확실하면 해당 클립을 유지하세요. 모든 시간은 초입니다. 사용자 지시: " + instruction.strip()}]
    allowed = {}
    for clip in clips:
        path = media_path(clip["id"])
        duration = float(clip["duration"])
        allowed[clip["id"]] = duration
        content.append({"type": "input_text", "text": f"클립 ID={clip['id']}, 이름={str(clip.get('name',''))[:100]}, 길이={duration:.2f}초, 생성 프롬프트={str(clip.get('prompt',''))[:1500]}. 다음 이미지는 이 클립의 대표 프레임입니다."})
        content.append({"type": "input_image", "image_url": frame_data_uri(path), "detail": "low"})
    schema = {"type": "object", "additionalProperties": False, "properties": {"summary": {"type": "string"}, "clips": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string"}, "start": {"type": "number"}, "end": {"type": "number"}}, "required": ["id", "start", "end"]}}, "mutes": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"start": {"type": "number"}, "end": {"type": "number"}}, "required": ["start", "end"]}}}, "required": ["summary", "clips", "mutes"]}
    payload = {"model": OPENAI_MODEL, "store": False, "input": [{"role": "user", "content": content}], "text": {"format": {"type": "json_schema", "name": "video_edit_plan", "strict": True, "schema": schema}}}
    result = request_json("https://api.openai.com/v1/responses", key, payload)
    text = "".join(part.get("text", "") for item in result.get("output", []) for part in item.get("content", []) if part.get("type") == "output_text")
    if not text:
        raise ValueError("ChatGPT가 편집안을 반환하지 않았습니다")
    plan = json.loads(text)
    seen = set()
    total = 0
    for clip in plan["clips"]:
        clip_id, start, end = clip["id"], float(clip["start"]), float(clip["end"])
        if clip_id not in allowed or clip_id in seen or start < 0 or end <= start or end > allowed[clip_id] + 0.05:
            raise ValueError("편집안에 잘못된 클립 또는 구간이 있습니다")
        seen.add(clip_id)
        total += end - start
    if not seen:
        raise ValueError("편집안에 남은 영상이 없습니다")
    for mute in plan["mutes"]:
        start, end = float(mute["start"]), float(mute["end"])
        if start < 0 or end <= start or end > total + 0.05:
            raise ValueError("편집안의 음소거 시간이 영상 밖입니다")
    return plan
