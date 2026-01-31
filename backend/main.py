import os
from groq import Groq
from tavily import TavilyClient
from deepgram import DeepgramClient
from dotenv import load_dotenv

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

for claim in claims:
    search_response = tavily_client.search(
        query=claim,
        search_depth="advanced",
        max_results=3
    )

    evidence = []
    for result in search_response.get('results', []):
        content = result.get('content', '')
        url = result.get('url', '')
        if content:
            evidence.append(content)
            print(f"\n📄 Source: {url}")
            print(f"   Evidence: {content[:200]}...")

    print(f"\n✓ Found {len(evidence)} pieces of evidence")
