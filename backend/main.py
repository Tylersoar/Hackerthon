"""
Main entry point for the FastAPI backend.

This module sets up a WebSocket endpoint that:
1. Receives raw audio bytes from the frontend.
2. Streams audio to Deepgram for real-time transcription.
3. Processes finalized sentences through a fact-checking logic pipeline.
"""
import asyncio
import os
import uuid
import time
from datetime import datetime

from fastapi import FastAPI, WebSocket
from deepgram import DeepgramClient
from deepgram.clients.live.v1 import LiveTranscriptionEvents, LiveOptions
from dotenv import load_dotenv
import logic

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Missing API keys")

# Initialize Deepgram SDK and FastAPI instance
deepgram_client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
app = FastAPI()


def _ts():
    return datetime.now().isoformat(timespec="seconds")


def dprint(component, message):
    print(f"[{_ts()}] [{component}] {message}")

async def verify_and_report(claim_text, full_context, sentence_id, user_socket):
    """
    Verifies a detected claim and sends the result to the frontend.
    
    :param claim_text: The extracted claim string.
    :param full_context: The full text context (accumulator value) for better verification.
    :param sentence_id: The UUID for this sentence block.
    :param user_socket: The active WebSocket connection.
    """
    dprint("HANDLE", f"Start verify_and_report id={sentence_id}")

    # Step 1: Notify frontend immediately so it can show a "loading/checking" state
    # We already have the claim text here.
    dprint("HANDLE", f"Sending claim_detected id={sentence_id}")
    await user_socket.send_json({
        "type": "claim_detected",
        "id": sentence_id,
        "claim": claim_text
    })

    # Step 2: Perform RAG/Search to verify the claim against reliable sources
    start_verify = time.monotonic()
    verdict = await logic.verify_claim(claim_text, context_text=full_context)
    dprint("HANDLE", f"verify_claim completed in {time.monotonic() - start_verify:.2f}s")

    # Step 3: Push the final verdict and explanation to the UI
    dprint("HANDLE", f"Sending fact_check id={sentence_id} isTrue={verdict['result']['isTrue']}")
    await user_socket.send_json({
        "type": "fact_check",
        "id": sentence_id,
        "expandedClaim": verdict.get("expanded_claim", claim_text),
        "result": {
            "isTrue": verdict["result"]["isTrue"],
            "explanation": verdict["result"]["explanation"]
        }
    })
    dprint("HANDLE", f"Completed verify_and_report id={sentence_id}")


