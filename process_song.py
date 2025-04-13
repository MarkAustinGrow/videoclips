import os
import json
from dotenv import load_dotenv
from src.database.supabase_client import init_supabase
from src.video.processor import VideoProcessor

# Load environment variables
load_dotenv()

def process_song(song_id: str, input_video_path: str, transcription_data: list):
    """Process a song's video into clips and upload metadata."""
    supabase = init_supabase()
    processor = VideoProcessor()
    
    # Split the video into clips
    print(f"Splitting video into clips: {input_video_path}")
    processor.split_video(input_video_path)
    
    # Process clip metadata
    print("Processing clip metadata...")
    clips_metadata = processor.process_clips_with_timestamps(song_id, transcription_data)
    
    # Validate and upload each clip's metadata
    for clip in clips_metadata:
        clip_path = os.path.join(processor.clips_dir, clip['filename'])
        
        if processor.validate_clip(clip_path):
            print(f"Uploading metadata for clip: {clip['filename']}")
            
            # Insert clip metadata into video_clips table
            supabase.table('video_clips').insert({
                'filename': clip['filename'],
                'filepath': f"/videos/{clip['filename']}",
                'song_id': clip['song_id'],
                'start_time': clip['start_time'],
                'end_time': clip['end_time'],
                'order_index': clip['order_index']
            }).execute()
        else:
            print(f"Warning: Invalid clip or missing file: {clip_path}")

if __name__ == "__main__":
    # Example usage
    SONG_ID = "c492d4c1-bba8-40eb-934a-3240e1624be6"  # Summer Electric
    VIDEO_PATH = "input/summer_electric.mp4"  # Replace with your video path
    
    # Load transcription data from the example
    TRANSCRIPTION_DATA = json.loads('''[{"end": 8.479999542236328, "text": "", "start": 0.3199999928474426}, ...]''')  # Your transcription data
    
    process_song(SONG_ID, VIDEO_PATH, TRANSCRIPTION_DATA) 