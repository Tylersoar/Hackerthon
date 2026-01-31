# 📋 Frontend Data Structure & WebSocket Protocol

## Overview
The frontend manages two main state arrays: **transcript segments** and **claims**. They are linked via unique IDs.

---

## 🗂️ Data Structures

### **1. Transcript Segments** (`transcriptSegments`)
An array of text segments that make up the live transcript. Each segment can either be regular text OR a claim.

```javascript
[
  {
    id: "seg-1",              // Unique segment ID
    text: "The economy is ",  // The actual text
    claimId: null             // null = not a claim, just regular text
  },
  {
    id: "seg-2",
    text: "unemployment rate is at 3%",  // This text is a claim
    claimId: "claim-1"        // Links to the claim in claims array
  },
  {
    id: "seg-3",
    text: " which is low.",
    claimId: null
  }
]
```

**Key Points:**
- Each segment has a unique `id`
- If `claimId` is `null`, it's regular text (rendered in antiquewhite)
- If `claimId` exists, it links to a claim (rendered in grey/green/red based on status)

---

### **2. Claims** (`claims`)
An array of detected claims with their fact-check status.

```javascript
[
  {
    id: "claim-1",           // Unique claim ID (matches claimId in transcript)
    text: "unemployment rate is at 3%",  // The claim text
    status: "complete",      // "checking" or "complete"
    isTrue: true,            // true/false/null
    explanation: "According to the U.S. Bureau of Labor Statistics..."
  }
]
```

**Key Points:**
- `id` must match the `claimId` in transcript segments
- `status`: 
  - `"checking"` = grey text, shows "Checking..." in sidebar
  - `"complete"` = green/red text, clickable
