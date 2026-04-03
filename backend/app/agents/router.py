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
        self, message: str, conversation_history: list = None
    ) -> str:
        """Generate a quick response without using agents."""
        history_len = len(conversation_history) if conversation_history else 0
        log.info("simple_chat_response | history_messages=%d", history_len)

        system_prompt = (
            "You are Candi, a friendly AI interview preparation assistant. "
            "You help candidates prepare for job interviews. Be helpful, concise, and encouraging. "
            "If the user hasn't uploaded their resume and job description yet, gently remind them to do so. "
            "Keep responses under 3 paragraphs unless asked for detail."
        )

        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history[-10:])
        messages.append({"role": "user", "content": message})

        log.debug("Calling OpenAI gpt-4o-mini for simple chat (%d total messages)", len(messages))
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )

        reply = response.choices[0].message.content
        log.info("simple_chat_response complete | reply_length=%d chars", len(reply))
        return reply

    async def quick_question_response(
        self,
        message: str,
        resume_text: str = "",
        jd_text: str = "",
        prep_context: dict = None,
    ) -> str:
        """Answer a specific question using the uploaded documents as context."""
        log.info(
            "quick_question_response | has_resume=%s has_jd=%s has_prep_context=%s",
            bool(resume_text), bool(jd_text), bool(prep_context),
        )

        system_prompt = (
            "You are Candi, an AI interview preparation assistant. "
            "The user has uploaded their resume and job description. Answer their question based on this context. "
            "Be specific, actionable, and concise. Reference specific details from their documents when relevant."
        )

        context = (
            f"## Resume Summary:\n{resume_text[:2000] if resume_text else 'Not provided'}\n\n"
            f"## Job Description Summary:\n{jd_text[:2000] if jd_text else 'Not provided'}\n"
        )
        if prep_context:
            context += f"\n## Previous Preparation Notes:\n{str(prep_context)[:1000]}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {message}"},
        ]

        log.debug("Calling OpenAI gpt-4o-mini for quick question (%d messages)", len(messages))
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=800,
            temperature=0.7,
        )

        reply = response.choices[0].message.content
        log.info("quick_question_response complete | reply_length=%d chars", len(reply))
        return reply