# --- THE MAIN LOOP ---
@app.websocket("/ws")
async def websocket_endpoint(user_socket : WebSocket) :
    """
    Handles the lifecycle of a WebSocket connection, bridging the frontend
    audio stream with Deepgram's AI transcription service.
    """
    await user_socket.accept()
    dprint("WS", "WebSocket connection accepted")

    # --- Session state ---
    # Rolling context of last finalized sentences (strings)
    context_sentences = []
    CONTEXT_SENTENCES = int(os.getenv("CONTEXT_SENTENCES", "3"))

    # Sentence assembly state
    current_sentence_id = str(uuid.uuid4())
    working_text = ""  # live, growing text for the current sentence

    # Finalization guards/timers
    update_seq = 0  # increases on every DG update; guards pending finalize tasks
    pending_finalize_task = None
    pending_idle_task = None

    # Grace timings (seconds)
    GRACE_PUNCT = float(os.getenv("GRACE_PUNCT", "0.55"))
    GRACE_NOPUNCT = float(os.getenv("GRACE_NOPUNCT", "1.30"))
    GRACE_CONNECTOR = float(os.getenv("GRACE_CONNECTOR", "2.00"))
    NORMALIZE_TRANSCRIPT = os.getenv("NORMALIZE_TRANSCRIPT", "0") not in ("0", "false", "False", None)

    # Initialize a persistent connection to Deepgram's streaming API
    dg_connection = deepgram_client.listen.asyncwebsocket.v("1")

    options = LiveOptions(
        model="nova-3",
        smart_format=True,
        # Increase endpointing so Deepgram is less likely to cut mid‑sentence
        endpointing=1200,
        punctuate=True,
        language="en-US",
        # Switch to raw PCM 16-bit LE at 16kHz to ensure consistent decoding
        encoding="linear16",
        sample_rate=16000,
        channels=1,
    )
    dprint(
        "WS",
        "Deepgram LiveOptions set (model=nova-3, smart_format=True, endpointing=1200, punctuate=True, language=en-US)",
    )

    def _ends_with_terminal_punct(s: str) -> bool:
        s = s.strip()
        return len(s) > 0 and s[-1] in ".!?"

    def _has_connector_or_comma(s: str) -> bool:
        s = s.strip().lower()
        # If sentence ends with comma/semicolon/colon, or last token is a connector, likely continuation
        if s.endswith((",", ";", ":")):
            return True
        connector_tokens = {"that", "and", "than", "because", "which", "who", "whom", "whose", "while", "but"}
        last = s.split()[-1] if s.split() else ""
        return last in connector_tokens

    def _choose_grace_seconds(s: str) -> float:
        if _has_connector_or_comma(s):
            return GRACE_CONNECTOR
        return GRACE_PUNCT if _ends_with_terminal_punct(s) else GRACE_NOPUNCT

    def _normalize_transcript_piece(s: str) -> str:
        """
        Conservative normalization to improve readability for common fused words.
        Enabled only when NORMALIZE_TRANSCRIPT is truthy.
        """
        if not NORMALIZE_TRANSCRIPT or not s:
            return s
        try:
            import re
            rules = [
                (re.compile(r"\bthebears\b", re.IGNORECASE), "the bears"),
                (re.compile(r"\bthebear\b", re.IGNORECASE), "the bear"),
                (re.compile(r"\bthebody\b", re.IGNORECASE), "the body"),
                (re.compile(r"\bthebodies\b", re.IGNORECASE), "the bodies"),
            ]
            out = s
            for pat, repl in rules:
                out = pat.sub(repl, out)
            return out
        except Exception:
            return s

    async def _send_transcript(text: str, is_final: bool, sid: str | None = None):
        await user_socket.send_json({
            "type": "transcript",
            "text": text,
            "id": sid or current_sentence_id,
            "is_final": is_final
        })

    def _split_terminated_sentences(text: str):
        """
        Split text into a list of fully terminated sentences and a trailing remainder.
        A sentence is considered terminated if it ends with one of . ! ? (optionally
        followed by quotes/brackets and spaces). This is conservative but effective
        to process multi-sentence utterances promptly.
        """
        s = text or ""
        sentences = []
        n = len(s)
        start = 0
        i = 0
        terminal_set = {'.', '!', '?'}
        trailing = set(['"', "'", ')', ']', '}', '”', '’', ' '])
        while i < n:
            ch = s[i]
            if ch in terminal_set:
                j = i + 1
                # consume trailing quotes/brackets/spaces
                while j < n and s[j] in trailing:
                    j += 1
                sent = s[start:j].strip()
                if sent:
                    sentences.append(sent)
                start = j
                i = j
                continue
            i += 1
        remainder = s[start:].strip()
        return sentences, remainder

    async def _finalize_sentence_and_dispatch(final_text: str, sentence_id_value: str, reason: str = "segmented"):
        """Finalize a single sentence: emit final transcript, extract claim with prior context,
        update rolling context, and schedule verification if a claim is found.
        Does not mutate working_text/current_sentence_id; caller manages those.
        """
        nonlocal context_sentences
        # 1) Send final transcript for this sentence id
        await _send_transcript(final_text, True, sentence_id_value)

        # 2) Build prior context (before appending current) for extraction
        prior_context = " ".join(context_sentences[-CONTEXT_SENTENCES:]) if context_sentences else None
        dprint("DG", f"Finalizing sentence (reason={reason}), extracting claim with prior context…")
        claim_text = await logic.extract_claim(final_text, context_text=prior_context)

        # 3) Update rolling context
        context_sentences.append(final_text)
        if len(context_sentences) > CONTEXT_SENTENCES:
            context_sentences = context_sentences[-CONTEXT_SENTENCES:]

        # 4) Trigger verification if a claim was detected
        if claim_text:
            full_context = " ".join(context_sentences[-CONTEXT_SENTENCES:])
            dprint("DG", f"Claim FOUND; scheduling verify_and_report (id={sentence_id_value})")
            asyncio.create_task(
                verify_and_report(claim_text, full_context, sentence_id_value, user_socket)
            )
        else:
            dprint("DG", "No claim in finalized sentence.")

    async def _finalize_current(local_seq: int, reason: str = "grace"):
        nonlocal working_text, current_sentence_id, update_seq, pending_idle_task, pending_finalize_task, context_sentences
        # Guard: only finalize if no newer updates arrived
        if local_seq != update_seq:
            dprint("DG", f"Finalize skipped (seq changed) reason={reason}")
            return

        final_text = working_text.strip()
        if not final_text:
            dprint("DG", "Finalize skipped (empty text)")
            return

        # Split into fully-terminated sentences and a trailing remainder
        sentences, remainder = _split_terminated_sentences(final_text)
        ids = []
        # First sentence uses current id, subsequent get new ids
        for idx, sent in enumerate(sentences):
            sid = current_sentence_id if idx == 0 else str(uuid.uuid4())
            ids.append(sid)
            await _finalize_sentence_and_dispatch(sent, sid, reason=reason)

        # If there's a remainder (non-terminated), finalize it as well since we're timing out/closing
        if remainder:
            sid = str(uuid.uuid4()) if sentences else current_sentence_id
            await _finalize_sentence_and_dispatch(remainder, sid, reason=reason + ":remainder")

        # Rotate state for next sentence
        working_text = ""
        current_sentence_id = str(uuid.uuid4())

        # Clear timers
        if pending_idle_task and not pending_idle_task.done():
            pending_idle_task.cancel()
        if pending_finalize_task and not pending_finalize_task.done():
            pending_finalize_task.cancel()
        pending_idle_task = None
        pending_finalize_task = None

    async def _schedule_finalize_after(delay: float, local_seq: int, reason: str):
        nonlocal pending_finalize_task
        async def runner():
            try:
                await asyncio.sleep(delay)
                await _finalize_current(local_seq, reason)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                dprint("DG", f"Finalize task error: {e}")
        # Cancel any existing finalize task
        if pending_finalize_task and not pending_finalize_task.done():
            pending_finalize_task.cancel()
        pending_finalize_task = asyncio.create_task(runner())

    async def _schedule_idle_finalize(local_seq: int):
        nonlocal pending_idle_task
        delay = _choose_grace_seconds(working_text)
        async def runner():
            try:
                await asyncio.sleep(delay)
                await _finalize_current(local_seq, reason="idle")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                dprint("DG", f"Idle finalize task error: {e}")
        # Reset idle task
        if pending_idle_task and not pending_idle_task.done():
            pending_idle_task.cancel()
        pending_idle_task = asyncio.create_task(runner())

    async def on_transcript(self, result, **kwargs):
        """
        Event handler: Runs whenever Deepgram processes a chunk of audio.
        """
        nonlocal current_sentence_id, working_text, update_seq

        try:
            # Support both object- and dict-shaped payloads from SDK/events
            sentence = ""
            if isinstance(result, dict):
                sentence = (
                    result.get("channel", {})
                    .get("alternatives", [{"transcript": ""}])[0]
                    .get("transcript", "")
                )
                is_final = result.get("is_final", False)
            else:
                sentence = getattr(getattr(result, "channel", {}), "alternatives", [{}])[0].get(
                    "transcript", ""
                ) if isinstance(getattr(result, "channel", {}), dict) else getattr(
                    getattr(result, "channel", None).alternatives[0], "transcript", ""
                ) if getattr(getattr(result, "channel", None), "alternatives", None) else ""
                # Guard against SDK variations where `is_final` might be absent
                is_final = getattr(result, "is_final", False)

            if not sentence:
                return

            # Optional conservative normalization of the incoming piece
            sentence_norm = _normalize_transcript_piece(sentence)

            # Update live working text (append piece) and segment any fully-terminated sentences
            new_working = (working_text + " " + sentence_norm).strip()
            working_text = new_working

            # Segment into completed sentences and a trailing remainder
            sentences, remainder = _split_terminated_sentences(working_text)

            # If we have any completed sentences, finalize them immediately
            if sentences:
                # Bump sequence so any pending finalize tasks are invalidated
                update_seq += 1
                # Finalize first sentence with current id, others with new ids
                for idx, sent in enumerate(sentences):
                    sid = current_sentence_id if idx == 0 else str(uuid.uuid4())
                    await _finalize_sentence_and_dispatch(sent, sid, reason="segment")
                # After processing, set remainder as new working text and rotate current id
                working_text = remainder
                current_sentence_id = str(uuid.uuid4())

            # Send interim transcript for the current remainder (if any)
            if working_text:
                # Bump sequence for the current interim state
                update_seq += 1
                await _send_transcript(working_text, False, current_sentence_id)

                # Schedule/refresh idle finalize based on current text
                await _schedule_idle_finalize(update_seq)

            # If Deepgram marks this chunk as final, schedule a grace finalize for the remainder
            if is_final and working_text:
                delay = _choose_grace_seconds(working_text)
                dprint("DG", f"Scheduling finalize in {delay:.2f}s (is_final from DG)")
                await _schedule_finalize_after(delay, update_seq, reason="dg_final")

        except Exception as e:
            dprint("DG", f"on_transcript error: {e}")

    # Register the callback and start the Deepgram stream
    async def on_open(self, event, **kwargs):
        dprint("DG", "connection opened")

    async def on_close(self, event=None, **kwargs):
        dprint("DG", "connection closed")

    async def on_error(self, err=None, **kwargs):
        dprint("DG", f"error event: {err}")

    async def on_metadata(self, meta=None, **kwargs):
        dprint("DG", f"metadata: {meta}")

    dg_connection.on(LiveTranscriptionEvents.Open, on_open)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)
    dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
    dprint("WS", "Starting Deepgram websocket stream")
    await dg_connection.start(options)
    dprint("WS", "Deepgram websocket stream started")

    try:
        # Main loop: Receive binary audio data from browser and pipe it to Deepgram
        while True:
            # Wait for audio from frontend
            # dprint("WS", "Waiting for audio bytes from frontend...")
            data = await user_socket.receive_bytes()

            # Forward raw PCM/Opus bytes to Deepgram for processing
            # dprint("WS", f"Forwarding {len(data)} bytes to Deepgram")
            await dg_connection.send(data)

    except Exception as e:
        dprint("WS", f"Error: {e}")
    finally:
        dprint("WS", "Finishing Deepgram websocket stream")
        # Try finalizing any remaining working text before closing connection
        if working_text.strip():
            # Force immediate finalize ignoring sequence changes
            try:
                await _finalize_current(update_seq, reason="ws_close")
            except Exception as e:
                dprint("WS", f"Error finalizing on close: {e}")
        await dg_connection.finish()
        dprint("WS", "WebSocket handler exiting")
