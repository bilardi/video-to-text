"""This package contains classes to manage the Amazon Transcribe communication"""

import asyncio
from collections.abc import AsyncGenerator, Callable, Awaitable
from typing import Any
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent


class MyTranscriptHandler(TranscriptResultStreamHandler):
    """Handles transcript events from Amazon Transcribe and queues final results."""

    def __init__(self, output_queue: asyncio.Queue) -> None:
        super().__init__(output_queue)
        self.output_queue = output_queue

    async def handle_transcript_event(self, transcript_event: TranscriptEvent) -> None:
        """Filter out partial results and enqueue only final transcript alternatives."""
        results = transcript_event.transcript.results
        for result in results:
            # Only send final transcriptions or handle partials
            if not result.is_partial:
                for alt in result.alternatives:
                    await self.output_queue.put(alt.transcript)


class TranscribeService:
    """Manages a streaming session with Amazon Transcribe."""

    def __init__(self, region: str = "eu-west-1") -> None:
        # The client will automatically use AWS_PROFILE from the environment
        self.client = TranscribeStreamingClient(region=region)

    async def start_transcription(
        self,
        audio_generator: AsyncGenerator[bytes, None],
        callback: Callable[[str], Awaitable[None]],
    ) -> None:
        """Open a Transcribe stream, send audio chunks,
        and invoke callback for each final transcript."""
        # Start the stream towards AWS
        stream = await self.client.start_stream_transcription(
            language_code="it-IT", media_sample_rate_hz=16000, media_encoding="pcm"
        )

        async def send_audio():
            async for chunk in audio_generator:
                await stream.input_stream.send_audio_event(audio_chunk=chunk)
            await stream.input_stream.end_stream()

        # Run sending and receiving in parallel
        await asyncio.gather(send_audio(), self.process_events(stream, callback))

    async def process_events(self, stream: Any, callback: Callable[[str], Awaitable[None]]):
        """Consume transcript events from the output stream
        and forward final results to the callback."""
        result_queue = asyncio.Queue()

        class QueueHandler(MyTranscriptHandler):
            """Overrides handle_transcript_event to route results to result_queue."""

            def __init__(self) -> None:
                super().__init__(stream.output_stream)

            async def handle_transcript_event(self, transcript_event: TranscriptEvent) -> None:
                results = transcript_event.transcript.results
                for result in results:
                    if not result.is_partial:
                        for alt in result.alternatives:
                            await result_queue.put(alt.transcript)

        handler = QueueHandler()

        async def drain_queue():
            while True:
                text = await result_queue.get()
                await callback(text)

        await asyncio.gather(handler.handle_events(), drain_queue())
