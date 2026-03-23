# Inspiration
In an era where misinformation spreads faster than ever, we wanted to create a tool that could help people verify what they hear in real-time. Whether it's a podcast, interview, or live speech, TruthStream was born from the need to instantly fact-check spoken content without disrupting the listening experience. We envisioned a world where truth is just a glance away.

# What it does
TruthStream is an AI-powered real-time audio fact-checking platform. Users can either record live audio through their microphone or upload audio files. The application:

1. Transcribes speech in real-time using Deepgram's Nova-3 model
2. Detects factual claims within the transcript using Groq's Llama 3.3 70B model
3. Verifies each claim by searching trusted sources with Tavily's advanced search API
4. Analyses the evidence against claims using AI reasoning
5. Visualises results with color-coded text: grey for checking, green for true, red for false
6. Users can click on any verified claim to see a detailed explanation of why it's true or false, complete with evidence sources.

# How we built it
**Frontend:**

- React with hooks for state management
- Bootstrap React for responsive UI components
- WebSocket API for real-time bidirectional communication
- MediaRecorder API for audio capture in WebM/Opus format
- Custom dark theme with Montserrat typography

**Backend:**

- FastAPI with WebSocket support for real-time audio streaming
- Deepgram SDK for speech-to-text transcription
- Groq API with Llama 3.3 70B for claim detection and analysis
- Tavily API for evidence gathering from trusted sources
- Asynchronous processing to handle multiple claims simultaneously

**Architecture**: The frontend streams audio chunks over WebSocket to the backend, which buffers and processes them. The backend sends three message types: transcript (immediate), claim_detected (~2s later), and fact_check (~5s total). This creates a smooth real-time experience.

# Challenges we ran into
1. WebSocket stability: Getting the WebSocket connection to stay open while processing long audio files was tricky. We had to implement proper timeout handling and differentiate between live recording and file upload sessions.

2. Claim text matching: Splitting transcript segments to highlight specific claims required careful string manipulation to avoid duplicating text or creating mismatched segments.

3. Real-time processing: Balancing speed with accuracy was challenging. We optimized by processing claims asynchronously while continuing to transcribe.

4. Audio format compatibility: Ensuring the WebM/Opus audio format from the browser was compatible with Deepgram's API required specific MediaRecorder configuration.

5. Node module corruption: We encountered dependency issues with Vite during development that required complete reinstallation of node_modules.

# Accomplishments that we're proud of
- Built a fully functional real-time fact-checking system in a hackathon timeframe
- Achieved seamless WebSocket streaming with zero data loss
- Created an intuitive UI that makes complex AI processing feel simple
- Successfully integrated four different APIs (Deepgram, Groq, Tavily, FastAPI) into a cohesive system
- Implemented both live recording and file upload with the same processing pipeline
- Designed a color-coding system that makes truth instantly recognizable

# What we learned
- WebSocket protocols: Deep understanding of bidirectional real-time communication patterns
- Audio processing: How to handle streaming audio data in chunks and buffer management
- AI prompt engineering: Crafting precise prompts for claim detection and fact verification
- Async programming: Managing asynchronous tasks in Python with FastAPI and asyncio
- React state management: Complex state updates for real-time data visualization
- API orchestration: Coordinating multiple AI services to work together seamlessly

# What's next for TruthStream
- Source citations: Display clickable links to evidence sources for transparency
- Multi-language support: Expand beyond English to fact-check global content
- Speaker identification: Identify different speakers and track claims per person
- Browser extension: Real-time fact-checking for YouTube, podcasts, and video calls
- Confidence scores: Show probability ratings for ambiguous claims
- Historical tracking: Save fact-check sessions for later review
- Mobile app: Native iOS/Android apps for on-the-go fact-checking
- API access: Allow developers to integrate TruthStream into their own applications
