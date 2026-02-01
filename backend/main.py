import os
import json
from deepgram import DeepgramClient
from dotenv import load_dotenv
import logic  # We import the file we just made

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Missing API keys")

deepgram_client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

file_path = "../res/polarBear.mp3"


def main():
    print(f"📂 Reading audio file: {file_path}")
    with open(file_path, "rb") as audio_file:
        audio_bytes = audio_file.read()

    # Transcription request (EXACTLY AS IN YOUR ORIGINAL CODE)
    response = deepgram_client.listen.v1.media.transcribe_file(
        request=audio_bytes,
        model="nova-3",
        smart_format=True,
        punctuate=True,
        language="en"
    )

    # Extract transcript text
    transcript = response.results.channels[0].alternatives[0].transcript
    print("Transcript:", transcript)

    # Message 1: Send transcript
    transcript_message = {
        "type": "transcript",
        "text": transcript
    }
    print("\n📤 Message 1 - TRANSCRIPT:")
    print(json.dumps(transcript_message, indent=2))

    sentences = transcript.split('.')

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # --- CALL THE BRAIN (LOGIC.PY) ---
        # This replaces the huge block of code in your loop
        result_data = logic.process_sentence_logic(sentence)

        if result_data:
            # Reconstruct the print statements you had originally

            print(f"\n{'=' * 60}")
            print(f"🔍 Processing Claim: {sentence}")
            print('=' * 60)

            # Message 2: Claim detected
            claim_detected_message = {
                "type": "claim_detected",
                "id": result_data["id"],
                "claim": sentence
            }
            print("\n📤 Message 2 - CLAIM DETECTED:")
            print(json.dumps(claim_detected_message, indent=2))

            # Print evidence summary
            for ev in result_data["evidence"]:
                print(f"   Evidence: {ev[:200]}...")

            # Message 3: Fact-check complete
            fact_check_message = {
                "type": "fact_check",
                "id": result_data["id"],
                "result": {
                    "isTrue": result_data["result"]["isTrue"],
                    "explanation": result_data["result"]["explanation"]
                }
            }

            print(f"\n📤 Message 3 - FACT CHECK COMPLETE:")
            print(json.dumps(fact_check_message, indent=2))

            # Display summary
            print(f"\n{'✅ TRUE' if result_data['result']['isTrue'] else '❌ FALSE'}")
            print(f"📊 Explanation: {result_data['result']['explanation']}")

    print("\n" + "=" * 60)
    print("✅ ALL MESSAGES SENT TO FRONTEND")
    print("=" * 60)


if __name__ == "__main__":
    main()