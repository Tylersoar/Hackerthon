import os
from groq import Groq
from tavily import TavilyClient
from deepgram import DeepgramClient
from dotenv import load_dotenv
import json

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

sentences = transcript.split('.')
claims = []

for sentence in sentences:
    sentence = sentence.strip()
    if not sentence:
        continue

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
        claims.append(sentence)

print("Identified Claims:", claims)

# Store results for frontend
results = []

for claim in claims:
    print(f"\n{'=' * 60}")
    print(f"🔍 Processing Claim: {claim}")
    print('=' * 60)

    # Step 1: Search with Tavily
    search_response = tavily_client.search(
        query=claim,
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
            print(f"\n📄 Source: {url}")
            print(f"   Evidence: {content[:200]}...")

    print(f"\n✓ Found {len(evidence)} pieces of evidence")


    evidence_text = "\n\n".join([f"Source {i + 1}: {ev}" for i, ev in enumerate(evidence)])

    analysis_completion = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """You are a fact-checker. Analyze the claim against the evidence provided.

Respond ONLY with valid JSON in this exact format:
{
    "is_true": true or false,
    "confidence": "high", "medium", or "low",
    "explanation": "Brief explanation why the claim is true/false based on evidence",
    "key_finding": "One sentence summary of the most important evidence"
}"""
            },
            {
                "role": "user",
                "content": f"Claim: {claim}\n\nEvidence:\n{evidence_text}\n\nAnalyze this claim."
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
            "is_true": False,
            "confidence": "low",
            "explanation": "Unable to parse analysis",
            "key_finding": "Analysis failed"
        }

    # Prepare result for frontend
    result = {
        "claim": claim,
        "is_true": analysis["is_true"],
        "confidence": analysis["confidence"],
        "explanation": analysis["explanation"],
        "key_finding": analysis["key_finding"],
        "sources": sources,
        "evidence_count": len(evidence)
    }

    results.append(result)

    # Display results
    print(f"\n{'✅ TRUE' if result['is_true'] else '❌ FALSE'} ({result['confidence']} confidence)")
    print(f"📊 Explanation: {result['explanation']}")
    print(f"🔑 Key Finding: {result['key_finding']}")

# Final output for frontend
print("\n" + "=" * 60)
print("📦 FINAL RESULTS FOR FRONTEND:")
print("=" * 60)
print(json.dumps(results, indent=2))