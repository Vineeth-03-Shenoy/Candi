"""
Intent Router - Determines how to handle user messages

Routes messages to either:
1. SIMPLE_CHAT - Direct LLM response (fast, no agents)
2. FULL_PREPARATION - Research → Strategy → Content → PDF (slow, agentic)
3. QUICK_QUESTION - Uses context from previous prep but answers quickly
"""
import os
from openai import OpenAI
from typing import Literal

IntentType = Literal["SIMPLE_CHAT", "FULL_PREPARATION", "QUICK_QUESTION"]


class IntentRouter:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def classify_intent(self, message: str, has_resume: bool = False, has_jd: bool = False) -> IntentType:
        """
        Classify the user's intent based on their message.
        
        Returns:
            - FULL_PREPARATION: User explicitly wants to start interview prep
            - QUICK_QUESTION: User has uploaded docs and asks a specific question
            - SIMPLE_CHAT: General conversation or questions
        """
        # Keywords that trigger full preparation
        prep_keywords = [
            "start preparation", "prepare for interview", "generate guide",
            "create prep", "help me prepare", "interview prep",
            "start interview", "begin preparation", "generate pdf",
            "full analysis", "analyze everything"
        ]
        
        message_lower = message.lower()
        
        # Check for explicit preparation request
        for keyword in prep_keywords:
            if keyword in message_lower:
                return "FULL_PREPARATION"
        
        # If user has uploaded documents and asks a question, use quick question mode
        if has_resume or has_jd:
            # Check if it's a question about the role/interview
            question_indicators = ["?", "what", "how", "why", "when", "where", "which", "can you", "could you", "tell me"]
            if any(indicator in message_lower for indicator in question_indicators):
                return "QUICK_QUESTION"
        
        # Default to simple chat
        return "SIMPLE_CHAT"
    
    async def simple_chat_response(self, message: str, conversation_history: list = None) -> str:
        """
        Generate a quick response without using agents.
        """
        system_prompt = """You are Candi, a friendly AI interview preparation assistant. 
You help candidates prepare for job interviews. Be helpful, concise, and encouraging.
If the user hasn't uploaded their resume and job description yet, gently remind them to do so.
Keep responses under 3 paragraphs unless asked for detail."""

        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history[-10:])  # Last 10 messages for context
        
        messages.append({"role": "user", "content": message})
        
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",  # Fast model for simple chat
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        return response.choices[0].message.content
    
    async def quick_question_response(
        self, 
        message: str, 
        resume_text: str = "", 
        jd_text: str = "",
        prep_context: dict = None
    ) -> str:
        """
        Answer a specific question using the uploaded documents as context.
        """
        system_prompt = """You are Candi, an AI interview preparation assistant.
The user has uploaded their resume and job description. Answer their question based on this context.
Be specific, actionable, and concise. Reference specific details from their documents when relevant."""

        context = f"""
## Resume Summary:
{resume_text[:2000] if resume_text else "Not provided"}

## Job Description Summary:
{jd_text[:2000] if jd_text else "Not provided"}
"""
        
        if prep_context:
            context += f"\n## Previous Preparation Notes:\n{str(prep_context)[:1000]}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {message}"}
        ]
        
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=800,
            temperature=0.7
        )
        
        return response.choices[0].message.content
