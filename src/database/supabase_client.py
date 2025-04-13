import os
from supabase import create_client, Client
from typing import Dict, Any

def init_supabase() -> Client:
    """Initialize Supabase client with environment variables."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        raise ValueError("Missing Supabase credentials in environment variables")
    
    try:
        # Create options with proper structure
        options: Dict[str, Any] = {
            'schema': 'public',
            'headers': {
                'X-Client-Info': 'supabase-py/1.2.0'
            },
            'auth': {
                'persistSession': False
            }
        }
        
        return create_client(url, key, options)
    except Exception as e:
        print(f"Error initializing Supabase client: {str(e)}")
        raise 