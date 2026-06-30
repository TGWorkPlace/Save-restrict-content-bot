# cantarella / Modified by You
# Don't Remove Credit
# Telegram Channel @cantarellabots
#
# Generic helper utilities used by start.py.
# NOTE: Bad-words removal, custom thumbnail, prefix/suffix, metadata and
# sleep settings are now fully DB-backed (per user) instead of hard-coded
# constants. These functions are now pure helpers that accept their
# configuration as parameters - the caller (start.py) is responsible for
# fetching the relevant values from the database before calling them.

import os
import re
import random
import subprocess
import asyncio
import aiohttp


def clean_filename(filename: str, words_to_remove=None) -> str:
    """Remove unwanted words from filename.

    `words_to_remove` should be a list of words/strings fetched from the
    database for the current user (see db.get_delete_words). If omitted or
    empty, no words are stripped - only whitespace is normalized.
    """
    if not filename:
        return filename

    words_to_remove = words_to_remove or []

    name_parts = filename.rsplit('.', 1)
    name = name_parts[0]
    ext = name_parts[1] if len(name_parts) > 1 else ""

    for word in words_to_remove:
        if not word:
            continue
        name = re.sub(re.escape(word), '', name, flags=re.IGNORECASE)

    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'[_\-\s]+', ' ', name).strip()

    return f"{name}.{ext}" if ext else name


def apply_prefix_suffix(filename: str, prefix: str = None, suffix: str = None) -> str:
    """Apply prefix and suffix to filename.

    `prefix`/`suffix` should be fetched per-user from the database
    (see db.get_prefix / db.get_suffix).
    """
    if not filename:
        return filename

    name_parts = filename.rsplit('.', 1)
    if len(name_parts) == 2:
        name, ext = name_parts
    else:
        name = filename
        ext = ""

    if prefix:
        name = f"{prefix}.{name}"

    if suffix:
        name = f"{name}.{suffix}"

    if ext:
        return f"{name}.{ext}"
    return name


async def smart_sleep(sleep_values=None):
    """Intelligent sleep with randomization between batch downloads.

    Picks a random value from the user's custom sleep list (fetched from
    the database by the caller), adds +/-20% jitter for natural behaviour.
    """
    base_sleep = sleep_values or [3, 5, 7, 10]
    sleep_time = random.choice(base_sleep)
    jitter = random.uniform(-0.2, 0.2) * sleep_time
    final_sleep = sleep_time + jitter
    await asyncio.sleep(final_sleep)


async def download_thumbnail(url):
    """Download a thumbnail from a direct URL (still useful as a generic
    utility, e.g. if an admin wants to set a per-user thumbnail by URL)."""
    if not url:
        return None

    try:
        os.makedirs("temp_thumbs", exist_ok=True)
        thumb_path = f"temp_thumbs/thumb_{random.randint(1000, 9999)}.jpg"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    with open(thumb_path, 'wb') as f:
                        f.write(await response.read())
                    return thumb_path
    except Exception as e:
        print(f"Error downloading thumbnail: {e}")

    return None


# Fields supported in the per-user metadata dict (also used by settings.py
# to build the /metadata inline panel).
METADATA_FIELDS = [
    "METADATA_TITLE",
    "METADATA_AUTHOR",
    "METADATA_ARTIST",
    "METADATA_DESCRIPTION",
    "METADATA_COMMENT",
    "METADATA_VIDEO_TITLE",
    "METADATA_AUDIO_TITLE",
    "METADATA_SUBTITLE_TITLE",
]


