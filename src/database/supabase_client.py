import os
from supabase import create_client, Client

def init_supabase() -> Client:
    """Initialize Supabase client with environment variables."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        raise ValueError("Missing Supabase credentials in environment variables")
    
    return create_client(url, key) 