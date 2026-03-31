
import subprocess
import time
import sys

def check_char_output():
    device_id = "HYC5T19B11003570"
    cmd = ["adb", "-s", device_id, "shell", "getevent", "-t", "/dev/input/event2"]
    
    print(f"Running: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # Merge stderr to stdout
        bufsize=0
    )
    
    print("Start tapping now! (5 seconds)")
    start_time = time.time()
    collected = []
    
    # Set non-blocking read if possible, but let's just try read(1) with a timeout
    import os
    import fcntl
    fd = process.stdout.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    while time.time() - start_time < 5:
        try:
            char = process.stdout.read(1)
            if char:
                sys.stdout.buffer.write(char)
                sys.stdout.buffer.flush()
                collected.append(char)
        except BlockingIOError:
            time.sleep(0.01)
    
    process.terminate()
    print(f"\nDone. Collected {len(collected)} bytes.")

if __name__ == "__main__":
    check_char_output()
