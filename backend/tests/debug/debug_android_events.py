
import time
import logging
import sys
from app.core.environment.controllers.android_event_recorder import AndroidEventRecorder

# Setup logging to see everything
logging.basicConfig(level=logging.DEBUG)

def test_recorder():
    device_id = "HYC5T19B11003570"
    recorder = AndroidEventRecorder()
    
    print(f"Starting recording on {device_id}...")
    recorder.start_recording(device_id)
    
    # Wait a bit for setup
    time.sleep(2)
    
    print("Simulating tap at 500, 500...")
    # Use adb to simulate a real tap while recording
    import subprocess
    subprocess.run(["adb", "-s", device_id, "shell", "input", "tap", "500", "500"])
    
    # Wait for events to be processed
    time.sleep(2)
    
    print("Stopping recording...")
    events = recorder.stop_recording()
    
    print(f"Captured {len(events)} events!")
    for i, e in enumerate(events):
        print(f"  Event {i}: {e.event_type} at ({e.x}, {e.y})")

if __name__ == "__main__":
    test_recorder()
