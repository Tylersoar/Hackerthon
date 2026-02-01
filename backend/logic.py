"""
Logic layer for fact-checking.

This module provides two async functions used by the WebSocket pipeline in
backend/main.py:

- `extract_claim(text)` — asks an LLM if a sentence is a verifiable factual claim.
- `verify_claim(claim_text)` — searches the web for evidence and asks an LLM to
  evaluate the claim against that evidence, returning a boolean verdict and
  short explanation.

Design notes:
- Simple timestamped `print()`-based logging via `dprint()` (no logging
  framework) to keep developer visibility easy during hacking.
- External services: Groq (LLM) and Tavily (search). API keys are loaded from
  the environment using `python-dotenv`.
- Blocking SDK calls are executed in a thread via `asyncio.to_thread(...)` so
  the async event loop remains responsive.
"""

import os
import asyncio
import json
import uuid
import time
from datetime import datetime
from groq import Groq
from tavily import TavilyClient
from dotenv import load_dotenv
from typing import Any, Dict, List, Optional

load_dotenv()

def _ts() -> str:
    """Return a compact ISO timestamp (to the second) for log lines."""
    return datetime.now().isoformat(timespec="seconds")


def dprint(component: str, message: str) -> None:
    """Lightweight, standardized debug print.

    Format: `[YYYY-MM-DDTHH:MM:SS] [COMPONENT] message`

    Example:
        dprint("LOGIC", "Starting claim extraction")
    """
    print(f"[{_ts()}] [{component}] {message}")


# Initialize external clients once at import time.
# NOTE: These SDKs are synchronous. We call them inside `asyncio.to_thread` to
# avoid blocking the event loop.
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

async def extract_claim(text: str) -> Optional[str]:
    """Return the input `text` if it contains a verifiable factual claim.

    This function delegates to a small Groq prompt that must respond strictly
    with "YES" or "NO". A "YES" means the sentence should be fact-checked;
    in that case we return the original `text`. A "NO" results in `None`.

    Parameters:
        text: Transcribed sentence to check.

    Returns:
        The same `text` when a claim is detected; otherwise `None`.

    Logging:
        Emits timing of the LLM call and the YES/NO result via `dprint`.
    """
    dprint("LOGIC", f"🕵️ Checking if claim: '{text[:50]}...'")
    try:
        t0 = time.monotonic()
        # IMPORTANT: Groq SDK is synchronous; run in a worker thread.
        completion = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """You are a claim detection engine analyzing a live audio stream.
        The input text is a rolling buffer of the last few sentences spoken.
        Determine if the text *contains* a "Verifiable Factual Claim" that has just been completed.

        Respond with ONLY "YES" or "NO".

        Criteria for "YES":
        1. The statement contains specific data, statistics, or numbers (e.g., "Inflation is 10%").
        2. It asserts a specific event, action, or historical fact.
        3. It makes a definitive statement about reality (e.g., "Paris is in France").
        4. Important: If the start of the text is old context, but the *end* of the text completes a new claim, respond YES.

        Criteria for "NO":
        1. Pure opinions ("I think...", "In my opinion").
        2. Future predictions ("It will rain tomorrow").
        3. Vague generalizations ("Life is hard").
        4. Questions or commands.

        If the text contains a specific statistic, ALWAYS respond YES."""
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            temperature=0.0,
            max_tokens=10  # Increased slightly to allow for "YES" with potential whitespace
        )

        is_claim = completion.choices[0].message.content.strip().upper()
        dprint("LOGIC", f"🕵️ Is Claim? {is_claim} (took {time.monotonic() - t0:.2f}s)")

        if "YES" in is_claim:
            return text

        return None
    except Exception as e:
        dprint("LOGIC", f"❌ Error in extract_claim: {e}")
        return None

async def verify_claim(claim_text: str) -> Dict[str, Any]:
    """Verify a factual claim using Tavily search + Groq analysis.

    Steps:
      1. Use Tavily to find a few high-signal sources for the claim.
      2. Concatenate the evidence and ask Groq for a JSON-only verdict
         in the shape: `{ "isTrue": bool, "explanation": str }`.

    Parameters:
        claim_text: The claim string previously returned by `extract_claim`.

    Returns:
        A dictionary with the following structure:
        {
          "claim": str,
          "evidence": List[str],  # raw snippets from Tavily results
          "result": {
            "isTrue": bool,
            "explanation": str
          }
        }

    Logging:
        Emits timings for Tavily and Groq calls, number of sources found,
        a preview of source URLs, and JSON-parse errors when applicable.
    """
    dprint("LOGIC", f"🌍 Searching Tavily for: '{claim_text[:50]}...'")
    try:
        t_search = time.monotonic()
        # Tavily client is synchronous; run it in a worker thread.
        search_response = await asyncio.to_thread(
            tavily_client.search,
            query=claim_text,
            search_depth="advanced",
            max_results=3
        )
        dprint("LOGIC", f"🌍 Tavily search completed in {time.monotonic() - t_search:.2f}s")

        # Normalize search results into `evidence` (content) and `sources` (urls)
        evidence: List[str] = []
        sources: List[str] = []
        for result in search_response.get('results', []):
            content = result.get('content', '')
            url = result.get('url', '')
            if content:
                evidence.append(content)
                sources.append(url)
        
        dprint("LOGIC", f"🌍 Found {len(evidence)} sources")
        if sources:
            preview_urls = ", ".join(sources[:2]) + (" ..." if len(sources) > 2 else "")
            dprint("LOGIC", f"🔗 Sources: {preview_urls}")

        # Build a compact evidence block for the LLM to reason over.
        evidence_text = "\n\n".join([f"Source {i + 1}: {ev}" for i, ev in enumerate(evidence)])

        dprint("LOGIC", f"🧠 Analyzing with Groq...")
        t_analyze = time.monotonic()
        # Ask Groq to return JSON only; we still guard with a parser fallback.
        analysis_completion = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a fact-checker. Analyze the claim against the evidence provided.\n\n"
                        "Respond ONLY with valid JSON in this exact format:\n"
                        "{\n"
                        "    \"isTrue\": true or false,\n"
                        "    \"explanation\": \"Brief explanation why the claim is true/false based on evidence\"\n"
                        "}"
                    )
                },
                {
                    "role": "user",
                    "content": f"Claim: {claim_text}\n\nEvidence:\n{evidence_text}\n\nAnalyze this claim."
                }
            ],
            temperature=0.2,
            max_tokens=300
        )
        dprint("LOGIC", f"🧠 Analysis model call took {time.monotonic() - t_analyze:.2f}s")

        # Parse the analysis
        try:
            # Some models may accidentally include backticks or extra text.
            # We defensively strip whitespace and attempt JSON parsing.
            analysis = json.loads(analysis_completion.choices[0].message.content.strip())
            dprint("LOGIC", f"🧠 Analysis complete: {analysis.get('isTrue')}")
        except json.JSONDecodeError:
            dprint("LOGIC", f"❌ JSON Parse Error")
            analysis = {
                "isTrue": False,
                "explanation": "Unable to parse analysis"
            }

        return {
            "claim": claim_text,
            "evidence": evidence,
            "result": analysis
        }
    except Exception as e:
        dprint("LOGIC", f"❌ Error in verify_claim: {e}")
        return {
            "claim": claim_text,
            "evidence": [],
            "result": {"isTrue": False, "explanation": f"Error: {str(e)}"}
        }