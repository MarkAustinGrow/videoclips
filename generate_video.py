import os
import json
import requests
from typing import List, Dict
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip
from src.database.supabase_client import init_supabase

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
    """Find a clip with matching text, optionally from the same song."""
    query = supabase.table('video_clips').select('*').eq('source_text', text)
    if song_id:
        query = query.eq('song_id', song_id)
    
    result = query.execute()
    return result.data[0] if result.data else None

def generate_video(song_id: str, transcription_data: List[Dict], audio_path: str = None):
    """Generate a video from clips based on transcription data."""
    supabase = init_supabase()
    
    # Create temporary directory for clips
    os.makedirs("temp_clips", exist_ok=True)
    
    try:
        clips = []
        
        # Process each segment
        for i, segment in enumerate(transcription_data):
            # Try to find clip for this segment
            clip_data = find_matching_clip(supabase, segment['text'], song_id)
            
            if not clip_data:
                # Try to find matching clip from any song
                clip_data = find_matching_clip(supabase, segment['text'])
            
            if clip_data:
                # Download clip
                local_path = f"temp_clips/clip_{i:03d}.mp4"
                if download_clip(clip_data['filepath'], local_path):
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