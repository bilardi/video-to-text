import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _mock_start_transcription(audio_generator, callback):
    """Drain the audio generator and fire a single fake transcript callback."""
    async for _ in audio_generator:
        pass
    await callback("test transcript")


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

class TestGetIndex:
    @pytest.mark.asyncio
    async def test_returns_html(self, tmp_path):
        fake_html = "<html><body>PoC</body></html>"
        html_file = tmp_path / "index.html"
        html_file.write_text(fake_html)

        import builtins
        real_open = builtins.open

        def fake_open(path, mode="r", *args, **kwargs):
            if "index.html" in str(path):
                return real_open(str(html_file), mode, *args, **kwargs)
            return real_open(path, mode, *args, **kwargs)

        with patch("builtins.open", fake_open):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "PoC" in response.text


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------

class TestUploadVideo:
    @pytest.mark.asyncio
    async def test_upload_saves_file_and_returns_path(self, tmp_path):
        import builtins
        real_open = builtins.open

        def fake_open(path, mode="r", *args, **kwargs):
            if mode == "wb" and "/tmp/" in str(path):
                return real_open(str(tmp_path / os.path.basename(path)), mode, *args, **kwargs)
            return real_open(path, mode, *args, **kwargs)

        with patch("builtins.open", fake_open):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/upload",
                    files={"file": ("video.mp4", b"fake-video-bytes", "video/mp4")},
                )

        assert response.status_code == 200
        assert response.json()["path"] == "/tmp/video.mp4"

    @pytest.mark.asyncio
    async def test_upload_returns_correct_filename(self, tmp_path):
        import builtins
        real_open = builtins.open

        def fake_open(path, mode="r", *args, **kwargs):
            if mode == "wb" and "/tmp/" in str(path):
                return real_open(str(tmp_path / os.path.basename(path)), mode, *args, **kwargs)
            return real_open(path, mode, *args, **kwargs)

        with patch("builtins.open", fake_open):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/upload",
                    files={"file": ("my_video.mp4", b"data", "video/mp4")},
                )

        assert response.json()["path"].endswith("my_video.mp4")


# ---------------------------------------------------------------------------
# WS /ws/transcribe  (raw PCM binary streaming)
# ---------------------------------------------------------------------------

class TestWsTranscribe:
    def test_receives_transcript_text(self):
        with patch("app.main.transcribe_service.start_transcription", side_effect=_mock_start_transcription):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as ws:
                    ws.send_bytes(b"\x00\x01" * 1024)
                    ws.close()
                    msg = ws.receive_text()
                    assert msg == "test transcript"

    def test_server_does_not_crash_on_empty_chunks(self):
        with patch("app.main.transcribe_service.start_transcription", side_effect=_mock_start_transcription):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as ws:
                    ws.send_bytes(b"")
                    ws.close()


# ---------------------------------------------------------------------------
# WS /ws/transcribe/file  (server-side ffmpeg conversion)
# ---------------------------------------------------------------------------

class TestWsTranscribeFile:
    def test_receives_transcript_for_valid_path(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_bytes(b"fake")

        mock_proc = MagicMock()
        mock_proc.stdout.read = AsyncMock(side_effect=[b"\x00\x01" * 512, b""])

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc), \
             patch("app.main.transcribe_service.start_transcription", side_effect=_mock_start_transcription):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe/file") as ws:
                    ws.send_text(str(video))
                    msg = ws.receive_text()
                    assert msg == "test transcript"

    def test_ffmpeg_called_with_correct_args(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_bytes(b"fake")

        mock_proc = MagicMock()
        mock_proc.stdout.read = AsyncMock(side_effect=[b"", b""])

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec, \
             patch("app.main.transcribe_service.start_transcription", side_effect=_mock_start_transcription):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe/file") as ws:
                    ws.send_text(str(video))

            args = mock_exec.call_args[0]
            assert "ffmpeg" in args
            assert "s16le" in args
            assert "16000" in args