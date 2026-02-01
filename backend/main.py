"""
Main entry point for the FastAPI backend.

This module sets up a WebSocket endpoint that:
1. Receives raw audio bytes from the frontend.
2. Streams audio to Deepgram for real-time transcription.
3. Processes finalized sentences through a fact-checking logic pipeline.
"""
import asyncio
import os
import uuid
import time
from datetime import datetime

from fastapi import FastAPI, WebSocket
from deepgram import DeepgramClient
from deepgram.clients.live.v1 import LiveTranscriptionEvents, LiveOptions
from dotenv import load_dotenv
import logic  # We import the file we just made

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Missing API keys")

# Initialize Deepgram SDK and FastAPI instance
deepgram_client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
app = FastAPI()


def _ts():
    return datetime.now().isoformat(timespec="seconds")


def dprint(component, message):
    print(f"[{_ts()}] [{component}] {message}")

async def handle_sentence(text, sentence_id, user_socket):
    """
    Processes a finalized sentence to detect and verify claims.

    :param text: The transcribed text string.
    :param sentence_id: A unique UUID for tracking this specific sentence.
    :param user_socket: The active WebSocket connection to the frontend.
    """
    dprint("HANDLE", f"Start handle_sentence id={sentence_id}")

    # Step 1: Use LLM to determine if the sentence contains a verifiable claim
    start_claim = time.monotonic()
    claim_text = await logic.extract_claim(text)
    dprint(
        "HANDLE",
        f"extract_claim completed in {time.monotonic() - start_claim:.2f}s; has_claim={'YES' if claim_text else 'NO'}",
    )

    if claim_text:
        # Step 2: Notify frontend immediately so it can show a "loading/checking" state
        dprint("HANDLE", f"Sending claim_detected id={sentence_id}")
        await user_socket.send_json({
            "type": "claim_detected",
            "id": sentence_id,
            "claim": claim_text

        })

        # Step 3: Perform RAG/Search to verify the claim against reliable sources
        start_verify = time.monotonic()
        verdict = await logic.verify_claim(claim_text)
        dprint("HANDLE", f"verify_claim completed in {time.monotonic() - start_verify:.2f}s")

        # Step 4: Push the final verdict and explanation to the UI
        dprint("HANDLE", f"Sending fact_check id={sentence_id} isTrue={verdict['result']['isTrue']}")
        await user_socket.send_json({
            "type": "fact_check",
            "id": sentence_id,
            "result": {
                "isTrue": verdict["result"]["isTrue"],
                "explanation": verdict["result"]["explanation"]
            }
        })
        dprint("HANDLE", f"Completed handle_sentence id={sentence_id}")

# --- THE MAIN LOOP ---
@app.websocket("/ws")
async def websocket_endpoint(user_socket : WebSocket) :
    """
    Handles the lifecycle of a WebSocket connection, bridging the frontend
    audio stream with Deepgram's AI transcription service.
    """
    await user_socket.accept()
    dprint("WS", "WebSocket connection accepted")

    # Initialize a persistent connection to Deepgram's streaming API
    dg_connection = deepgram_client.listen.asyncwebsocket.v("1")

    options = LiveOptions(
        model="nova-3",
        smart_format=True,
        endpointing=500,
        punctuate=True,
        language="en-US",
        # Switch to raw PCM 16-bit LE at 16kHz to ensure consistent decoding
        encoding="linear16",
        sample_rate=16000,
        channels=1,
    )
    dprint(
        "WS",
        "Deepgram LiveOptions set (model=nova-3, smart_format=True, endpointing=500, punctuate=True, language=en-US)",
    )

    async def on_transcript(self, result, **kwargs):
        """
        Event handler: Runs whenever Deepgram processes a chunk of audio.
        """
        try:
            dprint("DG", "on_transcript event received")

            # Support both object- and dict-shaped payloads from SDK/events
            sentence = ""
            if isinstance(result, dict):
                sentence = (
                    result.get("channel", {})
                    .get("alternatives", [{"transcript": ""}])[0]
                    .get("transcript", "")
                )
                is_final = result.get("is_final", False)
            else:
                sentence = getattr(getattr(result, "channel", {}), "alternatives", [{}])[0].get(
                    "transcript", ""
                ) if isinstance(getattr(result, "channel", {}), dict) else getattr(
                    getattr(result, "channel", None).alternatives[0], "transcript", ""
                ) if getattr(getattr(result, "channel", None), "alternatives", None) else ""
                # Guard against SDK variations where `is_final` might be absent
                is_final = getattr(result, "is_final", False)

            if not sentence:
                return

            # Unique ID allows the frontend to link transcripts to future fact-check results
            sent_id = str(uuid.uuid4())

            # Send interim or final text to frontend for real-time captions
            preview = (sentence[:60] + "...") if len(sentence) > 60 else sentence
            dprint("DG", f"Sending transcript id={sent_id} is_final={is_final} text='{preview}'")
            await user_socket.send_json(
                {
                    "type": "transcript",
                    "text": sentence,
                    "id": sent_id,
                }
            )

            if is_final:
                # If Deepgram marks the sentence as finished, start the background fact-check
                dprint("DG", f"Scheduling handle_sentence for id={sent_id}")
                asyncio.create_task(handle_sentence(sentence, sent_id, user_socket))
        except Exception as e:
            dprint("DG", f"on_transcript error: {e}")

    # Register the callback and start the Deepgram stream
    async def on_open(self, event, **kwargs):
        dprint("DG", "connection opened")

    async def on_close(self, event=None, **kwargs):
        dprint("DG", "connection closed")

    async def on_error(self, err=None, **kwargs):
        dprint("DG", f"error event: {err}")

    async def on_metadata(self, meta=None, **kwargs):
        dprint("DG", f"metadata: {meta}")

    dg_connection.on(LiveTranscriptionEvents.Open, on_open)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)
    dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
    dprint("WS", "Starting Deepgram websocket stream")
    await dg_connection.start(options)
    dprint("WS", "Deepgram websocket stream started")

    try:
        # Main loop: Receive binary audio data from browser and pipe it to Deepgram
        while True:
            # Wait for audio from frontend
            # dprint("WS", "Waiting for audio bytes from frontend...")
            data = await user_socket.receive_bytes()

            # Forward raw PCM/Opus bytes to Deepgram for processing
            # dprint("WS", f"Forwarding {len(data)} bytes to Deepgram")
            await dg_connection.send(data)

    except Exception as e:
        dprint("WS", f"Error: {e}")
    finally:
        dprint("WS", "Finishing Deepgram websocket stream")
        await dg_connection.finish()
        dprint("WS", "WebSocket handler exiting")

