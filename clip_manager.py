import os
import json
import streamlit as st
import paramiko
from dotenv import load_dotenv
from src.database.supabase_client import init_supabase

# Load environment variables
load_dotenv()

def upload_to_server(local_path: str, remote_filename: str):
    """Upload a file to the video server via SFTP."""
    try:
        transport = paramiko.Transport((
            os.getenv('VIDEO_SERVER'),
            22
        ))
        transport.connect(
            username=os.getenv('VIDEO_SERVER_USER'),
            password=os.getenv('VIDEO_SERVER_PASSWORD')
        )
        
        sftp = paramiko.SFTPClient.from_transport(transport)
        
        # Upload to videos directory
        remote_path = f'/var/www/html/videos/{remote_filename}'
        sftp.put(local_path, remote_path)
        
        sftp.close()
        transport.close()
        return True
    except Exception as e:
        st.error(f"Upload failed: {str(e)}")
        return False

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
                        # Save clip file
                        clip_filename = f"clip_{segment_index:03d}.mp4"
                        with open(f"video_clips/{clip_filename}", "wb") as f:
                            f.write(clip_file.getvalue())
                        
                        # Upload to server and Supabase
                        if upload_to_server(f"video_clips/{clip_filename}", clip_filename):
                            # Update Supabase with metadata
                            supabase.table('video_clips').insert({
                                'filename': clip_filename,
                                'filepath': f"/videos/{clip_filename}",
                                'song_id': selected_song,
                                'start_time': selected_segment['start'],
                                'end_time': selected_segment['end'],
                                'order_index': segment_index,
                                'scene_type': scene_type,
                                'scene_tags': scene_tags.split(','),
                                'source_text': selected_segment['text'],
                                'manual_description': manual_description
                            }).execute()
                            st.success(f"Uploaded clip {segment_index} with metadata")
            
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

if __name__ == "__main__":
    # Create necessary directories
    os.makedirs("video_clips", exist_ok=True)
    
    main() 