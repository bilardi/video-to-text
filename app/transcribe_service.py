import asyncio
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent


class MyTranscriptHandler(TranscriptResultStreamHandler):
    def __init__(self, output_queue):
        super().__init__(output_queue)
        self.output_queue = output_queue

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        for result in results:
            # Only send final transcriptions or handle partials
            if not result.is_partial:
                for alt in result.alternatives:
                    await self.output_queue.put(alt.transcript)


class TranscribeService:
    def __init__(self, region="us-east-1"):
        # The client will automatically use AWS_PROFILE from the environment
        self.client = TranscribeStreamingClient(region=region)

    async def start_transcription(self, audio_generator, callback):
        # Start the stream towards AWS
        stream = await self.client.start_stream_transcription(
            language_code="it-IT", media_sample_rate_hz=16000, media_encoding="pcm"  # -16bit"
        )

        async def send_audio():
            async for chunk in audio_generator:
                await stream.input_stream.send_audio_event(audio_chunk=chunk)
            await stream.input_stream.end_stream()

        # Run sending and receiving in parallel
        await asyncio.gather(send_audio(), self.process_events(stream, callback))

    # async def process_events(self, stream, callback):
    #     result_queue = asyncio.Queue()
    #     handler = MyTranscriptHandler(stream.output_stream)
    #     handler.output_queue = result_queue  # keep our queue separate
    #     await handler.handle_events()
    #     while True:
    #         text = await result_queue.get()
    #         await callback(text)
    async def process_events(self, stream, callback):
        result_queue = asyncio.Queue()

        class QueueHandler(MyTranscriptHandler):
            def __init__(self):
                super().__init__(stream.output_stream)

            async def handle_transcript_event(self, transcript_event: TranscriptEvent):
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
