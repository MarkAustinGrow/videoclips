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
        
        # Song selection for video generation
        songs = fetch_songs(supabase)
        song_options = {song['id']: song['title'] for song in songs}
        
        target_song = st.selectbox(
            "Select Song to Generate Video For",
            options=list(song_options.keys()),
            format_func=lambda x: song_options[x],
            key="generate_song"
        )
        
        # Transcription input
        transcription_text = st.text_area(
            "Paste the transcription JSON data for the target song",
            height=200,
            key="generate_transcription"
        )
        
        if transcription_text:
            try:
                transcription_data = json.loads(transcription_text)
                
                # Display clip reuse options
                st.subheader("Clip Reuse Settings")
                
                allow_other_songs = st.checkbox(
                    "Allow using clips from other songs",
                    value=True,
                    help="If checked, the system will look for matching clips from other songs when needed"
                )
                
                use_fuzzy_matching = st.checkbox(
                    "Use fuzzy text matching",
                    value=True,
                    help="If checked, the system will try to find clips with similar text when exact matches aren't found"
                )
                
                if st.button("Generate Video"):
                    with st.spinner("Generating video..."):
                        # Call generate_video function
                        output_path = generate_video(
                            song_id=target_song,
                            transcription_data=transcription_data
                        )
                        
                        if output_path and os.path.exists(output_path):
                            # Upload to server
                            video_filename = f"generated_{target_song}.mp4"
                            video_url = upload_to_server(output_path, video_filename)
                            
                            if video_url:
                                st.success("Video generated successfully!")
                                st.video(video_url)
                                
                                # Display clip usage statistics
                                st.subheader("Clip Usage Statistics")
                                try:
                                    stats = supabase.table('clip_usages')\
                                        .select('clip_id, video_clips(source_text)')\
                                        .eq('song_id', target_song)\
                                        .execute()
                                    
                                    if stats.data:
                                        st.write("Clips used in this video:")
                                        for usage in stats.data:
                                            st.write(f"- {usage['video_clips']['source_text']}")
                                except Exception as e:
                                    st.error(f"Error fetching usage statistics: {str(e)}")
                            else:
                                st.error("Failed to upload generated video")
                        else:
                            st.error("Failed to generate video")
                            
            except json.JSONDecodeError:
                st.error("Invalid JSON data. Please check the format.")
            except Exception as e:
                st.error(f"Error: {str(e)}")

if __name__ == "__main__":
    main() 