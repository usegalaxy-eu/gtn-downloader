#!/usr/bin/env python3
import os
import re
import yaml
import ftplib
import shutil
import requests
import time
from urllib.parse import urlparse, unquote, quote
from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError

# Config
PROVIDER = os.environ.get("ONECLIENT_PROVIDER_HOST")
SPACE_ID = os.environ.get("ONEPROVIDER_SPACE_ID")
ROOT_ID = os.environ.get("ONEPROVIDER_ROOT_ID")
TOKEN = os.environ.get("ONEPROVIDER_REST_ACCESS_TOKEN")
TMP_DIR = "/tmp/gtn-api-upload"
HTTP_DOWNLOAD_RETRIES = int(os.environ.get("HTTP_DOWNLOAD_RETRIES", "3"))
HTTP_RETRY_BACKOFF_SECONDS = int(os.environ.get("HTTP_RETRY_BACKOFF_SECONDS", "20"))
HTTP_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


# Utility helpers


def sanitize_name(name: str) -> str:
    """Replace unsafe characters for folder names.
    Plan for next updates is to delete this function and use quote (then no issues with folder names)
    """
    return re.sub(r'[\\/:\*,?"<>|%.#!@$&\'\(\)\[\]{} ]', "-", str(name or ""))


def get_safe_filename_from_url(url):
    """Extract correct filename from URL, handling Zenodo /content links."""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parts[-1] == "content" and len(parts) > 1:
        filename = parts[-2]
    else:
        filename = parts[-1]
    return unquote(filename)


def ensure_tmp_clean():
    """Ensure /tmp folder is fresh for each CI run."""
    if os.path.exists(TMP_DIR):
        shutil.rmtree(TMP_DIR, ignore_errors=True)
    os.makedirs(TMP_DIR, exist_ok=True)


# Onedata API helpers


def get_children(parent_id):
    """Return list of child entries (dicts) under given Onedata folder ID."""
    url = f"https://{PROVIDER}/api/v3/oneprovider/data/{parent_id}/children"
    headers = {"X-Auth-Token": TOKEN}
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 200:
        return r.json().get("children", [])
    return []


def get_child_id(parent_id, name):
    """Return fileId of a child by name (folder or file)."""
    for child in get_children(parent_id):
        if child.get("name") == name:
            return child.get("fileId")
    return None


def create_directory(parent_id, name):
    """Create folder in Onedata."""
    if not name:
        print("⚠️ Skipping directory creation — empty name.")
        return None

    safe_name = quote(name, safe="")

    url = f"https://{PROVIDER}/api/v3/oneprovider/data/{parent_id}/children?name={safe_name}&type=DIR"
    headers = {"X-Auth-Token": TOKEN}
    r = requests.post(url, headers=headers)

    if r.status_code == 201:
        print(f"📁 Created dir: {name}")
        return r.json()["fileId"]

    elif r.status_code == 400 and "eexist" in r.text.lower():
        print(f"ℹ️ Directory exists: {name}")
        return get_child_id(parent_id, name)

    else:
        print(f"❌ Failed to create dir '{name}': {r.status_code} - {r.text}")
        return None


def file_exists(parent_id, name):
    """Check if a file with given name already exists in parent folder."""
    return any(child.get("name") == name for child in get_children(parent_id))


def upload_file(parent_id, local_path, dest_name):
    """Upload one file into Onedata folder."""
    if not os.path.exists(local_path):
        print(f"⚠️ Local file not found: {local_path}")
        return False

    safe_name = quote(dest_name, safe="")
    url = f"https://{PROVIDER}/api/v3/oneprovider/data/{parent_id}/children?name={safe_name}"
    headers = {"X-Auth-Token": TOKEN, "Content-Type": "application/octet-stream"}

    print(f"➡️ Uploading: {local_path} → {dest_name}")

    with requests.Session() as session:
        try:
            with open(local_path, "rb") as f:
                r = session.post(url, headers=headers, data=f, timeout=(30, 3600))
        except requests.exceptions.SSLError as e:
            print(f"⚠️ SSL error during upload: {e}")
            print("🔁 Retrying with SSL verify disabled (temporary fallback)...")
            with open(local_path, "rb") as f:
                r = session.post(
                    url, headers=headers, data=f, timeout=(30, 3600), verify=False
                )

    if r.status_code == 201:
        print(
            f"✅ Uploaded {dest_name} ({os.path.getsize(local_path) / (1024**2):.2f} MB)"
        )
        os.remove(local_path)
        return True

    elif r.status_code == 400 and "eexist" in r.text.lower():
        print(f"ℹ️ File already exists: {dest_name}")
        os.remove(local_path)
        return True

    else:
        print(f"❌ Upload failed for {dest_name}: {r.status_code} - {r.text}")
        os.remove(local_path)
        return False


# Download handlers


