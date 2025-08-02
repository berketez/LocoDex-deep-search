import base64
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import List, Literal

from pydantic import BaseModel, ValidationError

from libs.utils.llms import single_shot_llm_call


@dataclass(frozen=True, kw_only=True)
class PodcastDialogue:
    speaker: str
    text: str


@dataclass(frozen=True, kw_only=True)
class PodcastScript:
    title: str
    host_voice: str
    guest_voice: str
    dialogue: List[PodcastDialogue]


class LineItem(BaseModel):
    speaker: Literal["Host", "Guest"]
    text: str


class Script(BaseModel):
    script_data: List[LineItem]


def _generate_audio_segment(text: str, voice: str) -> bytes:
    """Generate a single audio segment using Together AI API."""
    import requests
    
    url = "https://api.together.ai/v1/audio/generations"

    headers = {"Authorization": f"Bearer {os.getenv('TOGETHER_API_KEY')}"}

    data = {
        "input": "-" + text,  # Add hyphen for slight pause
        "voice": voice,
        "response_format": "mp3",  # Get MP3 directly instead of raw PCM
        "sample_rate": 44100,
        "stream": False,
        "model": "cartesia/sonic",
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.content


def generate_podcast_audio(script: PodcastScript) -> bytes:
    """
    Generate podcast audio from a script using the Together AI API.
    
    Parameters:
        script (PodcastScript): The podcast script to generate
        api_key (str): Together AI API key
        
    Returns:
        bytes: Raw audio data from the API
    
    Raises:
        ValueError: If API key is missing or voices are invalid
    """
 
    available_voices = ["laidback woman", "customer support man"]
    
    if script.host_voice not in available_voices or script.guest_voice not in available_voices:
        raise ValueError(f"Invalid voice selected. Available voices: {', '.join(available_voices)}")
    
    # Combine all audio segments into one response
    audio_data = bytearray()
    for line in script.dialogue:
        voice = script.host_voice if line.speaker == "Host" else script.guest_voice
        segment_audio = _generate_audio_segment(line.text, voice)
        audio_data.extend(segment_audio)
    
    return bytes(audio_data)


def generate_podcast_script(
    *,
    system_prompt: str, 
    input_text: str, 
    podcast_name: str = "My Podcast",
    host_voice: str = "laidback woman", 
    guest_voice: str = "customer support man"
) -> PodcastScript:
    """
    Generate a podcast script using an LLM.
    
    Args:
        system_prompt: The prompt to guide the LLM
        input_text: The content to base the podcast on
        podcast_name: Title of the podcast
        host_voice: Voice style for the host
        guest_voice: Voice style for the guest
        
    Returns:
        A PodcastScript object with the generated dialogue
    """
    try:
        response = single_shot_llm_call(
            model="together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            system_prompt=system_prompt,
            message=input_text,
            response_format={
                "type": "json_object",
                "schema": Script.model_json_schema(),
            },
        )
        llm_script = Script.model_validate_json(response)
    except ValidationError as e:
        raise ValueError(f"Invalid script format: {e}")
    
    
    dialogue = [
        PodcastDialogue(
            speaker="Host" if item.speaker == "Host" else "Guest",
            text=item.text
        ) for item in llm_script.script_data
    ]
    
    return PodcastScript(
        title=podcast_name,
        host_voice=host_voice,
        guest_voice=guest_voice,
        dialogue=dialogue
    )


# Available voices in the cartesia/sonic model
AVAILABLE_VOICES = [
    "laidback woman",  # Good for hosts
    "customer support man",  # Good for guests
]


def full_podcast_generation(*, system_prompt: str, text: str, podcast_name: str = "My Podcast", host_voice: str = "laidback woman", guest_voice: str = "customer support man") -> str:
    script = generate_podcast_script(system_prompt=system_prompt, input_text=text, podcast_name=podcast_name, host_voice=host_voice, guest_voice=guest_voice)
    audio = generate_podcast_audio(script)
    base64_audio = get_base64_audio(audio)
    return base64_audio


def pcm_to_wav_bytes(pcm_data, sample_rate=44100):
    """
    Convert raw PCM float32le data to WAV format using ffmpeg.
    This creates temporary files but doesn't save the audio permanently.
    """
    with tempfile.NamedTemporaryFile(suffix='.pcm', delete=True) as pcm_file:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as wav_file:
            # Write PCM data to temp file
            pcm_file.write(pcm_data)
            pcm_file.flush()
            
            # Use ffmpeg to convert (same as the working implementation)
            cmd = [
                "ffmpeg", 
                "-y",                  # Overwrite output files
                "-f", "f32le",         # Input format is 32-bit float PCM
                "-ar", str(sample_rate), # Sample rate
                "-ac", "1",            # Mono audio
                "-i", pcm_file.name,   # Input file
                wav_file.name          # Output file
            ]
            
            # Run ffmpeg
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Error converting audio format: {result.stderr}")
            
            # Read the WAV data
            wav_file.seek(0)
            return wav_file.read()


def get_base64_audio(audio_bytes: bytes) -> str:
    """
    Convert audio bytes to a base64-encoded data URL for HTML embedding.
    
    Args:
        audio_bytes: Raw audio data bytes
        
    Returns:
        String containing a data URL with base64-encoded audio
    """
    encoded = base64.b64encode(audio_bytes).decode('utf-8')
    return f"data:audio/mp3;base64,{encoded}"


def save_podcast_html(script: PodcastScript, audio_bytes: bytes, output_path: str = "podcast_test.html"):
    """
    Save a podcast as an HTML file with embedded audio player.
    
    Args:
        script: The podcast script
        audio_bytes: Raw audio data bytes
        output_path: Where to save the HTML file
        
    Returns:
        Path to the HTML file
    """
    # Convert audio to base64
    base64_audio = get_base64_audio(audio_bytes)
    
    # Create HTML content
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{script.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        h1 {{ color: #333; }}
        .player-container {{ margin: 30px 0; }}
        .transcript {{ margin-top: 40px; }}
        .line {{ margin-bottom: 15px; }}
        .speaker {{ font-weight: bold; }}
    </style>
</head>
<body>
    <h1>{script.title}</h1>
    
    <div class="player-container">
        <h2>Listen to the Podcast</h2>
        <audio controls>
            <source src="{base64_audio}" type="audio/wav">
            Your browser does not support the audio element.
        </audio>
    </div>
    
    <div class="transcript">
        <h2>Transcript</h2>
        {''.join(f'<div class="line"><span class="speaker">{line.speaker}:</span> {line.text}</div>' for line in script.dialogue)}
    </div>
</body>
</html>
"""
    
    # Save to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return output_path


def save_podcast_to_disk(audio_bytes: bytes, output_path: str) -> str:
    """
    Save podcast audio bytes to disk in MP3 format.
    
    Args:
        audio_bytes: Raw MP3 audio data bytes
        output_path: Path to save the audio file
        
    Returns:
        Path to the saved audio file
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    
    return output_path


if __name__ == "__main__":
    text = "today we are talking about the latest trends in AI and the future of the industry"
    
    # Generate podcast script and audio
    system_prompt = "Generate a podcast script from the following text"
    script = generate_podcast_script(
        system_prompt=system_prompt,
        input_text=text,
        podcast_name="AI Trends Podcast",
        host_voice="laidback woman",
        guest_voice="customer support man"
    )
    print(script)
    audio = generate_podcast_audio(script)
    
    # Save as HTML with embedded audio
    html_path = save_podcast_html(script, audio)
    print(f"HTML file with embedded audio generated at: {html_path}")