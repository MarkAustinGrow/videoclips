# K-Pop Video Clip Manager Documentation

## Overview
The K-Pop Video Clip Manager is a web application that allows users to:
1. Upload and manage 5-second video clips with associated metadata
2. Generate music videos by intelligently combining clips based on lyrics
3. Track clip usage and maintain a library of reusable video segments

## System Architecture

### Components
1. **Frontend**: Streamlit web interface
2. **Backend**: Python application with video processing capabilities
3. **Database**: Supabase for storing metadata and clip information
4. **Storage**: Nginx server for serving video files
5. **Container**: Docker for deployment and isolation

### Tech Stack
- Python 3.11
- Streamlit
- MoviePy
- Supabase
- Docker & Docker Compose
- Nginx
- FFmpeg

## Directory Structure
```
video_clips/
├── src/
│   ├── database/
│   │   └── supabase_client.py    # Supabase connection handling
│   ├── video/
│   │   └── processor.py          # Video processing utilities
│   └── ai/
│       └── openai_client.py      # OpenAI integration (optional)
├── clip_manager.py               # Main Streamlit application
├── generate_video.py             # Video generation logic
├── process_song.py              # Song processing utilities
├── docker-compose.yml           # Development configuration
├── docker-compose.prod.yml      # Production configuration
├── Dockerfile                   # Container definition
├── nginx.conf                   # Nginx configuration
├── requirements.txt             # Python dependencies
└── .env                        # Environment variables
```

## Database Schema

### video_clips Table
```sql
CREATE TABLE video_clips (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    song_id uuid REFERENCES songs(id),
    start_time FLOAT,
    end_time FLOAT,
    order_index INTEGER,
    scene_type TEXT,
    scene_tags TEXT[],
    source_text TEXT,
    manual_description TEXT,
    filesize INTEGER,
    times_used INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now()
);
```

### songs Table
```sql
CREATE TABLE songs (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    transcribed JSONB,
    created_at TIMESTAMP DEFAULT now()
);
```

### clip_usages Table
```sql
CREATE TABLE clip_usages (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    clip_id uuid REFERENCES video_clips(id),
    song_id uuid REFERENCES songs(id),
    order_index INTEGER,
    used_at TIMESTAMP DEFAULT now()
);
```

## Core Functions

### Clip Management
- `upload_to_server(local_path, remote_filename)`: Uploads clips to Nginx server
- `find_matching_clip(supabase, text, song_id)`: Finds clips matching lyric text
- `track_clip_usage(supabase, clip_id, song_id, segment_index)`: Tracks clip usage

### Video Generation
- `generate_video(song_id, transcription_data, progress_callback)`: Main video generation
- `download_clip(url, local_path)`: Downloads clips for processing
- `VideoProcessor.split_video(input_path, segment_duration)`: Splits videos into clips

## Setup Instructions

1. **Environment Setup**
```bash
# Clone repository
git clone <repository-url>
cd video_clips

# Create environment file
cp .env.example .env
# Edit .env with your credentials:
# - SUPABASE_URL
# - SUPABASE_KEY
# - LINODE_SERVER_PASSWORD (if using remote storage)
```

2. **Database Setup**
- Create a Supabase project
- Execute the table creation SQL statements
- Set up storage bucket for clips (optional)

3. **Development Environment**
```bash
# Build and run with Docker
docker-compose up --build
```

4. **Production Deployment**
```bash
# On your server
git clone <repository-url>
cd video_clips

# Configure environment
cp .env.example .env
nano .env  # Add your credentials

# Start services
docker-compose -f docker-compose.prod.yml up -d
```

## Video Generation Process

1. **Clip Preparation**
- Upload 5-second video clips
- Add metadata (scene type, tags, description)
- Associate with song and lyrics

2. **Generation Process**
- Load song transcription data
- For each segment:
  1. Find matching clips
  2. Download and verify clips
  3. Add to video sequence
- Concatenate clips
- Write final video

## Best Practices

1. **Clip Management**
- Use consistent 5-second clip lengths
- Provide detailed scene descriptions
- Tag clips appropriately for better matching

2. **Error Handling**
- Validate clip properties before processing
- Handle missing clips gracefully
- Clean up temporary files

3. **Performance**
- Use Docker volumes for clip storage
- Implement caching where appropriate
- Monitor resource usage

## Troubleshooting

Common issues and solutions:

1. **Missing Clips**
- Check clip filepath in database
- Verify Nginx serving configuration
- Ensure proper file permissions

2. **Video Generation Failures**
- Check clip download success
- Verify clip duration and format
- Monitor memory usage during concatenation

3. **Database Issues**
- Verify Supabase connection
- Check table schema matches
- Monitor query performance

## Future Improvements

1. **Features**
- Audio track synchronization
- Advanced clip matching algorithms
- Batch clip processing

2. **Performance**
- Clip caching system
- Parallel processing
- Stream processing for large videos

3. **UI/UX**
- Progress visualization
- Clip preview interface
- Batch upload capabilities 