# ---- LEGACY BELOW ------
#
# file_path = "../res/polarBear.mp3"
#
#
# def main():
#     print(f"📂 Reading audio file: {file_path}")
#     with open(file_path, "rb") as audio_file:
#         audio_bytes = audio_file.read()
#
#     # Transcription request (EXACTLY AS IN YOUR ORIGINAL CODE)
#     response = deepgram_client.listen.v1.media.transcribe_file(
#         request=audio_bytes,
#         model="nova-3",
#         smart_format=True,
#         punctuate=True,
#         language="en"
#     )
#
#     # Extract transcript text
#     transcript = response.results.channels[0].alternatives[0].transcript
#     print("Transcript:", transcript)
#
#     # Message 1: Send transcript
#     transcript_message = {
#         "type": "transcript",
#         "text": transcript
#     }
#     print("\n📤 Message 1 - TRANSCRIPT:")
#     print(json.dumps(transcript_message, indent=2))
#
#     sentences = transcript.split('.')
#
#     for sentence in sentences:
#         sentence = sentence.strip()
#         if not sentence:
#             continue
#
#         # --- CALL THE BRAIN (LOGIC.PY) ---
#         # This replaces the huge block of code in your loop
#         result_data = logic.process_sentence_logic(sentence)
#
#         if result_data:
#             # Reconstruct the print statements you had originally
#
#             print(f"\n{'=' * 60}")
#             print(f"🔍 Processing Claim: {sentence}")
#             print('=' * 60)
#
#             # Message 2: Claim detected
#             claim_detected_message = {
#                 "type": "claim_detected",
#                 "id": result_data["id"],
#                 "claim": sentence
#             }
#             print("\n📤 Message 2 - CLAIM DETECTED:")
#             print(json.dumps(claim_detected_message, indent=2))
#
#             # Print evidence summary
#             for ev in result_data["evidence"]:
#                 print(f"   Evidence: {ev[:200]}...")
#
#             # Message 3: Fact-check complete
#             fact_check_message = {
#                 "type": "fact_check",
#                 "id": result_data["id"],
#                 "result": {
#                     "isTrue": result_data["result"]["isTrue"],
#                     "explanation": result_data["result"]["explanation"]
#                 }
#             }
#
#             print(f"\n📤 Message 3 - FACT CHECK COMPLETE:")
#             print(json.dumps(fact_check_message, indent=2))
#
#             # Display summary
#             print(f"\n{'✅ TRUE' if result_data['result']['isTrue'] else '❌ FALSE'}")
#             print(f"📊 Explanation: {result_data['result']['explanation']}")
#
#     print("\n" + "=" * 60)
#     print("✅ ALL MESSAGES SENT TO FRONTEND")
#     print("=" * 60)
#
#
# if __name__ == "__main__":
#     main()