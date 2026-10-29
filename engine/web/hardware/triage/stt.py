from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .abstain import triage_with_abstention
except ImportError:
    from abstain import triage_with_abstention


# -------------------------
# Backend detection
# -------------------------

STT_BACKEND = "mock"

try:
    import whisper
    STT_BACKEND = "whisper"
except ImportError:
    pass

try:
    import vosk
    STT_BACKEND = "vosk"
except ImportError:
    pass


# -------------------------
# Transcription functions
# -------------------------


def _transcribe_mock(audio_path: str) -> dict[str, Any]:
    """
    Mock transcription for testing the pipeline without heavy AI models.
    
    It guesses the text based on the filename to let you test different routes.
    """
    filename = Path(audio_path).stem.lower()
    
    if "crop" in filename or "khet" in filename:
        text = "My wheat crop was destroyed by heavy rain. About 40 percent loss."
        conf = 0.85
    elif "wage" in filename or "kaam" in filename or "nrega" in filename:
        text = "I have a job card but no work was given for 15 days."
        conf = 0.75
    elif "pension" in filename or "shikayat" in filename:
        text = "My old age pension is delayed for 2 months."
        conf = 0.80
    elif "noise" in filename or "bad" in filename:
        text = "uh... um... background noise..."
        conf = 0.15
    else:
        text = "I need help with my scheme."
        conf = 0.40

    return {
        "text": text,
        "confidence": conf,
        "backend": "mock",
        "note": "No real speech model installed. Using filename-based mock for testing."
    }


def _transcribe_whisper(audio_path: str) -> dict[str, Any]:
    """
    Use OpenAI Whisper (or Indic-Whisper) for transcription.
    """
    model = whisper.load_model("base")  # Use "small" or "medium" for better Hindi/Indic support
    result = model.transcribe(audio_path, language="hi") # Or "en", or let it auto-detect
    
    text = result.get("text", "").strip()
    
    # Whisper doesn't give a direct 0-1 confidence easily, so we use a heuristic
    # based on no_speech_prob and average logprob.
    segments = result.get("segments", [])
    if segments:
        avg_logprob = sum(s.get("avg_logprob", -1.0) for s in segments) / len(segments)
        # avg_logprob is usually negative. Closer to 0 is better.
        conf = max(0.0, min(1.0, 1.0 + avg_logprob)) 
    else:
        conf = 0.0
        
    return {
        "text": text,
        "confidence": round(conf, 3),
        "backend": "whisper"
    }


def _transcribe_vosk(audio_path: str) -> dict[str, Any]:
    """
    Use Vosk for offline, lightweight speech recognition.
    Requires downloading a Vosk model folder.
    """
    import wave
    import json as json_lib
    
    # Assume model is in a folder named 'vosk-model'
    model_path = Path(__file__).parent / "vosk-model"
    if not model_path.exists():
        raise FileNotFoundError(f"Vosk model not found at {model_path}")
        
    model = vosk.Model(str(model_path))
    
    with wave.open(audio_path, "rb") as wf:
        rec = vosk.KaldiRecognizer(model, wf.getframerate())
        audio_data = wf.readframes(wf.getnframes())
        rec.AcceptWaveform(audio_data)
        result = json_lib.loads(rec.FinalResult())
        
    text = result.get("text", "").strip()
    conf = result.get("conf", 0.0)
    
    return {
        "text": text,
        "confidence": round(float(conf), 3),
        "backend": "vosk"
    }


def transcribe_audio(audio_path: str) -> dict[str, Any]:
    """
    Main transcription dispatcher.
    """
    if STT_BACKEND == "whisper":
        return _transcribe_whisper(audio_path)
    elif STT_BACKEND == "vosk":
        return _transcribe_vosk(audio_path)
    else:
        return _transcribe_mock(audio_path)


# -------------------------
# Full Audio Pipeline
# -------------------------


def pipeline_from_audio(
    audio_path: str, 
    speech_confidence_threshold: float = 0.50
) -> dict[str, Any]:
    """
    1. Transcribe audio.
    2. If speech confidence is too low, ABSTAIN immediately.
    3. Otherwise, pass text to the intent/slots/abstain pipeline.
    """
    audio_path_str = str(audio_path)
    
    try:
        speech_result = transcribe_audio(audio_path_str)
    except Exception as exc:
        return {
            "audio_path": audio_path_str,
            "action": "ABSTAIN",
            "risk": "HIGH",
            "fallback_reason": f"Speech transcription failed: {exc}",
            "speech_result": None,
            "text_result": None
        }
        
    text = speech_result.get("text", "")
    speech_conf = speech_result.get("confidence", 0.0)
    
    # Gate 1: Speech Confidence Check
    if speech_conf < speech_confidence_threshold:
        return {
            "audio_path": audio_path_str,
            "action": "ABSTAIN",
            "risk": "HIGH",
            "confidence": speech_conf,
            "fallback_reason": "Speech confidence too low. Fall back to pictogram menu.",
            "speech_result": speech_result,
            "text_result": None
        }
        
    # Gate 2: Text Triage Pipeline
    text_result = triage_with_abstention(text)
    
    return {
        "audio_path": audio_path_str,
        "speech_result": speech_result,
        "text_result": text_result,
        "final_action": text_result.get("action"),
        "final_risk": text_result.get("risk")
    }


# -------------------------
# CLI / Demo
# -------------------------


def run_demo() -> None:
    # Since we don't have real audio files right now, we will pass 
    # "fake" filenames to the mock transcriber to simulate different scenarios.
    
    fake_audio_files = [
        "recording_crop_loss.wav",
        "recording_wage_work.wav",
        "recording_pension_delay.wav",
        "recording_bad_noise.wav",
        "recording_vague.wav"
    ]
    
    print(f"Using STT Backend: {STT_BACKEND}\n")
    
    for fake_file in fake_audio_files:
        result = pipeline_from_audio(fake_file)
        print(f"Audio: {fake_file}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("-" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HaqSetu Speech-to-Text Triage Pipeline."
    )
    
    parser.add_argument(
        "--audio",
        help="Path to a real .wav audio file.",
    )
    
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run mock audio demo.",
    )
    
    args = parser.parse_args()
    
    if args.demo:
        run_demo()
        return
        
    if not args.audio:
        parser.error("Provide --audio <path.wav> or --demo.")
        
    result = pipeline_from_audio(args.audio)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()