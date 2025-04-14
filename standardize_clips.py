import os
import tempfile
import requests
from dotenv import load_dotenv
from moviepy.editor import VideoFileClip
import shutil
from src.database.supabase_client import init_supabase

# Load environment variables
load_dotenv()

# Target resolution
TARGET_RESOLUTION = (960, 960)

def download_clip(url, local_path):
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

def resize_clip(clip_path, target_size=TARGET_RESOLUTION):
    """Resize video clip to target dimensions."""
    try:
        clip = VideoFileClip(clip_path)
        original_size = clip.size
        
        # Only resize if needed
        if original_size != target_size:
            print(f"Resizing clip from {original_size} to {target_size}")
            
            # Use ffmpeg directly to avoid PIL issues
            temp_output = f"{clip_path}_temp.mp4"
            ffmpeg_cmd = f"ffmpeg -i {clip_path} -vf scale={target_size[0]}:{target_size[1]} -c:v libx264 -c:a aac -y {temp_output}"
            
            print(f"Running command: {ffmpeg_cmd}")
            os.system(ffmpeg_cmd)
            
            # Close the clip
            clip.close()
            
            # Check if the resized file exists and has content
            if os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
                # Replace original with resized
                os.remove(clip_path)
                os.rename(temp_output, clip_path)
                print(f"Successfully resized clip to {target_size}")
                return True, original_size
            else:
                print(f"Failed to resize clip: output file not created or empty")
                return False, original_size
        else:
            print(f"Clip already at target size {target_size}")
            clip.close()
            return False, original_size
    except Exception as e:
        print(f"Error resizing clip: {str(e)}")
        try:
            if 'clip' in locals() and clip is not None:
                clip.close()
        except:
            pass
        return False, None

def upload_to_server(local_path, remote_filename):
    """Upload a file to the nginx videos directory."""
    try:
        # Create the videos directory if it doesn't exist
        nginx_videos_dir = '/usr/share/nginx/html/videos'
        os.makedirs(nginx_videos_dir, exist_ok=True)
        
        # Copy the file to the nginx directory
        remote_path = os.path.join(nginx_videos_dir, remote_filename)
        shutil.copy2(local_path, remote_path)
        
        # Return both internal and external URLs
        return {
            'internal_url': f'http://nginx/videos/{remote_filename}',  # For Docker network
            'external_url': f'http://172.236.1.244/videos/{remote_filename}'  # For public access
        }
    except Exception as e:
        print(f"Upload failed: {str(e)}")
        return None

def main():
    # Initialize Supabase client
    supabase = init_supabase()
    
    # Create temp directory
    temp_dir = "temp_standardize"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # Get all clips from database
        response = supabase.table('video_clips').select('*').execute()
        clips = response.data
        
        print(f"Found {len(clips)} clips in database")
        
        # Process each clip
        for clip in clips:
            clip_id = clip['id']
            filename = clip['filename']
            internal_url = clip.get('internal_url')
            filepath = clip.get('filepath')
            
            # Use internal URL if available, otherwise use filepath
            url = internal_url if internal_url else filepath
            
            if not url:
                print(f"No URL found for clip {filename}, skipping")
                continue
                
            print(f"\nProcessing clip: {filename}")
            
            # Download clip
            temp_path = os.path.join(temp_dir, filename)
            if not download_clip(url, temp_path):
                print(f"Failed to download clip {filename}, skipping")
                continue
            
            # Resize clip
            was_resized, original_size = resize_clip(temp_path)
            
            if was_resized or not clip.get('width'):
                # Upload back to server
                urls = upload_to_server(temp_path, filename)
                
                if urls:
                    # Update database record
                    supabase.table('video_clips').update({
                        'width': TARGET_RESOLUTION[0],
                        'height': TARGET_RESOLUTION[1],
                        'original_resolution': f"{original_size[0]}x{original_size[1]}" if original_size else None
                    }).eq('id', clip_id).execute()
                    
                    print(f"Successfully standardized clip {filename}")
                else:
                    print(f"Failed to upload standardized clip {filename}")
            else:
                print(f"Clip {filename} already at target resolution, no update needed")
            
            # Clean up
            os.remove(temp_path)
    
    except Exception as e:
        print(f"Error in main process: {str(e)}")
    
    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("\nStandardization process complete")

if __name__ == "__main__":
    main()