- `isTrue`: 
  - `null` = not checked yet
  - `true` = green text (#10b981)
  - `false` = red text (#dc3545)

---

## 🔌 WebSocket Message Protocol

### **Message 1: Regular Transcript Text**
Send this immediately when Deepgram returns text that contains NO claims.

```json
{
  "type": "transcript",
  "text": "Today I want to talk about the economy. The "
}
```

**Frontend behavior:**
- Appends text to `transcriptSegments` with `claimId: null`
- Renders in antiquewhite color

---

### **Message 2: Claim Detected**
Send this when Groq extracts a claim from the text. This should come ~2 seconds AFTER the transcript text.

```json
{
  "type": "claim_detected",
  "id": "uuid-abc-123",
  "claim": "unemployment rate is at 3%"
}
```

**Frontend behavior:**
1. Finds the last transcript segment containing this claim text
2. **Splits** that segment into 3 parts:
   - Text before claim (if any)
   - The claim itself (with `claimId`)
   - Text after claim (if any)
3. Adds claim to claims list with `status: "checking"`
4. Renders claim text in **grey (#6c757d)** with "⏳ Checking..." in sidebar

---

### **Message 3: Fact-Check Complete**
Send this when Tavily search + Groq verification finishes (~3 seconds after claim detected).

```json
{
  "type": "fact_check",
  "id": "uuid-abc-123",
  "result": {
    "isTrue": true,
    "explanation": "According to the U.S. Bureau of Labor Statistics, the unemployment rate was approximately 3.7% in recent months..."
  }
}
```

**Frontend behavior:**
- Updates claim in claims list: `status: "complete"`, `isTrue`, `explanation`
- Changes claim text color:
  - **Green (#10b981)** if `isTrue: true`
  - **Red (#dc3545)** if `isTrue: false`
- Makes claim clickable to show modal with explanation

---

## 🔄 Complete Flow Example

**User says:** "The unemployment rate is at 3% which is historically low."

### **Step 1: Backend sends transcript (immediately)**
```json
{
  "type": "transcript",
  "text": "The unemployment rate is at 3% which is historically low."
}
```
→ Frontend shows all text in antiquewhite

---

### **Step 2: Backend sends claim detected (~2s later)**
```json
{
  "type": "claim_detected",
  "id": "claim-abc-123",
  "claim": "unemployment rate is at 3%"
}
```
→ Frontend splits text:
- "The " (antiquewhite)
- "unemployment rate is at 3%" (grey)
- " which is historically low." (antiquewhite)

→ Sidebar shows: 
```
🔍 unemployment rate is at 3%
   ⏳ Checking...
```

---

### **Step 3: Backend sends fact-check result (~5s total)**
```json
{
  "type": "fact_check",
  "id": "claim-abc-123",
  "result": {
    "isTrue": true,
    "explanation": "The U.S. Bureau of Labor Statistics reports..."
  }
}
```
→ Frontend changes "unemployment rate is at 3%" to **green**, makes it clickable

→ Sidebar shows green text (no "True/False" label, just the color)

---

## ⚠️ Important Notes for Backend Team

### **1. Don't Send Claim Text Twice**
❌ **Wrong:**
```json
{"type": "transcript", "text": "unemployment rate is at 3%"}
{"type": "claim_detected", "claim": "unemployment rate is at 3%"}
```
This will show duplicate text!

✅ **Correct:**
```json
{"type": "transcript", "text": "The unemployment rate is at 3% is low."}
{"type": "claim_detected", "claim": "unemployment rate is at 3%"}
```

### **2. ID Must Match**
The `id` in `claim_detected` MUST match the `id` in `fact_check`:
```json
{"type": "claim_detected", "id": "abc-123", ...}
{"type": "fact_check", "id": "abc-123", ...}  ✅ Same ID
```

### **3. Use Async Tasks**
Don't block the WebSocket waiting for fact-checks. Use async tasks:
```python
# Send transcript immediately
await websocket.send_json({"type": "transcript", "text": sentence})

# Fork async task for claim detection + fact-checking
asyncio.create_task(process_claim(sentence, websocket))
```

### **4. Handle "No Claim Found"**
If Groq says "no verifiable claim", just send `transcript` and nothing else. Don't force a `claim_detected` message.

### **5. Case Sensitivity**
The claim text must match EXACTLY (case-sensitive) with what's in the transcript, or the splitting won't work.

---

## 🎨 Visual Summary

```
USER SPEAKS: "The Earth is flat"
     ↓
DEEPGRAM TRANSCRIBES
     ↓
BACKEND → {"type": "transcript", "text": "The Earth is flat"}
     ↓
FRONTEND: Shows in antiquewhite
     ↓
GROQ EXTRACTS CLAIM (2s)
     ↓
BACKEND → {"type": "claim_detected", "id": "claim-1", "claim": "The Earth is flat"}
     ↓
FRONTEND: Turns grey, shows "⏳ Checking..." in sidebar
     ↓
TAVILY SEARCH + GROQ VERIFY (3s)
     ↓
BACKEND → {"type": "fact_check", "id": "claim-1", "result": {"isTrue": false, "explanation": "..."}}
     ↓
FRONTEND: Turns RED, clickable, shows in sidebar
```

---

## 🧪 Test Messages You Can Send

```json
// Test 1: Regular text
{"type": "transcript", "text": "Hello everyone, "}

// Test 2: Text with a claim inside
{"type": "transcript", "text": "I think water boils at 100 degrees Celsius."}

// Test 3: Detect the claim
{"type": "claim_detected", "id": "test-1", "claim": "water boils at 100 degrees Celsius"}

// Test 4: Mark it as TRUE
{"type": "fact_check", "id": "test-1", "result": {"isTrue": true, "explanation": "Correct at sea level and standard atmospheric pressure."}}

// Test 5: Send false claim
{"type": "transcript", "text": "The Earth is flat according to research."}
{"type": "claim_detected", "id": "test-2", "claim": "The Earth is flat"}
{"type": "fact_check", "id": "test-2", "result": {"isTrue": false, "explanation": "The Earth is an oblate spheroid."}}
```

---

## 🚀 WebSocket Connection Details

- **URL:** `ws://localhost:8000/ws`
- **Audio Format:** Binary WebM/Opus chunks (250ms intervals)
- **Sample Rate:** 16kHz mono
- **Message Format:** JSON for all text messages