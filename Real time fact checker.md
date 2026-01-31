Here is the **Mission Brief** for your team. Copy and paste this directly into your group chat or Slack.

---

# 🚀 Project: Truth Stream (Hackathon Brief)

**The Pitch:** A real-time "lie detector" for live speech. We transcribe audio instantly and render a "fact-check subtitle track" alongside the text.

**The Goal:** **Extreme Speed.** If the fact-check takes >3 seconds, we fail.

---

### 🛠 The "Speed Stack" (Our Tech Choices)

- **Frontend:** React + Vite (State management is key here).
    
- **Transport:** WebSockets (Binary audio up, JSON text down).
    
- **Backend:** Python **FastAPI** (Must be Async).
    
- **Speech-to-Text:** **Deepgram Nova-2** (Streaming API).
    
- **AI Intelligence:** **Groq** API running **Llama 3-8B** (For sub-200ms inference).
    
- **Fact Source:** **Tavily** API (Web search optimized for agents).
    

---

### 📡 The Data Flow (Architecture)

1. **Mic Input (FE)** → Stream Audio Chunks (WS) → **Backend**.
    
2. **Backend** → Stream to **Deepgram**.
    
3. **Deepgram** → Returns "Sentence Finished" Text.
    
4. **Backend (Fork 1)** → Push Text to **Frontend** (User sees transcript immediately).
    
5. **Backend (Fork 2)** → **Groq** (Extract Claim) → **Tavily** (Search) → **Groq** (Verify).
    
6. **Backend** → Push "Truth Rating" to **Frontend** (Snaps onto the text 2s later).
    

---

### 👨‍💻 Backend Tasks (The Orchestrator)

- **Setup:** FastAPI with `websockets` support.
    
- **Deepgram:** Implement the streaming client (receive audio, send text back).
    
- **The "Rolling Window":**
    
    - **Do not** process sentences in isolation.
        
    - Keep a buffer of the last 3 sentences (`deque(maxlen=3)`).
        
    - Send `[Context] + [Target Sentence]` to Groq so it understands "It" or "He".
        
- **Async Logic:** When Deepgram returns text, **do not block.** `await` the socket send to frontend, but use `asyncio.create_task` for the heavy LLM/Search logic.
    
- **Mock Tavily:** Write a fake search function that sleeps for 1s and returns "True" so we don't burn API credits during dev.
    

### 🎨 Frontend Tasks (The Experience)

- **Audio Capture:** Use `MediaRecorder` API to capture mic input and send binary blobs every 250ms over WebSocket.
    
- **Stable UI:**
    
    - Incoming text needs a **UUID**.
        
    - When the "Fact Check" event comes in 3 seconds later, it must find that UUID and attach the result (Green Check / Red X).
        
    - _Do not let the text jump around._
        
- **Optimistic UI:**
    
    - As soon as a sentence finishes, show a grey "Searching..." spinner or icon.
        
    - Don't leave the user staring at blank space.
        
- **Visual Feedback:** Add a simple **VU Meter** (audio visualizer) so the user knows the mic is working during silence.
    

---

### ⚠️ The Golden Rules

1. **Latency is King:** Show the transcript _instantly_. Never wait for the fact-check to show the text.
    
2. **Context Matters:** Pass the previous sentence to the AI, or it won't know what the speaker is talking about.
    
3. **Don't Over-Check:** If the AI says "No verifiable claim found," just show the text and move on. Don't force a search.