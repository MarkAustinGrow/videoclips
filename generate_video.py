import os
import json
import requests
from typing import List, Dict
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip
from src.database.supabase_client import init_supabase
from datetime import datetime
import shutil
import traceback
import gc

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
    
    # Normalize the text for "oh" patterns
    normalized_text = text.strip().lower()
    words = [word.strip() for word in normalized_text.split(',')]
    is_oh_pattern = all(word == 'oh' for word in words if word)  # Skip empty strings
    
    # First try exact match from same song
    query = supabase.table('video_clips').select('*')
    if song_id:
        print(f"Trying exact match from same song (song_id: {song_id})")
        result = query.eq('song_id', song_id).eq('source_text', text).execute()
        if result.data:
            print("Found exact match from same song!")
            return result.data[0]
    
    # For "oh" patterns, try matching any "oh" sequence from the same song
    if is_oh_pattern and song_id:
        print("Trying to match any 'oh' sequence from same song")
        # Try to find a clip with similar number of "oh"s
        oh_count = len([w for w in words if w == 'oh'])
        print(f"Looking for clips with approximately {oh_count} 'oh's")
        
        # First try clips with exactly the same number of "oh"s
        result = query.eq('song_id', song_id).execute()
        for clip in result.data:
            clip_words = [w.strip().lower() for w in clip['source_text'].split(',')]
            clip_oh_count = len([w for w in clip_words if w == 'oh'])
            if clip_oh_count == oh_count:
                print(f"Found clip with matching number of 'oh's: {clip['source_text']}")
                return clip
        
        # If no exact count match, try any "oh" sequence
        result = query.eq('song_id', song_id).ilike('source_text', '%oh%oh%').execute()
        if result.data:
            print("Found 'oh' sequence match from same song!")
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
    try:
        temp_dir = "temp_clips"
        os.makedirs(temp_dir, exist_ok=True)
        clips = []
        current_batch = []
        batch_size = 5  # Process 5 clips at a time
        
        # Initialize Supabase client
        supabase = init_supabase()
        
        total_segments = len(transcription_data)
        
        for i, segment in enumerate(transcription_data):
            if progress_callback:
                progress_callback(f"Processing segment {i+1}/{total_segments}")
            
            print(f"\n=== Processing segment {i+1}/{total_segments} ===")
            print(f"Segment text: {segment['text']}\n")
            
            try:
                clip = process_segment(segment, song_id, temp_dir, i, supabase)
                if clip:
                    current_batch.append(clip)
                    
                # When batch is full or on last segment, concatenate and clear memory
                if len(current_batch) >= batch_size or i == total_segments - 1:
                    if current_batch:
                        print(f"\nProcessing batch of {len(current_batch)} clips...")
                        batch_video = concatenate_videoclips(current_batch, method="compose")
                        clips.append(batch_video)
                        
                        # Close individual clips to free memory
                        for c in current_batch:
                            c.close()
                        current_batch = []
                        
                        # Force garbage collection
                        gc.collect()
                
            except Exception as e:
                print(f"Error processing segment {i+1}: {str(e)}")
                continue
        
        if not clips:
            raise ValueError("No valid clips were generated")
            
        print("\nConcatenating final video...")
        # Set threads to 1 to avoid CPU overload
        final_video = concatenate_videoclips(clips, method="compose")
        
        output_dir = "generated_videos"
        os.makedirs(output_dir, exist_ok=True)
        output_path = f"{output_dir}/generated_{song_id}.mp4"
        
        print(f"\nWriting final video to {output_path}")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            threads=1,
            fps=24,
            preset='medium',  # Balance between speed and quality
            temp_audiofile=os.path.join(temp_dir, "temp-audio.m4a"),
            remove_temp=True
        )
        
        # Clean up
        print("\nCleaning up...")
        for clip in clips:
            clip.close()
        final_video.close()
        
        # Clear temp directory
        for file in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, file))
            except Exception as e:
                print(f"Error removing temp file {file}: {str(e)}")
        
        return output_path
        
    except Exception as e:
        print(f"Error in generate_video: {str(e)}")
        raise

def process_segment(segment, song_id, temp_dir, index, supabase):
    print(f"Looking for clip matching text: '{segment['text']}'")
    
    try:
        # Find matching clip
        clip_info = find_matching_clip(supabase, segment['text'], song_id)
        
        if clip_info:
            # Get clip URL (prefer internal URL for Docker network)
            clip_url = clip_info.get('internal_url')
            if not clip_url:
                clip_url = clip_info.get('filepath')  # Fallback to external URL
            
            if not clip_url:
                print(f"No valid URL found for clip: {clip_info}")
                return None
                
            temp_clip_path = os.path.join(temp_dir, f"clip_{index:03d}.mp4")
            print(f"Temp clip path: {temp_clip_path}")
            
            if download_clip(clip_url, temp_clip_path):
                print(f"Loading clip into moviepy: {temp_clip_path}")
                print("Creating VideoFileClip object...")
                
                # Set audio to False if the clip doesn't need audio processing
                clip = VideoFileClip(temp_clip_path, audio=True)
                
                print(f"Clip loaded successfully. Duration: {clip.duration}s, Size: {clip.size}")
                print(f"Successfully added clip {index} to sequence\n")
                
                # Track clip usage
                track_clip_usage(supabase, clip_info['id'], song_id, index)
                
                return clip
            else:
                print(f"Failed to download clip from {clip_url}")
                return None
        else:
            print(f"No clip found for segment {index}: {segment['text']}")
            return None
            
    except Exception as e:
        print(f"Error processing segment: {str(e)}")
        return None

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