# AI K-Pop Music Video Generator

An AI-powered system for generating K-pop music videos by intelligently combining video clips based on lyrics and music.

## Setup

1. Clone the repository:
```bash
git clone <your-repo-url>
cd video_clips
```

2. Create and configure your .env file:
```bash
cp .env.example .env
# Edit .env with your API keys and credentials
```

3. Build and run with Docker:
```bash
docker-compose up --build
```

## Project Structure

- `video_clips/` - Directory for storing 5-second video clips
- `main.py` - Main application entry point
- `src/` - Source code directory
  - `database/` - Database models and operations
  - `video/` - Video processing utilities
  - `ai/` - AI and OpenAI integration

## Manual Video Creation Process

1. Create initial music videos using your preferred video editor
2. Use ffmpeg to split videos into 5-second clips:
```bash
ffmpeg -i video.mp4 -c copy -map 0 -segment_time 5 -f segment video_clips/clip_%03d.mp4
```

3. Upload clips to the video server:
```bash
# Upload script will be provided in future updates
```

## Development

- Run tests: `docker-compose run app python -m pytest`
- Format code: `docker-compose run app black .`
- Lint code: `docker-compose run app flake8`

## Deployment

1. Push changes to GitHub
2. Pull on Linode server
3. Build and run Docker container:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

## License

MIT 