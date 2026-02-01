import os
import asyncio
import json
import uuid
from groq import Groq
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

# Initialize clients exactly as you had them
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# def process_sentence_logic(sentence):
#     """
#     Runs the exact Claim Check -> Tavily -> Fact Check flow from your original script.
#     """
#     # 1. Check if sentence contains a claim
#     completion = groq_client.chat.completions.create(
#         model="llama-3.3-70b-versatile",
#         messages=[
#             {
#                 "role": "system",
#                 "content": "Respond with only 'YES' or 'NO': Is this a verifiable factual claim?"
#             },
#             {
#                 "role": "user",
#                 "content": sentence
#             }
#         ],
#         temperature=0.1,
#         max_tokens=10
#     )
#
#     is_claim = completion.choices[0].message.content.strip().upper()
#
#     if is_claim != "YES":
#         return None
#
#     # Generate unique ID for this claim
#     claim_id = str(uuid.uuid4())
#
#     # 2. Search with Tavily
#     search_response = tavily_client.search(
#         query=sentence,
#         search_depth="advanced",
#         max_results=3
#     )
#
#     evidence = []
#     sources = []
#     for result in search_response.get('results', []):
#         content = result.get('content', '')
#         url = result.get('url', '')
#         if content:
#             evidence.append(content)
#             sources.append(url)
#
#     # 3. Analyze with Groq
#     evidence_text = "\n\n".join([f"Source {i + 1}: {ev}" for i, ev in enumerate(evidence)])
#
#     analysis_completion = groq_client.chat.completions.create(
#         model="llama-3.3-70b-versatile",
#         messages=[
#             {
#                 "role": "system",
#                 "content": """You are a fact-checker. Analyze the claim against the evidence provided.
#
# Respond ONLY with valid JSON in this exact format:
# {
#     "isTrue": true or false,
#     "explanation": "Brief explanation why the claim is true/false based on evidence"
# }"""
#             },
#             {
#                 "role": "user",
#                 "content": f"Claim: {sentence}\n\nEvidence:\n{evidence_text}\n\nAnalyze this claim."
#             }
#         ],
#         temperature=0.2,
#         max_tokens=300
#     )
#
#     # Parse the analysis
#     try:
#         analysis = json.loads(analysis_completion.choices[0].message.content.strip())
#     except json.JSONDecodeError:
#         analysis = {
#             "isTrue": False,
#             "explanation": "Unable to parse analysis"
#         }
#
#     # Return everything needed for the message
#     return {
#         "id": claim_id,
#         "claim": sentence,
#         "evidence": evidence,
#         "result": analysis
#     }

# ------- LEGACY ABOVE ------

async def extract_claim(text):

    completion = await asyncio.to_thread(
        groq_client.chat.completions.create,
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Respond with only 'YES' or 'NO': Is this a verifiable factual claim?"},
            {"role": "user", "content": text}
        ],
        temperature=0.1,
        max_tokens=10
    )

    is_claim = completion.choices[0].message.content.strip().upper()

    if is_claim != "YES":
        return None

    return text

async def verify_claim(claim_text):
    search_response = await asyncio.to_thread(
        tavily_client.search,
        query=claim_text,
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

    evidence_text = "\n\n".join([f"Source {i + 1}: {ev}" for i, ev in enumerate(evidence)])

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

    # Parse the analysis
    try:
        analysis = json.loads(analysis_completion.choices[0].message.content.strip())
    except json.JSONDecodeError:
        analysis = {
            "isTrue": False,
            "explanation": "Unable to parse analysis"
        }

    return {
        "claim": claim_text,
        "evidence": evidence,
        "result": analysis
    }