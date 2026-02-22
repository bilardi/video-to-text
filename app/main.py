"""FastAPI application exposing the transcription endpoints and the single-page UI."""

import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import HTMLResponse
from .transcribe_service import TranscribeService

app = FastAPI()
transcribe_service = TranscribeService()


@app.get("/")
async def get_index() -> HTMLResponse:
    """Serve the index.html single-page UI."""
    with open("/code/app/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.post("/upload")
async def upload_video(file: UploadFile = File(...)) -> dict:
    """Save the uploaded video file to /tmp and return its server-side path."""
    # Save uploaded file to a temp path
    tmp_path = f"/tmp/{file.filename}"
    with open(tmp_path, "wb") as f:
        f.write(await file.read())
    return {"path": tmp_path}


@app.websocket("/ws/transcribe")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Accept raw PCM binary chunks over WebSocket and stream them to Amazon Transcribe."""
    await websocket.accept()
    print("New streaming connection established", flush=True)

    audio_queue = asyncio.Queue()

    async def audio_producer():
        try:
            while True:
                # Receive binary chunk from FFmpeg or Browser
                data = await websocket.receive_bytes()
                await audio_queue.put(data)
        except WebSocketDisconnect:
            print("Client disconnected", flush=True)
            await audio_queue.put(None)
        except Exception as e:
            print(f"Receiver error: {e}", flush=True)
            await audio_queue.put(None)

    async def stream_generator():
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                break
            yield chunk

    async def send_to_client(text: str):
        # Print transcription in real-time to the console
        print(f"AWS Transcribe: {text}", flush=True)
        # Send back to the client via WebSocket
        await websocket.send_text(text)

    # Launch audio receiver in the background
    producer_task = asyncio.create_task(audio_producer())

    try:
        # Connect the generator to Amazon Transcribe Service
        await transcribe_service.start_transcription(stream_generator(), send_to_client)
    finally:
        await producer_task


@app.websocket("/ws/transcribe/file")
async def websocket_transcribe_file(websocket: WebSocket) -> None:
    """Accept a server-side file path over WebSocket, convert it to PCM via ffmpeg,
    and stream it to Amazon Transcribe."""
    await websocket.accept()
    print("New file transcription connection", flush=True)

    # Receive the file path from client
    video_path = await websocket.receive_text()
    print(f"Transcribing file: {video_path}", flush=True)

    audio_queue = asyncio.Queue()

    async def ffmpeg_producer():
        # Convert video to PCM 16bit 16kHz mono via ffmpeg
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-re",
            "-i",
            video_path,
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            await audio_queue.put(chunk)
        await audio_queue.put(None)

    async def stream_generator():
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                break
            yield chunk

    async def send_to_client(text: str):
        print(f"AWS Transcribe: {text}", flush=True)
        await websocket.send_text(text)

    producer_task = asyncio.create_task(ffmpeg_producer())

    try:
        await transcribe_service.start_transcription(stream_generator(), send_to_client)
    finally:
        await producer_task
