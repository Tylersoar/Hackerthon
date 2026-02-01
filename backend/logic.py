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
import re

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

def _strip_code_fences(s: str) -> str:
    """Remove common markdown code fences and surrounding ticks/quotes."""
    if not s:
        return s
    s = s.strip()
    # Remove triple backtick blocks
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9]*\n?|```$", "", s).strip()
    # Strip remaining single backticks and quotes
    s = s.strip("` ")
    s = s.replace('"', '').replace("'", "").strip()
    return s


def _looks_like_claim(text: str) -> bool:
    """Heuristic to decide if a sentence looks like a verifiable factual claim.

    Conservative but permissive enough to keep the pipeline flowing when the LLM
    is indecisive or returns "NO" too often.
    """
    if not text:
        return False
    t = text.strip()
    # Avoid questions
    if "?" in t:
        return False
    # Minimum length
    if len(t) < 25 and len(t.split()) < 5:
        return False
    tl = t.lower()
    # Avoid obvious opinions
    opinion_markers = [
        "i think", "i believe", "in my opinion", "it seems", "i feel",
    ]
    if any(m in tl for m in opinion_markers):
        return False

    # Signals of factuality: be/have verbs, numbers, dates, measured values, sources
    factual_patterns = [
        r"\b(is|are|was|were|has|have|had|contains|contained|includes|included)\b",
        r"\bfound that\b",
        r"\breported\b",
        r"\bestimated\b",
        r"\baccording to\b",
        r"\bin the year\b",
        r"\b\d{4}\b",            # years
        r"\b\d+(\.\d+)?%\b",    # percentages
        r"\b\d+(,\d{3})+\b",     # large numbers with commas
        r"\b\d+(\.\d+)?\b",     # any number
    ]
    return any(re.search(p, tl) for p in factual_patterns)


async def extract_claim(text: str, context_text: Optional[str] = None) -> Optional[str]:
    """Return a claim string if `text` (the last sentence) contains a
    verifiable factual claim, possibly relying on prior context.

    Model output is made robust to the following possibilities:
    - "NO" → return None
    - "YES" → return the original `text`
    - direct claim string → return that string
    - very short non-NO outputs (e.g., accidental "YES" variants) → fall back to original `text`

    Parameters:
        text: Transcribed last sentence to check (highlight span must come from this).
        context_text: Optional preceding context (e.g., previous 1–3 sentences)
                      to help determine if the last sentence forms a claim when
                      combined with earlier information.

    Returns:
        A claim string (either extracted or the original sentence) when a claim is
        detected; otherwise `None`.

    Logging:
        Emits timing and the raw model output via `dprint`.
    """
    dprint("LOGIC", f"🕵️ Checking if claim: '{text[:50]}...' with context={bool(context_text)}")
    try:
        t0 = time.monotonic()
        # IMPORTANT: Groq SDK is synchronous; run in a worker thread.
        if context_text:
            sys_prompt = (
                "You are a strict claim extraction engine.\n"
                "Input: The immediately preceding context and the last sentence.\n"
                "Task: Decide if the LAST SENTENCE constitutes a grammatically complete, verifiable factual claim\n"
                "on its own OR when combined with the provided context.\n\n"
                "Rules:\n"
                "1. If the last sentence is a FRAGMENT (missing verb/object/value) and context does not fix it → respond with NO.\n"
                "2. If it's an OPINION or QUESTION → respond with NO.\n"
                "3. If there is a COMPLETE verifiable fact, return ONLY the minimal claim text taken FROM THE LAST SENTENCE.\n"
                "   - If the subject is only in context, still select the predicate phrase from the last sentence (do not copy context words).\n"
                "   - Keep it concise; no added explanations.\n\n"
                "Output: Either the exact claim text (from the last sentence) or NO."
            )
            user_prompt = (
                f"Context (may be empty):\n{context_text}\n\n"
                f"Last sentence:\n{text}\n\n"
                "Return only the claim text from the last sentence, or NO."
            )
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ]
        else:
            messages = [
                {
                    "role": "system",
                    "content": """You are a strict claim extraction engine.
        Input: A transcript of spoken audio.
        Task: From the given text, decide if there is a grammatically complete, verifiable factual claim.

        Rules:
        1. If the text is a FRAGMENT (missing verb/object/value) → respond with NO.
        2. If the text is an OPINION or QUESTION → respond with NO.
        3. If there is a COMPLETE verifiable fact, return ONLY the claim text.

        Output: Either the exact claim text, or NO. Do not add explanations.
        """
                },
                {"role": "user", "content": text},
            ]

        completion = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.1,
            max_tokens=80
        )

        raw = completion.choices[0].message.content or ""
        result = _strip_code_fences(raw)

        # Also strip a leading label like "Claim:" if present
        # Keep this conservative to avoid chopping valid content.
        lower = result.lower()
        for prefix in ("claim:", "extracted claim:", "the claim is:", "this is a claim:"):
            if lower.startswith(prefix):
                result = result[len(prefix):].strip()
                lower = result.lower()
                break

        dprint("LOGIC", f"🕵️ Extract raw: {result} (took {time.monotonic() - t0:.2f}s)")

        # Negative responses (more permissive patterns)
        if lower in {"no", "no.", "not", "none"} or lower.startswith("no"):
            # Heuristic fallback: if the sentence looks like a claim, keep it
            permissive = os.getenv("CLAIM_FALLBACK_PERMISSIVE", "1") not in ("0", "false", "False")
            if permissive and (_looks_like_claim(text) or (context_text and _looks_like_claim(f"{context_text} {text}"))):
                dprint("LOGIC", "↩️ Heuristic override: LLM said NO but sentence looks like a claim — using full sentence")
                return text
            return None

        # Explicit YES → treat the whole sentence as the claim
        if lower in {"yes", "yes.", "true"} or lower.startswith("yes"):
            return text

        # If model returned some short token (e.g., "Yes" variants or truncated), fall back to sentence
        if len(result) < 10:
            return text

        return result

    except Exception as e:
        dprint("LOGIC", f"❌ Error in extract_claim: {e}")
        # Fallback: keep the pipeline alive with heuristic if enabled
        if os.getenv("CLAIM_FALLBACK_PERMISSIVE", "1") not in ("0", "false", "False") and _looks_like_claim(text):
            dprint("LOGIC", "↩️ Heuristic override on error: using full sentence as claim")
            return text
        return None

