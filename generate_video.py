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
from PIL import Image

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

def get_available_clips(temp_dir):
    """Get a list of available clips from the nginx server"""
    available_clips = []
    base_url = "http://nginx/videos"
    for i in range(100):  # Check first 100 possible clips
        clip_name = f"clip_{i:03d}.mp4"
        try:
            response = requests.head(f"{base_url}/{clip_name}")
            if response.status_code == 200:
                available_clips.append(clip_name)
        except:
            continue
    return available_clips

def get_fallback_clip(text, available_clips, used_clips):
    """Get a fallback clip when the preferred one isn't available"""
    # Try to find a clip that hasn't been used recently
    for clip in available_clips:
        if clip not in used_clips[-5:]:  # Avoid using the same clip in last 5 segments
            return clip
    # If all clips have been used recently, just use the first available one
    return available_clips[0] if available_clips else None

def standardize_clip_size(clip, target_size=(960, 960)):
    """Resize clip to standard dimensions if needed"""
    # Check if clip is None
    if clip is None:
        print("Warning: Cannot resize None clip")
        return None
        
    try:
        # Check if sizes are different
        if clip.size != target_size:
            try:
                # Use basic MoviePy resize without any additional parameters
                resized_clip = clip.resize(width=target_size[0], height=target_size[1])
                print(f"Successfully resized clip from {clip.size} to {target_size}")
                return resized_clip
            except Exception as e:
                print(f"Warning: Could not resize clip ({str(e)}), using original size {clip.size}")
                return clip  # Return original clip if resize fails
        return clip  # Return original clip if already correct size
    except Exception as e:
        print(f"Error in standardize_clip_size: {str(e)}")
        return clip  # Return original clip on any error

def process_image_with_pil(image):
    """Process image using PIL with updated resampling method"""
    if isinstance(image, Image.Image):
        try:
            # Use LANCZOS resampling (replacement for deprecated ANTIALIAS)
            return image.resize(image.size, resample=Image.LANCZOS)
        except AttributeError:
            # Fallback for older Pillow versions
            try:
                return image.resize(image.size, resample=Image.Resampling.LANCZOS)
            except AttributeError:
                # Last resort fallback
                return image
    return image

def generate_video(song_id: str, transcription_data: list, progress_callback=None):
    try:
        temp_dir = "temp_clips"
        os.makedirs(temp_dir, exist_ok=True)
        clips = []
        current_batch = []
        batch_size = 3
        used_clips = []
        target_size = (960, 960)  # Standard size for all clips
        
        # Get list of available clips
        print("\nChecking available clips...")
        available_clips = get_available_clips(temp_dir)
        if not available_clips:
            raise ValueError("No clips available on the server")
        print(f"Found {len(available_clips)} available clips")
        
        # Initialize Supabase client
        supabase = init_supabase()
        
        total_segments = len(transcription_data)
        
        for i, segment in enumerate(transcription_data):
            if progress_callback:
                progress_callback(f"Processing segment {i+1}/{total_segments}")
            
            print(f"\n=== Processing segment {i+1}/{total_segments} ===")
            print(f"Segment text: {segment['text']}\n")
            
            try:
                clip = None
                # First try to get the preferred clip
                preferred_clip = process_segment(segment, song_id, temp_dir, i, supabase)
                
                if preferred_clip is not None and hasattr(preferred_clip, 'get_frame'):
                    clip = standardize_clip_size(preferred_clip, target_size)
                else:
                    # If preferred clip failed, try a fallback
                    fallback_clip_name = get_fallback_clip(segment['text'], available_clips, used_clips)
                    if fallback_clip_name:
                        print(f"Using fallback clip: {fallback_clip_name}")
                        clip_path = os.path.join(temp_dir, f"temp_clip_{i}.mp4")
                        if download_clip(f"http://nginx/videos/{fallback_clip_name}", clip_path):
                            try:
                                raw_clip = VideoFileClip(clip_path)
                                clip = standardize_clip_size(raw_clip, target_size)
                            except Exception as e:
                                print(f"Error loading fallback clip: {str(e)}")
                
                if clip is not None and hasattr(clip, 'get_frame'):
                    print(f"Clip {i+1} loaded successfully")
                    current_batch.append(clip)
                    used_clips.append(fallback_clip_name)
                else:
                    print(f"Warning: Invalid clip generated for segment {i+1}")
                    continue
                    
                # When batch is full or on last segment, concatenate and clear memory
                if len(current_batch) >= batch_size or i == total_segments - 1:
                    if current_batch:
                        print(f"\nProcessing batch of {len(current_batch)} clips...")
                        try:
                            # Validate all clips in batch before concatenating
                            valid_clips = [c for c in current_batch if c is not None and hasattr(c, 'get_frame')]
                            if valid_clips:
                                batch_video = concatenate_videoclips(valid_clips, method="compose")
                                if batch_video is not None and hasattr(batch_video, 'get_frame'):
                                    clips.append(batch_video)
                                else:
                                    print("Warning: Invalid batch video generated")
                            else:
                                print("Warning: No valid clips in current batch")
                                
                            # Close individual clips to free memory
                            for c in current_batch:
                                try:
                                    if c is not None:
                                        c.close()
                                except Exception as e:
                                    print(f"Warning: Error closing clip: {str(e)}")
                            
                            current_batch = []
                            # Force garbage collection
                            gc.collect()
                            
                        except Exception as e:
                            print(f"Error processing batch: {str(e)}")
                            # Clean up failed batch
                            for c in current_batch:
                                try:
                                    if c is not None:
                                        c.close()
                                except:
                                    pass
                            current_batch = []
                            gc.collect()
                
            except Exception as e:
                print(f"Error processing segment {i+1}: {str(e)}")
                continue
        
        if not clips:
            raise ValueError("No valid clips were generated")
            
        print("\nConcatenating final video...")
        # Validate final clips before concatenating
        valid_final_clips = [c for c in clips if c is not None and hasattr(c, 'get_frame')]
        if not valid_final_clips:
            raise ValueError("No valid clips available for final video")
            
        # Set threads to 1 to avoid CPU overload
        final_video = concatenate_videoclips(valid_final_clips, method="compose")
        if final_video is None or not hasattr(final_video, 'get_frame'):
            raise ValueError("Failed to generate final video")
        
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
            try:
                if clip is not None:
                    clip.close()
            except Exception as e:
                print(f"Warning: Error closing clip: {str(e)}")
        
        if final_video is not None:
            try:
                final_video.close()
            except Exception as e:
                print(f"Warning: Error closing final video: {str(e)}")
        
        # Clear temp directory
        for file in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, file))
            except Exception as e:
                print(f"Error removing temp file {file}: {str(e)}")
        
        return output_path
        
    except Exception as e:
        print(f"Error in generate_video: {str(e)}")
        # Ensure cleanup on error
        try:
            for clip in clips:
                if clip is not None:
                    clip.close()
        except:
            pass
        gc.collect()
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
