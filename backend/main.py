import os
import json
from deepgram import DeepgramClient
from dotenv import load_dotenv
import json
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Missing API keys")

deepgram_client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

file_path = "../res/polarBear.mp3"

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def process_audio(audio_bytes: bytes, websocket: WebSocket):
    """Process audio file and send results to frontend via WebSocket"""
    
    # Transcription request
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

    # Message 1: Send transcript immediately
    transcript_message = {
        "type": "transcript",
        "text": transcript
    }
    await websocket.send_json(transcript_message)
    print("\n📤 Message 1 - TRANSCRIPT sent")

    sentences = transcript.split('.')

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Check if sentence contains a claim
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "Respond with only 'YES' or 'NO': Is this a verifiable factual claim?"
                },
                {
                    "role": "user",
                    "content": sentence
                }
            ],
            temperature=0.1,
            max_tokens=10
        )

        is_claim = completion.choices[0].message.content.strip().upper()

        if is_claim == "YES":
            # Generate unique ID for this claim
            claim_id = str(uuid.uuid4())

            print(f"\n{'=' * 60}")
            print(f"🔍 Processing Claim: {sentence}")
            print('=' * 60)

            # Message 2: Claim detected
            claim_detected_message = {
                "type": "claim_detected",
                "id": claim_id,
                "claim": sentence
            }
            await websocket.send_json(claim_detected_message)
            print("\n📤 Message 2 - CLAIM DETECTED sent")

            # Step 1: Search with Tavily
            search_response = tavily_client.search(
                query=sentence,
                search_depth="advanced",
                max_results=3
            )

            evidence = []
            sources = []
            for result in search_response.get('results', []):
                content = result.get('content', '')
                url = result.get('url', '')
                if content:
                    evidence.append(content)
                    sources.append(url)
                    print(f"   Evidence: {content[:200]}...")

            # Step 2: Analyze with Groq
            evidence_text = "\n\n".join([f"Source {i + 1}: {ev}" for i, ev in enumerate(evidence)])

            analysis_completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a fact-checker. Analyze the claim against the evidence provided.

Respond ONLY with valid JSON in this exact format:
{
    "isTrue": true or false,
    "explanation": "Brief explanation why the claim is true/false based on evidence"
}"""
                    },
                    {
                        "role": "user",
                        "content": f"Claim: {sentence}\n\nEvidence:\n{evidence_text}\n\nAnalyze this claim."
                    }
                ],
                temperature=0.2,
                max_tokens=300
            )

            # Parse the analysis
            try:
                analysis = json.loads(analysis_completion.choices[0].message.content.strip())
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                analysis = {
                    "isTrue": False,
                    "explanation": "Unable to parse analysis"
                }

            # Message 3: Fact-check complete
            fact_check_message = {
                "type": "fact_check",
                "id": claim_id,
                "result": {
                    "isTrue": analysis["isTrue"],
                    "explanation": analysis["explanation"]
                }
            }

            await websocket.send_json(fact_check_message)
            print(f"\n📤 Message 3 - FACT CHECK COMPLETE sent")

            # Display summary
            print(f"\n{'✅ TRUE' if analysis['isTrue'] else '❌ FALSE'}")
            print(f"📊 Explanation: {analysis['explanation']}")

    print("\n" + "=" * 60)
    print("✅ ALL MESSAGES SENT TO FRONTEND")
    print("=" * 60)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🔌 WebSocket connected")
    
    audio_buffer = bytearray()
    session_id = None
    session_type = None  # 'recording' or 'upload'
    
    try:
        while True:
            # Receive data from frontend with timeout
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=2.0)
            except asyncio.TimeoutError:
                # If we have buffered audio from file upload and no new data, process it
                if len(audio_buffer) > 0 and session_type == 'upload':
                    print(f"\n🎵 Processing uploaded audio file: {len(audio_buffer)} bytes")
                    await process_audio(bytes(audio_buffer), websocket)
                    audio_buffer.clear()
                    session_type = None
                    # Send processing complete message
                    await websocket.send_json({"type": "processing_complete"})
                    print("✅ Processing complete, waiting for new uploads...")
                continue
            
            # Handle JSON messages
            if 'text' in data:
                message = json.loads(data['text'])
                msg_type = message.get('type')
                
                if msg_type == 'start_recording':
                    session_id = message.get('id')
                    session_type = 'recording'
                    audio_buffer.clear()
                    print(f"🎤 Received recording session ID: {session_id}")
                    
                elif msg_type == 'upload_file':
                    session_id = message.get('id')
                    session_type = 'upload'
                    audio_buffer.clear()
                    print(f"📁 Received file upload session ID: {session_id}")
                    
                elif msg_type == 'stop_recording':
                    # Process the recorded audio
                    if len(audio_buffer) > 0 and session_type == 'recording':
                        print(f"\n🎤 Processing recorded audio: {len(audio_buffer)} bytes")
                        await process_audio(bytes(audio_buffer), websocket)
                        audio_buffer.clear()
                        session_type = None
                        # Send processing complete message
                        await websocket.send_json({"type": "processing_complete"})
                        print("✅ Recording processed, ready for next session")
                continue
            
            # Subsequent messages are binary audio chunks
            if 'bytes' in data:
                chunk = data['bytes']
                audio_buffer.extend(chunk)
                print(f"📥 Received audio chunk: {len(chunk)} bytes (total: {len(audio_buffer)})")
                
    except WebSocketDisconnect:
        print("🔌 WebSocket disconnected")
    except Exception as e:
        print(f"❌ Error: {e}")
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)