async def verify_claim(claim_text: str, context_text: Optional[str] = None) -> Dict[str, Any]:
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
    # Step 0: Expand the claim using recent context to resolve pronouns/generic nouns (if provided)
    expanded_claim = claim_text
    if context_text:
        try:
            dprint("LOGIC", "🧩 Expanding claim with context...")
            t_expand = time.monotonic()
            expansion = await asyncio.to_thread(
                groq_client.chat.completions.create,
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You rewrite claims to be standalone using the provided context. Return STRICT JSON only.\n\n"
                            "Rules:\n"
                            "- If the claim contains pronouns or generic nouns (e.g., 'they', 'the bears'), and the context unambiguously specifies the referent (e.g., 'polar bears'), replace with the specific term.\n"
                            "- Do NOT introduce new facts not supported by the context.\n"
                            "- Keep the meaning intact and concise.\n"
                            "- If context is ambiguous or insufficient, return the original claim unchanged.\n\n"
                            "Output JSON schema:\n{\n  \"expanded_claim\": string\n}"
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Context (last sentences):\n{context_text}\n\n"
                            f"Claim to rewrite as standalone: {claim_text}\n"
                            "Respond with JSON only."
                        )
                    }
                ],
                temperature=0.0,
                max_tokens=100
            )
            try:
                j = json.loads(expansion.choices[0].message.content.strip())
                ec = (j.get("expanded_claim") or "").strip()
                if 5 <= len(ec) <= 400:
                    expanded_claim = ec
                dprint("LOGIC", f"🧩 Expansion took {time.monotonic() - t_expand:.2f}s; using expanded claim")
            except Exception as je:
                dprint("LOGIC", f"⚠️ Expansion JSON parse failed; using original claim. Error: {je}")
        except Exception as e:
            dprint("LOGIC", f"⚠️ Expansion step failed; using original claim. Error: {e}")

    dprint("LOGIC", f"🌍 Searching Tavily for: '{expanded_claim[:50]}...'")
    try:
        t_search = time.monotonic()
        # Tavily client is synchronous; run it in a worker thread.
        search_response = await asyncio.to_thread(
            tavily_client.search,
            query=expanded_claim,
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
                        "You are a careful, conservative fact-checker. Analyze the claim against the evidence provided.\n\n"
                        "If the evidence is mixed, weak, or insufficient to determine truth, avoid a false negative and respond with an unknown verdict.\n\n"
                        "Respond ONLY with valid JSON in this exact format (no extra text):\n"
                        "{\n"
                        "  \"isTrue\": true | false | null,\n"
                        "  \"explanation\": \"Brief, neutral explanation citing why it is true/false/unknown based on the evidence. If unknown, state that evidence is insufficient.\"\n"
                        "}"
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Claim (standalone): {expanded_claim}\n\n"
                        f"Evidence:\n{evidence_text}\n\n"
                        + (f"Context for reference (optional):\n{context_text}\n\n" if context_text else "")
                        + "Analyze this claim."
                    )
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
            # Normalize to allow null for unknown
            if "isTrue" in analysis and analysis["isTrue"] not in (True, False, None):
                # If model returned string like "unknown", coerce to None
                if isinstance(analysis["isTrue"], str) and analysis["isTrue"].strip().lower() in {"unknown", "uncertain", "not sure", "insufficient"}:
                    analysis["isTrue"] = None
            dprint("LOGIC", f"🧠 Analysis complete: {analysis.get('isTrue')}")
        except json.JSONDecodeError:
            dprint("LOGIC", f"❌ JSON Parse Error")
            analysis = {
                "isTrue": None,
                "explanation": "Unable to parse analysis; verdict unknown"
            }

        return {
            "claim": claim_text,
            "expanded_claim": expanded_claim,
            "evidence": evidence,
            "result": analysis
        }
    except Exception as e:
        dprint("LOGIC", f"❌ Error in verify_claim: {e}")
        return {
            "claim": claim_text,
            "expanded_claim": claim_text,
            "evidence": [],
            "result": {"isTrue": None, "explanation": f"Error: {str(e)}"}
        }