def download_http(download_url, dest_path):
    """Download a file via HTTP/HTTPS."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    print(f"➡️ HTTP download: {download_url}")
    for attempt in range(1, HTTP_DOWNLOAD_RETRIES + 1):
        if os.path.isfile(dest_path):
            os.remove(dest_path)

        try:
            with requests.get(download_url, stream=True, timeout=(10, 120)) as r:
                if r.status_code in (403, 404):
                    print(f"🚫 Skipping ({r.status_code}): {download_url}")
                    return None

                if r.status_code in HTTP_RETRY_STATUS_CODES:
                    raise HTTPError(
                        f"{r.status_code} transient error for url: {download_url}",
                        response=r,
                    )

                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    downloaded = 0
                    for chunk in r.iter_content(chunk_size=512 * 1024):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if downloaded >= 100 * 1024 * 1024:
                                print(
                                    f"📥 Downloaded {downloaded / (1024**2):.1f} MB..."
                                )
                                downloaded = 0

            print(f"✅ Downloaded: {dest_path}")
            return dest_path

        except (Timeout, ConnectionError, HTTPError, RequestException) as e:
            is_retryable = not isinstance(e, HTTPError)
            if isinstance(e, HTTPError) and e.response is not None:
                is_retryable = e.response.status_code in HTTP_RETRY_STATUS_CODES

            if not is_retryable:
                print(f"🚫 Skipping non-retryable HTTP error: {e}")
                return None

            if attempt >= HTTP_DOWNLOAD_RETRIES:
                print(
                    f"⚠️ Giving up after {HTTP_DOWNLOAD_RETRIES} HTTP download attempts: {download_url}"
                )
                return None

            wait_seconds = HTTP_RETRY_BACKOFF_SECONDS * attempt
            print(
                f"⚠️ HTTP download failed on attempt {attempt}/{HTTP_DOWNLOAD_RETRIES}: {e}"
            )
            print(f"🔁 Retrying in {wait_seconds}s...")
            time.sleep(wait_seconds)

    return None


def download_ftp(download_url, dest_path):
    """Download a file via FTP."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    print(f"➡️ FTP download: {download_url}")
    ftp_host = download_url.split("://")[1].split("/")[0]
    ftp_path = "/".join(download_url.split("/")[3:])
    try:
        ftp = ftplib.FTP(ftp_host)
        ftp.login()
        with open(dest_path, "wb") as f:
            ftp.retrbinary(f"RETR {ftp_path}", f.write)
        ftp.quit()
        print(f"✅ FTP downloaded: {dest_path}")
        return dest_path
    except Exception as e:
        print(f"⚠️ FTP failed: {e}")
        return None


def download_file(download_url, dest_path):
    """Wrapper: select HTTP or FTP downloader."""
    if download_url.startswith("ftp://"):
        return download_ftp(download_url, dest_path)
    else:
        return download_http(download_url, dest_path)


# File upload handler


def handle_file_upload(url, parent_id):
    """Download file to tmp, upload to Onedata, then clean up."""
    raw_name = get_safe_filename_from_url(url)
    filename = raw_name

    if file_exists(parent_id, filename):
        print(f"⏩ Skipping (already exists): {filename}")
        return

    tmp_path = os.path.join(TMP_DIR, filename)
    local_file = download_file(url, tmp_path)
    if not local_file:
        return

    if upload_file(parent_id, local_file, filename):
        print(f"🧹 Upload complete and temp file cleaned: {local_file}")
    else:
        if os.path.exists(local_file):
            os.remove(local_file)
        print(f"⚠️ Failed upload for {filename}")


# YAML parsing and processing


def process_yaml(yaml_path, parent_id):
    """Parse a YAML and mirror its structure + upload all files."""
    print(f"➡️ Processing {yaml_path}")
    with open(yaml_path, "r") as f:
        try:
            data = yaml.safe_load(f)
        except Exception as e:
            print(f"⚠️ Invalid YAML {yaml_path}: {e}")
            return

    dest_name = sanitize_name(data.get("destination", {}).get("name", "Unknown"))
    dest_id = create_directory(parent_id, dest_name)
    if not dest_id:
        return

    for topic in data.get("items", []):
        topic_name = sanitize_name(topic.get("name", "Unnamed-Topic"))
        topic_id = create_directory(dest_id, topic_name)
        if not topic_id:
            continue

        for tutorial in topic.get("items", []):
            tut_name = sanitize_name(tutorial.get("name", "Tutorial"))
            tut_id = create_directory(topic_id, tut_name)
            if not tut_id:
                continue

            items = tutorial.get("items", [])
            has_direct_urls = any("url" in i for i in items)

            # direct URLs under tutorial
            if has_direct_urls:
                for item in items:
                    url = item.get("url")
                    if url:
                        handle_file_upload(url, tut_id)
                continue

            # nested DOI-level structure
            for doi in items:
                doi_name = sanitize_name(doi.get("name", ""))
                doi_id = create_directory(tut_id, doi_name)
                if not doi_id:
                    continue
                for item in doi.get("items", []):
                    url = item.get("url")
                    if url:
                        handle_file_upload(url, doi_id)


# MAIN


def main():
    if not TOKEN:
        print("❌ Missing ONEPROVIDER_REST_ACCESS_TOKEN")
        return

    ensure_tmp_clean()

    print("🔍 Preparing main folder: GTN data")
    sandbox_id = ROOT_ID

    for root, _, files in os.walk("training-material"):
        for file in files:
            if file == "data-library.yaml":
                yaml_path = os.path.join(root, file)
                process_yaml(yaml_path, sandbox_id)

    print("✅ Finished full upload run.")


if __name__ == "__main__":
    main()
