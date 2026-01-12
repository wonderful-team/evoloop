
import os
import re
import json

FRONTEND_DIR = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/frontend/src"
EN_JSON = os.path.join(FRONTEND_DIR, "locales/en.json")
ZH_JSON = os.path.join(FRONTEND_DIR, "locales/zh.json")

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def flatten_keys(data, parent_key=''):
    items = []
    for k, v in data.items():
        new_key = f"{parent_key}.{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_keys(v, new_key))
        else:
            items.append(new_key)
    return items

def scan_files():
    keys_in_code = set()
    # Match t("key") or t('key')
    pattern = re.compile(r't\([\'"]([\w\.]+)[\'"]')
    
    for root, dirs, files in os.walk(FRONTEND_DIR):
        for file in files:
            if file.endswith('.tsx') or file.endswith('.ts'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    matches = pattern.findall(content)
                    for m in matches:
                        keys_in_code.add(m)
    return keys_in_code

def check_missing():
    en_data = load_json(EN_JSON)
    zh_data = load_json(ZH_JSON)
    
    en_keys = set(flatten_keys(en_data))
    zh_keys = set(flatten_keys(zh_data))
    
    code_keys = scan_files()
    
    print("--- Missing in EN ---")
    for k in sorted(code_keys):
        # Allow dynamic keys or partial matches if needed, but for now strict
        if k not in en_keys:
             # loose check for "common.errors.xyz" vs "common.errors"
             print(k)

    print("\n--- Missing in ZH ---")
    for k in sorted(code_keys):
        if k not in zh_keys:
            print(k)

if __name__ == "__main__":
    check_missing()
