
import subprocess
import time

def check_raw_output():
    device_id = "HYC5T19B11003570"
    # Use -t for timestamp, -c 10 to exit after 10 lines
    cmd = ["adb", "-s", device_id, "shell", "getevent", "-t", "/dev/input/event2"]
    
    print(f"Running: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0 # Unbuffered
    )
    
    print("Start tapping now! (5 seconds)")
    start_time = time.time()
    count = 0
    while time.time() - start_time < 5:
        # Check if any output
        line = process.stdout.readline()
        if line:
            count += 1
            print(f"[{count}] RAW: {line!r}")
        else:
            time.sleep(0.1)
    
    process.terminate()
    print(f"Done. Received {count} lines.")
    err = process.stderr.read()
    if err:
        print(f"STDERR: {err}")

if __name__ == "__main__":
    check_raw_output()
