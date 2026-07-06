import logging
import re
import time

logger = logging.getLogger(__name__)


class SMSMixin:
    def read_sms(self, regex_pattern=None, timeout=30, device_id=None, after_timestamp=None):
        start_time = time.time()

        initial_delay = min(3, timeout)
        if initial_delay > 0:
            time.sleep(initial_delay)

        poll_count = 0

        while True:
            try:
                cmd = ["shell", "content", "query", "--uri", "content://sms/inbox", "--projection", "body,date"]
                stdout_str, _ = self._run_adb(cmd, device_id=device_id)

                messages = []
                for line in stdout_str.splitlines():
                    if not line.startswith("Row:"):
                        continue
                    body_match = re.search(r'body=(.*?), date=', line)
                    date_match = re.search(r'date=(\d+)', line)

                    if body_match and date_match:
                        body_text = body_match.group(1).strip()
                        date_val = int(date_match.group(1))

                        if after_timestamp and date_val <= after_timestamp:
                            continue

                        msg_dict = {"body": body_text, "date": date_val, "extract": None}

                        if regex_pattern:
                            extract_match = re.search(regex_pattern, body_text)
                            if extract_match:
                                msg_dict["extract"] = extract_match.group(0)
                                messages.append(msg_dict)
                        else:
                            messages.append(msg_dict)

                if regex_pattern and len(messages) > 0:
                    messages.sort(key=lambda x: x["date"], reverse=True)
                    return messages

                if not regex_pattern:
                    messages.sort(key=lambda x: x["date"], reverse=True)
                    return messages

            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"Failed to read SMS: {e}")

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                break

            poll_count += 1
            if poll_count <= 2:
                sleep_interval = 2.0
            elif poll_count <= 5:
                sleep_interval = 3.0
            else:
                sleep_interval = 5.0

            remaining = timeout - elapsed
            sleep_interval = min(sleep_interval, remaining)
            if sleep_interval > 0:
                time.sleep(sleep_interval)

        return []
