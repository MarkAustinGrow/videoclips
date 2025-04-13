import os
import ffmpeg
import json
from typing import Dict, List

class VideoProcessor:
    def __init__(self):
        """Initialize VideoProcessor with default settings."""
        self.clips_dir = "video_clips"
        self._ensure_clips_directory()
    
    def _ensure_clips_directory(self):
        """Ensure the video clips directory exists."""
        os.makedirs(self.clips_dir, exist_ok=True)
    
    def split_video(self, input_path: str, segment_duration: int = 5):
        """Split a video into segments of specified duration."""
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input video not found: {input_path}")
        
        output_pattern = os.path.join(self.clips_dir, "clip_%03d.mp4")
        
        try:
            stream = ffmpeg.input(input_path)
            stream = ffmpeg.output(
                stream,
                output_pattern,
                c="copy",
                map=0,
                f="segment",
                segment_time=segment_duration
            )
            ffmpeg.run(stream, overwrite_output=True)
        except ffmpeg.Error as e:
            print(f"Error splitting video: {str(e)}")
            raise

    def process_clips_with_timestamps(self, song_id: str, transcription_data: List[Dict]):
        """Process clips with their corresponding transcription timestamps."""
        clips_metadata = []
        
        for i, segment in enumerate(transcription_data):
            start_time = segment['start']
            end_time = segment['end']
            
            clip_metadata = {
                'song_id': song_id,
                'filename': f'clip_{i:03d}.mp4',
                'start_time': start_time,
                'end_time': end_time,
                'duration': end_time - start_time,
                'order_index': i
            }
            
            clips_metadata.append(clip_metadata)
        
        return clips_metadata

    def validate_clip(self, clip_path: str) -> bool:
        """Validate if a clip exists and is a valid video file."""
        if not os.path.exists(clip_path):
            return False
            
        try:
            probe = ffmpeg.probe(clip_path)
            return 'streams' in probe and len(probe['streams']) > 0
        except ffmpeg.Error:
            return False 