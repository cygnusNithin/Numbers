import requests

url = "https://www.diskwala.com/app/69e4133569eabf872087c789"  # must be a valid direct link
headers = {
    "User-Agent": "Mozilla/5.0",
    # If required, include cookies or Authorization headers from your logged-in session
    # "Cookie": "session=...",
    # "Authorization": "Bearer <token>",
}

with requests.get(url, headers=headers, stream=True, timeout=60) as r:
    r.raise_for_status()
    with open("output.bin", "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

print("Download complete")