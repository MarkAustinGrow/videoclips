import os
import json
import streamlit as st
import shutil
import tempfile
from dotenv import load_dotenv
from src.database.supabase_client import init_supabase
from generate_video import generate_video, find_matching_clip
from moviepy.editor import VideoFileClip

# Load environment variables
load_dotenv()

def upload_to_server(local_path: str, remote_filename: str):
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
        st.error(f"Upload failed: {str(e)}")
        return None

def check_and_standardize_resolution(clip_file, target_resolution=(960, 960)):
    """
    Check clip resolution and resize if needed.
    Returns: (temp_path, original_resolution, was_resized)
    """
    # Save uploaded file to a temporary location
    temp_fd, temp_path = tempfile.mkstemp(suffix='.mp4')
    os.close(temp_fd)
    
    with open(temp_path, "wb") as f:
        f.write(clip_file.getvalue())
    
    # Check resolution
    clip = VideoFileClip(temp_path)
    original_resolution = clip.size
    
    # If resolution doesn't match target, resize
    if original_resolution != target_resolution:
        st.warning(f"Resizing clip from {original_resolution} to {target_resolution}")
        
        try:
            # Create a new resized clip
            resized_clip = clip.resize(width=target_resolution[0], height=target_resolution[1])
            
            # Close original clip
            clip.close()
            
            # Save resized clip
            resized_path = temp_path + "_resized.mp4"
            resized_clip.write_videofile(
                resized_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=temp_path + "_audio.m4a",
                remove_temp=True
            )
            
            # Close resized clip
            resized_clip.close()
            
            # Replace original with resized
            os.remove(temp_path)
            os.rename(resized_path, temp_path)
            
            return temp_path, original_resolution, True
        except Exception as e:
            st.error(f"Error resizing clip: {str(e)}")
            clip.close()
            return temp_path, original_resolution, False
    
    # Close clip to free memory
    clip.close()
    return temp_path, original_resolution, False

def get_file_size(file_path: str) -> int:
    """Get file size in bytes."""
    return os.path.getsize(file_path)

def fetch_songs(supabase):
    """Fetch all songs from Supabase."""
    try:
        response = supabase.table('songs').select('id, title').execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching songs: {str(e)}")
        return []

def get_transcription(supabase, song_id: str):
    """Fetch transcription data for a song from Supabase."""
    try:
        response = supabase.table('songs').select('transcribed').eq('id', song_id).single().execute()
        if response.data and response.data.get('transcribed'):
            transcribed_data = response.data['transcribed']
            # Handle both string (JSON) and list data types
            if isinstance(transcribed_data, str):
                return json.loads(transcribed_data)
            elif isinstance(transcribed_data, list):
                return transcribed_data
            else:
                st.error(f"Unexpected transcription data type: {type(transcribed_data)}")
                return None
        return None
    except Exception as e:
        st.error(f"Error fetching transcription: {str(e)}")
        return None

