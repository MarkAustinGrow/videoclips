import os
import json
import requests
from typing import List, Dict
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip
from src.database.supabase_client import init_supabase
from datetime import datetime
import shutil
import traceback

def download_clip(url: str, local_path: str) -> bool:
    """Download a clip from URL to local path."""
    try:
        print(f"Downloading clip from {url} to {local_path}")
        response = requests.get(url)
        response.raise_for_status()
        with open(local_path, 'wb') as f:
            f.write(response.content)
        print(f"Successfully downloaded clip: {local_path}")
        return True
    except Exception as e:
        print(f"Error downloading clip {url}: {str(e)}")
        return False

def find_matching_clip(supabase, text: str, song_id: str = None) -> Dict:
    """Find clips with matching text, optionally from the same song."""
    print(f"\nLooking for clip matching text: '{text}'")
    
    # First try exact match from same song
    query = supabase.table('video_clips').select('*')
    if song_id:
        print(f"Trying exact match from same song (song_id: {song_id})")
        result = query.eq('song_id', song_id).eq('source_text', text).execute()
        if result.data:
            print("Found exact match from same song!")
            return result.data[0]
    
    # Then try exact match from any song
    print("Trying exact match from any song")
    result = query.eq('source_text', text).execute()
    if result.data:
        print("Found exact match from different song!")
        return result.data[0]
    
    # If no exact matches, try finding clips with similar text
    print("Trying fuzzy text matching")
    text_pattern = text.lower().replace("'", "''")  # Escape single quotes
    result = query.ilike('source_text', f"%{text_pattern}%").execute()
    if result.data:
        print("Found clip with similar text!")
        return result.data[0]
    
    print("No matching clips found")
    return None

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

def generate_video(song_id: str, transcription_data: list, progress_callback=None):
    """
    Generate a video from transcription data and clips.
    
    Args:
        song_id: The ID of the song to generate video for
        transcription_data: List of transcription segments
        progress_callback: Optional callback function(current_segment, message) for progress updates
    
    Returns:
        str: Path to the generated video file, or None if generation failed
    """
    try:
        print("\n=== Starting Video Generation ===")
        print(f"Song ID: {song_id}")
        print(f"Number of segments: {len(transcription_data)}")
        
        # Initialize Supabase client
        supabase = init_supabase()
        
        # Create temp directory for clips
        temp_dir = "temp_clips"
        os.makedirs(temp_dir, exist_ok=True)
        print(f"Created temporary directory for clips")
        
        # Initialize video sequence
        video_sequence = []
        
        for i, segment in enumerate(transcription_data):
            segment_text = segment.get('text', '').strip()
            if not segment_text:
                continue
                
            print(f"\nProcessing segment {i}: {segment_text}")
            if progress_callback:
                progress_callback(i, f"Processing segment {i+1}/{len(transcription_data)}")
            
            # Find matching clip
            clip_info = find_matching_clip(supabase, segment_text, song_id)
            
            if clip_info:
                # Get the correct URL from the clip info
                clip_url = clip_info.get('filepath') or clip_info.get('public_url')
                if not clip_url:
                    print(f"No valid URL found for clip: {clip_info}")
                    continue
                    
                temp_clip_path = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
                
                try:
                    # Download and add clip to sequence
                    if download_clip(clip_url, temp_clip_path):
                        print(f"Loading clip into moviepy: {temp_clip_path}")
                        
                        clip = VideoFileClip(temp_clip_path)
                        video_sequence.append(clip)
                        print("Successfully added clip to sequence")
                        
                        # Track clip usage
                        track_clip_usage(supabase, clip_info['id'], song_id, i)
                    else:
                        print(f"Failed to download clip from {clip_url}")
                except Exception as e:
                    print(f"Error processing clip: {str(e)}")
                    if progress_callback:
                        progress_callback(i, f"Error with clip {i+1}: {str(e)}")
                    continue
            else:
                print(f"No clip found for segment {i}: {segment_text}")
                if progress_callback:
                    progress_callback(i, f"No clip found for segment {i+1}")
        
        if not video_sequence:
            print("No clips were found to generate video")
            return None
            
        # Generate output path
        output_dir = "generated_videos"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"generated_{song_id}.mp4")
        
        if progress_callback:
            progress_callback(len(transcription_data)-1, "Concatenating clips...")
            
        print("\nConcatenating clips...")
        final_video = concatenate_videoclips(video_sequence)
        
        if progress_callback:
            progress_callback(len(transcription_data)-1, "Writing final video...")
            
        print(f"Writing video to {output_path}")
        final_video.write_videofile(output_path)
        
        # Clean up
        print("\nCleaning up temporary files...")
        for clip in video_sequence:
            clip.close()
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        return output_path
        
    except Exception as e:
        print(f"\nError generating video: {str(e)}")
        traceback.print_exc()
        return None
    finally:
        # Ensure clips are closed and temp files cleaned up
        try:
            for clip in video_sequence:
                clip.close()
            shutil.rmtree(temp_dir, ignore_errors=True)
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