"""
Intent Router - Determines how to handle user messages

Routes messages to either:
1. SIMPLE_CHAT    - Direct LLM response (fast, no agents)
2. FULL_PREPARATION - Research → Strategy → Content → PDF (slow, agentic)
3. QUICK_QUESTION - Uses context from previous prep but answers quickly
"""
import os
from openai import OpenAI
from typing import Literal

from app.utils.logger import get_logger
from app.utils.llm_logger import llm_call

log = get_logger(__name__)

IntentType = Literal["SIMPLE_CHAT", "FULL_PREPARATION", "QUICK_QUESTION"]


class IntentRouter:
    def __init__(self):
        log.debug("Initialising IntentRouter")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def classify_intent(
        self, message: str, has_resume: bool = False, has_jd: bool = False
    ) -> IntentType:
        """Classify the user's intent based on their message."""
        log.info("Classifying intent | has_resume=%s has_jd=%s | message='%s'",
                 has_resume, has_jd, message[:120])

        prep_keywords = [
            "start preparation", "prepare for interview", "generate guide",
            "create prep", "help me prepare", "interview prep",
            "start interview", "begin preparation", "generate pdf",
            "full analysis", "analyze everything",
        ]

        message_lower = message.lower()

        for keyword in prep_keywords:
            if keyword in message_lower:
                log.info("Intent classified as FULL_PREPARATION (keyword match: '%s')", keyword)
                return "FULL_PREPARATION"

        if has_resume or has_jd:
            question_indicators = [
                "?", "what", "how", "why", "when", "where", "which",
                "can you", "could you", "tell me",
            ]
            if any(ind in message_lower for ind in question_indicators):
                log.info("Intent classified as QUICK_QUESTION (docs present + question indicators)")
                return "QUICK_QUESTION"

        log.info("Intent classified as SIMPLE_CHAT (default)")
        return "SIMPLE_CHAT"

    async def simple_chat_response(
        self,
        message: str,
        session_id: str,
        retriever,
        conversation_history: list = None,
    ) -> tuple[str, dict]:
        """Generate a response with context retrieved from the vector store."""
        history_len = len(conversation_history) if conversation_history else 0
        log.info("simple_chat_response | session_id=%s | history_messages=%d", session_id, history_len)

        system_prompt = (
            "You are Candi, a friendly AI interview preparation assistant. "
            "You help candidates prepare for job interviews. Be helpful, concise, and encouraging. "
            "If the user hasn't uploaded their resume and job description yet, gently remind them to do so. "
            "Keep responses under 3 paragraphs unless asked for detail."
        )

        # Retrieve context from vector store
        context = retriever.get_context(session_id, message, top_k=5)
        if context:
            log.debug("Retrieved context from vector store | context_length=%d", len(context))
            system_prompt += f"\n\n{context}"

        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history[-10:])
        messages.append({"role": "user", "content": message})

        model       = os.getenv("ROUTER_SIMPLE_CHAT_MODEL",       "gpt-4o-mini")
        max_tokens  = int(os.getenv("ROUTER_SIMPLE_CHAT_MAX_TOKENS",  "500"))
        temperature = float(os.getenv("ROUTER_SIMPLE_CHAT_TEMPERATURE", "0.7"))
        log.debug("Calling %s for simple chat (%d total messages)", model, len(messages))
        response, tokens = llm_call(
            self.client, __name__,
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        reply = response.choices[0].message.content
        log.info("simple_chat_response complete | reply_length=%d chars", len(reply))
        return reply, tokens

    async def quick_question_response(
        self,
        message: str,
        session_id: str,
        retriever,
        resume_text: str = "",
        jd_text: str = "",
        prep_context: dict = None,
        conversation_history: list = None,
    ) -> tuple[str, dict]:
        """Answer a question with context from the vector store and uploaded docs."""
        history_len = len(conversation_history) if conversation_history else 0
        log.info(
            "quick_question_response | session_id=%s | has_resume=%s has_jd=%s has_prep_context=%s | history_messages=%d",
            session_id, bool(resume_text), bool(jd_text), bool(prep_context), history_len,
        )

        system_prompt = (
            "You are Candi, an AI interview preparation assistant. "
            "The candidate's resume and job description are provided below — use them as your primary source of truth.\n\n"
            "RULES:\n"
            "- NEVER use placeholder text like [Project Name], [Company Name], [specific outcome], or [X%].\n"
            "- ALWAYS use the candidate's real project names, companies, technologies, and metrics from their resume.\n"
            "- When showing how to answer a question, write the full sample answer as if the candidate is speaking, "
            "using their actual experience. Do not leave anything for them to fill in.\n"
            "- If the resume lacks a specific detail, say so honestly — do not invent placeholders."
        )

        # Always inject full resume + JD so the LLM has real details to reference
        if resume_text:
            system_prompt += f"\n\n## Candidate Resume:\n{resume_text[:4000]}"
        if jd_text:
            system_prompt += f"\n\n## Job Description:\n{jd_text[:2000]}"

        # Pull supplementary context from vector store (prep guide, rounds, strategy, etc.)
        vs_context = retriever.get_context(session_id, message, top_k=5)
        if vs_context:
            log.debug("Retrieved supplementary context from vector store | context_length=%d", len(vs_context))
            system_prompt += f"\n\n## Prep Guide Context (use to supplement the answer):\n{vs_context}"
        elif prep_context:
            log.debug("No vector store context | appending prep_context dict as fallback")
            system_prompt += f"\n\n## Previous Preparation Notes:\n{str(prep_context)[:1000]}"

        messages = [{"role": "system", "content": system_prompt}]
        # Include recent conversation so follow-up questions have full context
        if conversation_history:
            messages.extend(conversation_history[-10:])
        messages.append({"role": "user", "content": message})

        model       = os.getenv("ROUTER_QUICK_QA_MODEL",       "gpt-4o-mini")
        max_tokens  = int(os.getenv("ROUTER_QUICK_QA_MAX_TOKENS",  "1200"))
        temperature = float(os.getenv("ROUTER_QUICK_QA_TEMPERATURE", "0.7"))
        log.debug("Calling %s for quick question (%d total messages)", model, len(messages))
        response, tokens = llm_call(
            self.client, __name__,
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        reply = response.choices[0].message.content
        log.info("quick_question_response complete | reply_length=%d chars", len(reply))
        return reply, tokens
