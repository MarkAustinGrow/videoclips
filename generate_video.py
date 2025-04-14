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
    """
    Generate a video from transcription data and clips.
    
    Args:
        song_id: The ID of the song to generate video for
        transcription_data: List of transcription segments
        progress_callback: Optional callback function(current_segment, message) for progress updates
    
    Returns:
        str: Path to the generated video file, or None if generation failed
    """
    video_sequence = []  # Move this outside try block so finally can access it
    temp_dir = "temp_clips"  # Move this outside try block so finally can access it
    
    try:
        print("\n=== Starting Video Generation ===")
        print(f"Song ID: {song_id}")
        print(f"Number of segments: {len(transcription_data)}")
        print(f"First few segments: {transcription_data[:3]}")  # Debug: show sample of data
        
        # Initialize Supabase client
        supabase = init_supabase()
        
        # Create temp directory for clips
        os.makedirs(temp_dir, exist_ok=True)
        print(f"Created temporary directory: {temp_dir}")
        
        successful_clips = 0  # Track number of successful clips
        failed_clips = 0     # Track number of failed clips
        
        for i, segment in enumerate(transcription_data):
            try:
                segment_text = segment.get('text', '').strip()
                if not segment_text:
                    print(f"Skipping empty segment {i}")
                    continue
                    
                print(f"\n=== Processing segment {i+1}/{len(transcription_data)} ===")
                print(f"Segment text: {segment_text}")
                
                if progress_callback:
                    progress_callback(i, f"Processing segment {i+1}/{len(transcription_data)}")
                
                # Find matching clip
                clip_info = find_matching_clip(supabase, segment_text, song_id)
                
                if clip_info:
                    # Get the correct URL from the clip info - prefer internal URL when running in Docker
                    clip_url = clip_info.get('internal_url') or clip_info.get('filepath')
                    if not clip_url:
                        print(f"No valid URL found for clip: {clip_info}")
                        failed_clips += 1
                        continue
                        
                    temp_clip_path = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
                    print(f"Temp clip path: {temp_clip_path}")
                    
                    try:
                        # Download and add clip to sequence
                        if download_clip(clip_url, temp_clip_path):
                            print(f"Loading clip into moviepy: {temp_clip_path}")
                            try:
                                print("Creating VideoFileClip object...")
                                clip = VideoFileClip(temp_clip_path)
                                print(f"Clip loaded successfully. Duration: {clip.duration}s, Size: {clip.size}")
                                
                                # Verify clip properties
                                if clip.duration < 0.1:
                                    print("Error: Clip duration too short")
                                    clip.close()
                                    continue
                                    
                                if not clip.size or clip.size[0] <= 0 or clip.size[1] <= 0:
                                    print(f"Error: Invalid clip dimensions: {clip.size}")
                                    clip.close()
                                    continue
                                
                                video_sequence.append(clip)
                                print(f"Successfully added clip {len(video_sequence)} to sequence")
                                successful_clips += 1
                                
                                # Track clip usage
                                track_clip_usage(supabase, clip_info['id'], song_id, i)
                            except Exception as e:
                                print(f"Error in moviepy operations: {str(e)}")
                                traceback.print_exc()
                                if os.path.exists(temp_clip_path):
                                    print(f"Clip file size: {os.path.getsize(temp_clip_path)} bytes")
                                continue
                        else:
                            print(f"Failed to download clip from {clip_url}")
                            continue
                    except Exception as e:
                        print(f"Error processing clip: {str(e)}")
                        traceback.print_exc()  # Print full traceback
                        if progress_callback:
                            progress_callback(i, f"Error with clip {i+1}: {str(e)}")
                        failed_clips += 1
                        continue
                else:
                    print(f"No clip found for segment {i}: {segment_text}")
                    if progress_callback:
                        progress_callback(i, f"No clip found for segment {i+1}")
                    failed_clips += 1
            except Exception as e:
                print(f"Error processing segment {i}: {str(e)}")
                traceback.print_exc()
                failed_clips += 1
                continue
        
        print(f"\n=== Clip Processing Summary ===")
        print(f"Successfully processed: {successful_clips} clips")
        print(f"Failed to process: {failed_clips} clips")
        
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
        print(f"Number of clips to concatenate: {len(video_sequence)}")
        print(f"Clip durations: {[clip.duration for clip in video_sequence]}")
        
        final_video = concatenate_videoclips(video_sequence)
        
        if progress_callback:
            progress_callback(len(transcription_data)-1, "Writing final video...")
            
        print(f"Writing video to {output_path}")
        final_video.write_videofile(output_path)
        
        return output_path
        
    except Exception as e:
        print(f"\n=== Error generating video ===")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        traceback.print_exc()
        return None
    finally:
        # Ensure clips are closed and temp files cleaned up
        print("\nCleaning up resources...")
        try:
            for clip in video_sequence:
                try:
                    clip.close()
                except:
                    pass
            if os.path.exists(temp_dir):
                print(f"Removing temporary directory: {temp_dir}")
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")

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