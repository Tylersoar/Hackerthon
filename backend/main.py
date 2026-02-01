import asyncio
import os
import uuid

from fastapi import FastAPI, WebSocket
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
from dotenv import load_dotenv
import logic  # We import the file we just made

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Missing API keys")

deepgram_client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
app = FastAPI()

async def handle_sentence(text, sentence_id, user_socket):

    # Claim detection
    claim_text = await logic.extract_claim(text)

    if claim_text:
        # Immediately inform frontend
        await user_socket.send_json({
            "type": "claim_detected",
            "id": sentence_id,
            "claim": claim_text

        })

        # Verification
        verdict = await logic.verify_claim(claim_text)

        # Final result: give to frontend
        await user_socket.send_json({
            "type": "fact_check",
            "id": sentence_id,
            "result": {
                "isTrue": verdict["result"]["isTrue"],
                "explanation": verdict["result"]["explanation"]
            }
        })

# --- THE MAIN LOOP ---
@app.websocket("/ws")
async def websocket_endpoint(user_socket : WebSocket) :
    await user_socket.accept()

    dg_connection = deepgram_client.listen.asyncwebsocket.v("1")

    options = LiveOptions(
        model="nova-3",          # Upgrade to latest model
        smart_format=True,       # Critical for correct punctuation/formatting
        endpointing=500,         # Wait 500ms silence before finalizing (better context)
        punctuate=True,          # (Redundant with smart_format but good to keep)
        language="en-US",
        encoding="linear16",
        channels=1,
        sample_rate=16000,
    )

    async def on_transcript(self, result, **kwargs):
        sentence = result.channel.alternatives[0].transcript

        if len(sentence) == 0:
            return

        # Generate ID
        sent_id = str(uuid.uuid4())

        # Message 1: transcript, always sent
        await user_socket.send_json(
            {
                "type": "transcript",
                "text": sentence,
                "id": sent_id
            }

        )

        if result.is_final:
            asyncio.create_task(handle_sentence(sentence, sent_id, user_socket))

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)

    await dg_connection.start(options)

    # Keeps connection alive
    try:
        while True:
            # Wait for audio from frontend
            data = await user_socket.receive_bytes()

            # Push bytes to deepgram
            await dg_connection.send(data)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await dg_connection.finish()

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