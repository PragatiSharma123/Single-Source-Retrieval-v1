import logging
import re
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.services.rag_pipeline import _get_llm
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)
router = APIRouter()

# Map OpenAI frontend voices to ElevenLabs voices
VOICE_MAPPING = {
    "nova": "george", 
    "alloy": "rachel",
    "echo": "drew",
    "fable": "clyde",
    "onyx": "paul",
    "shimmer": "domi"
}

_SPOKEN_REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are a skilled audio narrator for a learning app. "
            "Rewrite the following text as a natural, engaging spoken explanation — "
            "like a knowledgeable teacher talking warmly to a curious student. "
            "Remove ALL markdown (headers, bullets, bold, asterisks, code blocks). "
            "Use smooth transitions. Be clear and engaging. "
            "Return ONLY the spoken script, nothing else."
        ),
    ),
    ("human", "{text}"),
])

def _strip_markdown(text: str) -> str:
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{2,}", ". ", text)
    text = re.sub(r"\n", " ", text)
    return text.strip()

class TTSRequest(BaseModel):
    text: str
    voice: str = "nova"

@router.post("/tts", summary="AI speech via ElevenLabs on OpenRouter")
async def text_to_speech(payload: TTSRequest):
    settings = get_settings()
    
    # Safely map the requested voice to an ElevenLabs equivalent
    elevenlabs_voice = VOICE_MAPPING.get(payload.voice.lower(), "george")

    # Stage 1: LLM rewrite
    llm = _get_llm()
    try:
        chain = _SPOKEN_REWRITE_PROMPT | llm
        result = chain.invoke({"text": payload.text})
        spoken_text = result.content.strip()
    except Exception as exc:
        logger.warning("Audio rewrite failed (%s) — using stripped text.", exc)
        spoken_text = _strip_markdown(payload.text)

    # Stage 2: Stream raw audio via /audio/speech
    url = f"{settings.openrouter_base_url}/audio/speech"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://my-learning-ai-assistant.local",
        "X-Title": "My Learning AI Assistant",
    }
    body = {
        "model": "elevenlabs/eleven-turbo-v2.5",
        "input": spoken_text,
        "voice": elevenlabs_voice,
        "response_format": "mp3"
    }

    async def stream_audio():
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    raw = await resp.aread()
                    logger.error("TTS error: %s", raw.decode())
                    raise HTTPException(status_code=502, detail="Upstream TTS error")
                
                # Yield the raw audio bytes directly to the frontend
                async for chunk in resp.aiter_bytes():
                    yield chunk

    # Return as a streaming MP3 response
    return StreamingResponse(
        stream_audio(), 
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=speech.mp3"}
    )