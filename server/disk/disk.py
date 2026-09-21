import requests

# Paste the URL you copied from the Network tab here
captured_direct_url = "https://www.diskwala.com/app/69e4133569eabf872087c789"

def force_download(direct_url, filename="project_alpha_video.mp4"):
    # We still use the App Header to ensure the file server doesn't block us
    headers = {
        'User-Agent': 'okhttp/4.9.3',
        'X-Requested-With': 'com.diskwalaapp'
    }

    print("🚀 Direct Stream Found. Bypassing App restrictions...")
    
    try:
        with requests.get(direct_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(filename, 'wb') as f:
                print("Downloading...")
                for chunk in r.iter_content(chunk_size=1024*1024): # 1MB chunks
                    f.write(chunk)
        print(f"✅ Download Complete: {filename}")
    except Exception as e:
        print(f"❌ Download failed: {e}")

force_download(captured_direct_url)


# test_url = "https://www.diskwala.com/app/69e4133569eabf872087c789"
