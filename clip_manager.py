import os
import json
import streamlit as st
import paramiko
from dotenv import load_dotenv
from src.database.supabase_client import init_supabase
from src.video.processor import VideoProcessor

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

def main():
    st.title("🎵 K-Pop Video Clip Manager")
    
    # Initialize clients
    supabase = init_supabase()
    processor = VideoProcessor()
    
    # File uploader for the main video
    st.header("1. Upload Original Video")
    video_file = st.file_uploader("Choose a video file", type=['mp4'])
    
    if video_file:
        # Save uploaded file
        with open("input/temp_video.mp4", "wb") as f:
            f.write(video_file.getvalue())
        st.success("Video uploaded successfully!")
        
        # Input for transcription data
        st.header("2. Transcription Data")
        transcription_text = st.text_area(
            "Paste the transcription JSON data",
            height=200
        )
        
        if transcription_text:
            try:
                transcription_data = json.loads(transcription_text)
                st.success("Transcription data loaded successfully!")
                
                # Display transcription segments
                st.header("3. Transcription Segments")
                for i, segment in enumerate(transcription_data):
                    st.text(f"{i:03d}: {segment['start']:.2f}s - {segment['end']:.2f}s: {segment['text']}")
                
                # Process video button
                if st.button("Process Video into Clips"):
                    with st.spinner("Processing video..."):
                        processor.split_video("input/temp_video.mp4")
                        clips_metadata = processor.process_clips_with_timestamps(
                            "c492d4c1-bba8-40eb-934a-3240e1624be6",  # Summer Electric ID
                            transcription_data
                        )
                        st.success("Video processed into clips!")
                        
                        # Display clips
                        st.header("4. Generated Clips")
                        for clip in clips_metadata:
                            clip_path = os.path.join(processor.clips_dir, clip['filename'])
                            col1, col2 = st.columns([3, 1])
                            
                            with col1:
                                st.text(f"Clip: {clip['filename']}")
                                if os.path.exists(clip_path):
                                    st.video(clip_path)
                            
                            with col2:
                                if st.button(f"Upload {clip['filename']}", key=clip['filename']):
                                    with st.spinner(f"Uploading {clip['filename']}..."):
                                        if upload_to_server(clip_path, clip['filename']):
                                            # Update Supabase
                                            supabase.table('video_clips').insert({
                                                'filename': clip['filename'],
                                                'filepath': f"/videos/{clip['filename']}",
                                                'song_id': clip['song_id'],
                                                'start_time': clip['start_time'],
                                                'end_time': clip['end_time'],
                                                'order_index': clip['order_index']
                                            }).execute()
                                            st.success(f"Uploaded {clip['filename']}")
                
            except json.JSONDecodeError:
                st.error("Invalid JSON data. Please check the format.")
            except Exception as e:
                st.error(f"Error: {str(e)}")

if __name__ == "__main__":
    # Create necessary directories
    os.makedirs("input", exist_ok=True)
    os.makedirs("video_clips", exist_ok=True)
    
    main() 