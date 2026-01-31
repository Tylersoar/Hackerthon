import os

from deepgram import DeepgramClient

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Initialize client with API key
client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

file_path = "../res/polarBear.webm"

with open(file_path, "rb") as audio_file:
    audio_bytes = audio_file.read()

# Transcription request
response = client.listen.v1.media.transcribe_file(
    request=audio_bytes,
    model="nova-3",
    smart_format=True,
    punctuate=True,
    language="en"
)

# Extract transcript text
transcript = response.results.channels[0].alternatives[0].transcript

print("Transcript:", transcript)
