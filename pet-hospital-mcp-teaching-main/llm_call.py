import configparser
import codecs
import json
import time
import requests

cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")
API_KEY = cfg["llm"]["api_key"]
BASE_URL = cfg["llm"]["base_url"].rstrip("/")
MODEL = cfg["llm"]["model"]


def call_llm(prompt: str) -> None:
    url = f"{BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "stream": True}
    with requests.post(url, headers=headers, json=payload, timeout=60, stream=True) as resp:
        if resp.status_code != 200:
            print(f"请求失败 {resp.status_code}: {resp.text}")
            return
        decoder = codecs.getincrementaldecoder("utf-8")()
        buf = ""
        for raw in resp.iter_content(1024):
            buf += decoder.decode(raw)
            while "\n\n" in buf:
                event, buf = buf.split("\n\n", 1)
                data = ""
                for line in event.split("\n"):
                    if line.startswith("data:"):
                        data += line[5:]
                data = data.strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    delta = json.loads(data)["choices"][0]["delta"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                text = delta.get("content") or ""
                for ch in text:
                    print(ch, end="", flush=True)
                    time.sleep(0.03)
        print()


if __name__ == "__main__":
    prompt = input("prompt> ")
    call_llm(prompt)