def main():
    st.title("🎵 K-Pop Video Clip Manager")
    
    # Initialize Supabase client
    supabase = init_supabase()
    
    # Add tabs for different functionalities
    tab1, tab2 = st.tabs(["Upload Clips", "Generate Video"])
    
    with tab1:
        # Fetch available songs
        songs = fetch_songs(supabase)
        song_options = {song['id']: song['title'] for song in songs}
        
        # Song selector at the top
        selected_song = st.selectbox(
            "Select Song",
            options=list(song_options.keys()),
            format_func=lambda x: song_options[x]
        )
        
        # Display transcription segments
        st.header("1. Transcription Segments")
        transcription_text = st.text_area(
            "Paste the transcription JSON data",
            height=200
        )
        
        if transcription_text:
            try:
                transcription_data = json.loads(transcription_text)
                
                # Display segments
                st.subheader("Available Segments")
                for i, segment in enumerate(transcription_data):
                    st.text(f"{i:03d}: {segment['start']:.2f}s - {segment['end']:.2f}s: {segment['text']}")
                
                # Clip upload section
                st.header("2. Upload Individual Clip")
                
                # Segment selector
                segment_index = st.number_input(
                    "Select segment number to upload clip for",
                    min_value=0,
                    max_value=len(transcription_data)-1,
                    value=0,
                    step=1
                )
                
                selected_segment = transcription_data[segment_index]
                st.info(f"Selected segment: {selected_segment['text']}")
                
                # File uploader for single clip
                clip_file = st.file_uploader("Upload 5-second clip for this segment", type=['mp4'])
                
                if clip_file:
                    # Create columns for layout
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.video(clip_file)
                    
                    with col2:
                        # Metadata form
                        st.subheader("Clip Metadata")
                        
                        scene_type = st.selectbox(
                            "Scene Type",
                            ["performance", "closeup", "group", "dance", "b-roll", "transition"]
                        )
                        
                        scene_tags = st.text_input(
                            "Scene Tags (comma separated)"
                        )
                        
                        manual_description = st.text_area(
                            "Manual Description"
                        )
                        
                        if st.button("Upload Clip"):
                            # Check and standardize resolution
                            clip_filename = f"clip_{segment_index:03d}.mp4"
                            os.makedirs("video_clips", exist_ok=True)
                            
                            # Process the uploaded clip
                            temp_path, original_resolution, was_resized = check_and_standardize_resolution(
                                clip_file, target_resolution=(960, 960)
                            )
                            
                            # Get file size after potential resize
                            file_size = get_file_size(temp_path)
                            
                            # Upload to nginx and get URLs
                            urls = upload_to_server(temp_path, clip_filename)
                            
                            if urls:
                                # Update Supabase with metadata
                                try:
                                    supabase.table('video_clips').insert({
                                        'filename': clip_filename,
                                        'filepath': urls['external_url'],  # Store external URL for public access
                                        'internal_url': urls['internal_url'],  # Store internal URL for container access
                                        'song_id': selected_song,
                                        'start_time': selected_segment['start'],
                                        'end_time': selected_segment['end'],
                                        'order_index': segment_index,
                                        'scene_type': scene_type,
                                        'scene_tags': scene_tags.split(','),
                                        'source_text': selected_segment['text'],
                                        'manual_description': manual_description,
                                        'filesize': file_size,
                                        'width': 960,  # Add resolution info
                                        'height': 960,  # Add resolution info
                                        'original_resolution': f"{original_resolution[0]}x{original_resolution[1]}"  # Store original resolution
                                    }).execute()
                                    
                                    if was_resized:
                                        st.success(f"Uploaded clip {segment_index} with metadata (resized from {original_resolution[0]}x{original_resolution[1]} to 960x960)")
                                    else:
                                        st.success(f"Uploaded clip {segment_index} with metadata")
                                    
                                    # Clean up temporary file
                                    os.remove(temp_path)
                                except Exception as e:
                                    st.error(f"Failed to save metadata: {str(e)}")
                
                # Display progress
                st.header("3. Upload Progress")
                try:
                    existing_clips = supabase.table('video_clips').select('order_index').eq('song_id', selected_song).execute()
                    uploaded_segments = [clip['order_index'] for clip in existing_clips.data]
                    
                    st.write("Uploaded segments:", sorted(uploaded_segments))
                    st.progress(len(uploaded_segments) / len(transcription_data))
                    st.write(f"Progress: {len(uploaded_segments)}/{len(transcription_data)} clips uploaded")
                    
                    # Show generate video button when all clips are uploaded
                    if len(uploaded_segments) == len(transcription_data):
                        if st.button("Generate Final Music Video"):
                            st.info("This feature will be implemented to stitch all clips together with the song.")
                            # TODO: Implement video stitching functionality
                
                except Exception as e:
                    st.error(f"Error checking progress: {str(e)}")
                
            except json.JSONDecodeError:
                st.error("Invalid JSON data. Please check the format.")
            except Exception as e:
                st.error(f"Error: {str(e)}")

    with tab2:
        st.header("Generate Music Video")
        
        st.write("Select a song to generate video for")
        selected_song = st.selectbox(
            "Select Song",
            options=list(song_options.keys()),
            format_func=lambda x: song_options[x],
            key="generate_video_song"
        )
        
        if st.button("Generate Video"):
            transcription_data = get_transcription(supabase, selected_song)
            
            if transcription_data:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(message):
                    # Update status message
                    status_text.text(message)
                    
                    # Try to extract progress from message if it contains segment info
                    try:
                        if "Processing segment" in message:
                            current, total = map(int, message.split()[2].split('/'))
                            progress = current / total
                            progress_bar.progress(progress)
                    except:
                        pass
                
                try:
                    output_path = generate_video(selected_song, transcription_data, progress_callback=update_progress)
                    if output_path:
                        st.success(f"Video generated successfully!")
                        st.video(output_path)
                    else:
                        st.error("Failed to generate video")
                except Exception as e:
                    st.error(f"Error during video generation: {str(e)}")
            else:
                st.error("No transcription data found for this song")

if __name__ == "__main__":
    main()
