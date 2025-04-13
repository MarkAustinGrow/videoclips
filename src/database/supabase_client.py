import os
from supabase import create_client, Client
from supabase.client import ClientOptions

def init_supabase() -> Client:
    """Initialize Supabase client with environment variables."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        raise ValueError("Missing Supabase credentials in environment variables")
    
    try:
        return create_client(
            url,
            key,
            options=ClientOptions(
                schema="public",
                postgrest_client_timeout=10,
                storage_client_timeout=10
            )
        )
    except Exception as e:
        print(f"Error initializing Supabase client: {str(e)}")
        raise 