async def add_metadata_with_ffmpeg(input_file, final_filename, metadata: dict = None):
    """Add metadata to video/audio files using ffmpeg while preserving all
    streams and adding stream titles.

    `metadata` is a per-user dict fetched from the database
    (see db.get_metadata) with keys matching METADATA_FIELDS. Any value can
    contain the literal token "{file_name}" which will be replaced with the
    final cleaned filename - this preserves the old "use filename as title"
    behaviour, just driven by the DB instead of a hard-coded env var.

    If a field is blank/missing, original metadata for that field is
    preserved (untouched).
    """
    metadata = metadata or {}

    meta_title       = metadata.get("METADATA_TITLE")
    meta_author      = metadata.get("METADATA_AUTHOR")
    meta_artist      = metadata.get("METADATA_ARTIST")
    meta_description = metadata.get("METADATA_DESCRIPTION")
    meta_comment     = metadata.get("METADATA_COMMENT")
    meta_video_title    = metadata.get("METADATA_VIDEO_TITLE")
    meta_audio_title    = metadata.get("METADATA_AUDIO_TITLE")
    meta_subtitle_title = metadata.get("METADATA_SUBTITLE_TITLE")

    if not any([meta_title, meta_author, meta_artist, meta_description,
                meta_comment, meta_video_title, meta_audio_title, meta_subtitle_title]):
        return input_file, False

    ext = input_file.rsplit('.', 1)[-1].lower()
    if ext not in ['mp4', 'mkv', 'avi', 'mov', 'flv', 'wmv', 'webm', 'mp3', 'flac', 'wav', 'm4a', 'aac', 'ogg']:
        return input_file, False

    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("FFmpeg/FFprobe not found. Skipping metadata addition.")
        return input_file, False

    try:
        dir_name = os.path.dirname(input_file)
        output_file = os.path.join(dir_name, f"temp_meta_{random.randint(1000, 9999)}.{ext}")

        # First, probe the file to get stream information
        probe_cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_streams', input_file
        ]

        try:
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            import json
            probe_data = json.loads(probe_result.stdout)
            streams = probe_data.get('streams', [])
        except Exception:
            streams = []

        cmd = [
            'ffmpeg', '-i', input_file,
            '-map', '0',
            '-c', 'copy',
            '-map_metadata', '0'  # Preserve all original metadata by default
        ]

        def fmt(value):
            return value.format(file_name=final_filename)

        # Add/override global metadata only if set
        if meta_title:
            cmd.extend(['-metadata', f'title={fmt(meta_title)}'])
        if meta_author:
            cmd.extend(['-metadata', f'author={fmt(meta_author)}'])
        if meta_artist:
            cmd.extend(['-metadata', f'artist={fmt(meta_artist)}'])
        if meta_description:
            cmd.extend(['-metadata', f'description={fmt(meta_description)}'])
        if meta_comment:
            cmd.extend(['-metadata', f'comment={fmt(meta_comment)}'])

        # Add stream-specific metadata only if set (preserves original if not set)
        for idx, stream in enumerate(streams):
            codec_type = stream.get('codec_type', '').lower()

            if codec_type == 'video' and meta_video_title:
                video_idx = sum(1 for s in streams[:idx] if s.get('codec_type') == 'video')
                cmd.extend([f'-metadata:s:v:{video_idx}', f'title={fmt(meta_video_title)}'])

            elif codec_type == 'audio' and meta_audio_title:
                audio_idx = sum(1 for s in streams[:idx] if s.get('codec_type') == 'audio')
                cmd.extend([f'-metadata:s:a:{audio_idx}', f'title={fmt(meta_audio_title)}'])

            elif codec_type == 'subtitle' and meta_subtitle_title:
                subtitle_idx = sum(1 for s in streams[:idx] if s.get('codec_type') == 'subtitle')
                cmd.extend([f'-metadata:s:s:{subtitle_idx}', f'title={fmt(meta_subtitle_title)}'])

        cmd.extend(['-y', output_file])

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        process.wait()

        if process.returncode == 0 and os.path.exists(output_file):
            os.remove(input_file)
            os.rename(output_file, input_file)
            return input_file, True
        else:
            if os.path.exists(output_file):
                os.remove(output_file)
            raise Exception("FFmpeg failed")

    except Exception as e:
        print(f"Metadata error: {e}")
        if 'output_file' in locals() and os.path.exists(output_file):
            try:
                os.remove(output_file)
            except Exception:
                pass
        return input_file, False
