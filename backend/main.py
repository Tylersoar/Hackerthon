import os
from groq import Groq
from tavily import TavilyClient
from deepgram import DeepgramClient
from dotenv import load_dotenv
import json
import uuid

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not GROQ_API_KEY or not DEEPGRAM_API_KEY or not TAVILY_API_KEY:
    raise RuntimeError("Missing API keys")

groq_client = Groq(api_key=GROQ_API_KEY)
deepgram_client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

file_path = "../res/polarBear.webm"

with open(file_path, "rb") as audio_file:
    audio_bytes = audio_file.read()

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

# Message 1: Send transcript immediately (simulating WebSocket send)
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

        # Message 2: Claim detected (~2s after transcript)
        claim_detected_message = {
            "type": "claim_detected",
            "id": claim_id,
            "claim": sentence
        }
        print("\n📤 Message 2 - CLAIM DETECTED:")
        print(json.dumps(claim_detected_message, indent=2))

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
                #print(f"\n📄 Source: {url}")
                print(f"   Evidence: {content[:200]}...")

        #print(f"\n✓ Found {len(evidence)} pieces of evidence")

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

        # Message 3: Fact-check complete (~5s total after transcript)
        fact_check_message = {
            "type": "fact_check",
            "id": claim_id,
            "result": {
                "isTrue": analysis["isTrue"],
                "explanation": analysis["explanation"]
            }
        }

        print(f"\n📤 Message 3 - FACT CHECK COMPLETE:")
        print(json.dumps(fact_check_message, indent=2))

        # Display summary
        print(f"\n{'✅ TRUE' if analysis['isTrue'] else '❌ FALSE'}")
        print(f"📊 Explanation: {analysis['explanation']}")

print("\n" + "=" * 60)
print("✅ ALL MESSAGES SENT TO FRONTEND")
print("=" * 60)