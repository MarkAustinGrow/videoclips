import os
from dotenv import load_dotenv
from src.database.supabase_client import init_supabase
from src.video.processor import VideoProcessor
from src.ai.openai_client import init_openai

# Load environment variables
load_dotenv()

def main():
    # Initialize clients
    supabase = init_supabase()
    openai = init_openai()
    
    # Initialize video processor
    video_processor = VideoProcessor()
    
    print("AI K-Pop Music Video Generator initialized successfully!")
    print("Ready to process videos and generate clips.")

if __name__ == "__main__":
    main() 