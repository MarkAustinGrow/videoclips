import os
import json
import requests
from typing import List, Dict
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip
from src.database.supabase_client import init_supabase
from datetime import datetime

def download_clip(url: str, local_path: str) -> bool:
    """Download a clip from URL to local path."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(local_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"Error downloading clip {url}: {str(e)}")
        return False

def find_matching_clip(supabase, text: str, song_id: str = None) -> Dict:
    """Find clips with matching text, optionally from the same song."""
    # First try exact match from same song
    query = supabase.table('video_clips').select('*')
    if song_id:
        result = query.eq('song_id', song_id).eq('source_text', text).execute()
        if result.data:
            return result.data[0]
    
    # Then try exact match from any song
    result = query.eq('source_text', text).execute()
    if result.data:
        return result.data[0]
    
    # If no exact matches, try finding clips with similar text
    # This uses case-insensitive pattern matching
    text_pattern = text.lower().replace("'", "''")  # Escape single quotes
    result = query.ilike('source_text', f"%{text_pattern}%").execute()
    if result.data:
        return result.data[0]
    
    # If still no matches, return any available clip as placeholder
    result = query.limit(1).execute()
    return result.data[0] if result.data else None

def track_clip_usage(supabase, clip_id: str, song_id: str, segment_index: int):
    """Track when and how a clip is used."""
    try:
        # Insert usage record
        usage_data = {
            'clip_id': clip_id,
            'song_id': song_id,
            'order_index': segment_index,
            'used_at': datetime.now().isoformat()
        }
        supabase.table('clip_usages').insert(usage_data).execute()
        
        # Update clip statistics using a regular update
        supabase.table('video_clips').update({
            'times_used': 1,  # We'll handle increment in a trigger
            'last_used_at': datetime.now().isoformat()
        }).eq('id', clip_id).execute()
        
        return True
    except Exception as e:
        print(f"Error tracking clip usage: {str(e)}")
        return False

def generate_video(song_id: str, transcription_data: List[Dict], audio_path: str = None):
    """Generate a video from clips based on transcription data."""
    supabase = init_supabase()
    
    # Create temporary directory for clips
    os.makedirs("temp_clips", exist_ok=True)
    
    try:
        clips = []
        used_clips = set()  # Track clips used in this video
        
        # Process each segment
        for i, segment in enumerate(transcription_data):
            # Try to find clip for this segment
            clip_data = find_matching_clip(supabase, segment['text'], song_id)
            
            if clip_data:
                # Track usage if not already used in this video
                if clip_data['id'] not in used_clips:
                    track_clip_usage(supabase, clip_data['id'], song_id, i)
                    used_clips.add(clip_data['id'])
                
                # Download clip using internal Docker network URL
                local_path = f"temp_clips/clip_{i:03d}.mp4"
                if download_clip(clip_data['filepath'], local_path):  # This should be the internal URL
                    clip = VideoFileClip(local_path)
                    clips.append(clip)
                else:
                    print(f"Failed to download clip for segment {i}")
            else:
                print(f"No clip found for segment {i}: {segment['text']}")
        
        if clips:
            # Concatenate all clips
            final_clip = concatenate_videoclips(clips)
            
            # Add audio if provided
            if audio_path and os.path.exists(audio_path):
                audio = AudioFileClip(audio_path)
                final_clip = final_clip.set_audio(audio)
            
            # Write final video
            output_path = "output_video.mp4"
            final_clip.write_videofile(output_path)
            print(f"Video generated: {output_path}")
            
            # Clean up
            final_clip.close()
            for clip in clips:
                clip.close()
            
            return output_path
        else:
            print("No clips available to generate video")
            return None
            
    except Exception as e:
        print(f"Error generating video: {str(e)}")
        return None
    finally:
        # Clean up temporary files
        for file in os.listdir("temp_clips"):
            try:
                os.remove(os.path.join("temp_clips", file))
            except:
                pass

if __name__ == "__main__":
    # Example usage
    SONG_ID = "b449e6f5-5874-4c5f-99cd-399c762c2b44"  # Dancing Hearts
    
    # Load transcription data
    with open("transcription.json", "r") as f:
        transcription_data = json.load(f)
    
    # Generate video (add audio_path if you have the song audio file)
    output_path = generate_video(SONG_ID, transcription_data)
    if output_path:
        print(f"Video generated successfully at {output_path}") 