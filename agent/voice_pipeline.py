"""
The Voice Pipeline
Connects the Brain to the physical speakers.
"""
import sys
import os

# Add parent dir to path so we can import the engine
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.solution_generator import generate_spoken_solution

def speak(text: str):
    """Speaks the text out loud using offline Windows TTS."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        # Optional: Adjust speed and volume
        engine.setProperty('rate', 150) 
        engine.setProperty('volume', 1.0)
        print(f"\n🔊 [SPEAKING OUT LOUD]: {text}\n")
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"⚠️ Voice engine failed ({e}). Printing text instead:")
        print(text)

if __name__ == "__main__":
    print("🏛️ HAQSETU AGENT BOOTING UP...")
    print("Listening to villager... (Simulated)")
    
    # Simulate the villager saying: "My crop was destroyed, what do I do?"
    # The backend processes it and returns this data:
    scheme = "crop_loss"
    outcome = "include"
    ttbr = {"ttbr_days": 7, "bottleneck": {"task": "patwari_verification"}}
    
    # 1. Generate the solution
    script = generate_spoken_solution(scheme, outcome, {}, ttbr)
    
    # 2. Speak it
    speak(script)