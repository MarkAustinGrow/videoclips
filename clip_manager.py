import os
import json
import streamlit as st
import paramiko
from dotenv import load_dotenv
from src.database.supabase_client import init_supabase
from generate_video import generate_video

# Load environment variables
load_dotenv()

def upload_to_server(local_path: str, remote_filename: str):
    """Upload a file to the Linode server via SFTP."""
    try:
        transport = paramiko.Transport(('172.236.1.244', 22))
        transport.connect(
            username='root',
            password=os.getenv('LINODE_SERVER_PASSWORD')
        )
        
        sftp = paramiko.SFTPClient.from_transport(transport)
        
        # Upload to videos directory on Linode
        remote_path = f'/var/www/html/videos/{remote_filename}'
        sftp.put(local_path, remote_path)
        
        sftp.close()
        transport.close()
        
        # Return both internal and external URLs
        return {
            'internal_url': f'http://nginx/videos/{remote_filename}',  # For Docker network
            'external_url': f'http://172.236.1.244/videos/{remote_filename}'  # For public access
        }
    except Exception as e:
        st.error(f"Upload failed: {str(e)}")
        return None

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
                            # Save clip file temporarily
                            clip_filename = f"clip_{segment_index:03d}.mp4"
                            temp_path = f"video_clips/{clip_filename}"
                            os.makedirs("video_clips", exist_ok=True)
                            
                            with open(temp_path, "wb") as f:
                                f.write(clip_file.getvalue())
                            
                            # Get file size
                            file_size = get_file_size(temp_path)
                            
                            # Upload to Linode and get URLs
                            urls = upload_to_server(temp_path, clip_filename)
                            
                            if urls:
                                # Update Supabase with metadata
                                try:
                                    supabase.table('video_clips').insert({
                                        'filename': clip_filename,
                                        'filepath': urls['internal_url'],  # Store internal URL for Docker network
                                        'public_url': urls['external_url'],  # Store external URL for public access
                                        'song_id': selected_song,
                                        'start_time': selected_segment['start'],
                                        'end_time': selected_segment['end'],
                                        'order_index': segment_index,
                                        'scene_type': scene_type,
                                        'scene_tags': scene_tags.split(','),
                                        'source_text': selected_segment['text'],
                                        'manual_description': manual_description,
                                        'filesize': file_size
                                    }).execute()
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
        
        # Get available songs
        songs = fetch_songs(supabase)
        if not songs:
            st.warning("No songs found in database. Please upload some clips first.")
            return
            
        # Song selection
        selected_song = st.selectbox(
            "Select a song to generate video for",
            options=songs,
            format_func=lambda x: x['title']
        )
        
        if st.button("Generate Video"):
            if not selected_song:
                st.error("Please select a song first")
                return
                
            with st.spinner("Preparing to generate video..."):
                # Get transcription data
                transcription = get_transcription(supabase, selected_song['id'])
                if not transcription:
                    st.error("No transcription data found for this song")
                    return
                    
                # Progress tracking
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(current_segment, message):
                    # Update progress bar (0-100%)
                    progress = (current_segment + 1) / len(transcription) * 100
                    progress_bar.progress(int(progress))
                    status_text.text(message)
                
                try:
                    # Generate video with progress tracking
                    output_path = generate_video(
                        selected_song['id'],
                        transcription,
                        progress_callback=update_progress
                    )
                    
                    if output_path and os.path.exists(output_path):
                        # Show success and video player
                        st.success("Video generated successfully!")
                        st.video(output_path)
                        
                        # Download button
                        with open(output_path, 'rb') as f:
                            st.download_button(
                                "Download Video",
                                f,
                                file_name=f"generated_{selected_song['title']}.mp4",
                                mime="video/mp4"
                            )
                    else:
                        st.error("Failed to generate video. Check logs for details.")
                except Exception as e:
                    st.error(f"Error during video generation: {str(e)}")
                finally:
                    # Clear progress indicators
                    progress_bar.empty()
                    status_text.empty()

if __name__ == "__main__":
    main() 