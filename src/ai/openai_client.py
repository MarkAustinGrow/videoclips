import os
from openai import OpenAI

def init_openai() -> OpenAI:
    """Initialize OpenAI client with API key from environment variables."""
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        raise ValueError("Missing OpenAI API key in environment variables")
    
    return OpenAI(api_key=api_key) 