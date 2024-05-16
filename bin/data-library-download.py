import os
import yaml
import re
import argparse
import requests
from urllib.parse import urlparse, unquote
import time
import ftplib

def process_yaml(yaml_path, output_dir, summary_file):
    with open(yaml_path, 'r') as file:
        data = yaml.safe_load(file)

    destination_name = sanitize_name(data['destination']['name'])
    topics = data['items']

    for topic in topics:
        topic_name = sanitize_name(topic['name'])
        topic_path = os.path.join(output_dir, destination_name, topic_name)

        # process URLs at the topic level
        process_urls(topic_path, topic.get('items', []), summary_file)

        tutorials = topic['items']
        for tutorial in tutorials:
            tutorial_name = sanitize_name(tutorial['name'])
            tutorial_path = os.path.join(topic_path, tutorial_name)

            # process URLs at the tutorial level
            process_urls(tutorial_path, tutorial.get('items', []), summary_file)

            dois = tutorial.get('items', [])
            for doi in dois:
                doi_name = sanitize_name(doi.get('name', ''))
                doi_path = os.path.join(tutorial_path, doi_name)

                if not os.path.exists(doi_path):
                    os.makedirs(doi_path)

                # process URLs at the DOI level
                process_urls(doi_path, doi.get('items', []), summary_file)


def process_urls(output_path, items, summary_file):
    for entry in items:
        url = entry.get('url', '')
        if url:
            # download files if they don't exist in the output dir
            download_url = unquote(url)
            filename = os.path.join(output_path, os.path.basename(urlparse(download_url).path))

            # create the output dir
            os.makedirs(output_path, exist_ok=True)

            # check if the file already exists, if yes, skip the download
            if os.path.exists(filename):
                status = 'Download skipped (File already exists)'
                file_size = os.path.getsize(filename)
            else:
                try:
                    # Check if URL starts with 'ftp://' for FTP downloads
                    if download_url.startswith('ftp://'):
                        ftp = ftplib.FTP(download_url.split('://')[1].split('/')[0])
                        ftp.login()
                        ftp.cwd('/'.join(download_url.split('/')[3:-1]))
                        with open(filename, 'wb') as file:
                            ftp.retrbinary('RETR ' + download_url.split('/')[-1], file.write)
                        ftp.quit()
                        status = 'Downloaded'
                        file_size = os.path.getsize(filename)
                    else:
                        # Handle HTTP downloads
                        with requests.get(download_url, stream=True) as response:
                            response.raise_for_status()
                            with open(filename, 'wb') as file:
                                for chunk in response.iter_content(chunk_size=1024 * 1024 * 1024):  # 100 MB chunks
                                    if chunk:
                                        file.write(chunk)
                        status = 'Downloaded'
                        file_size = os.path.getsize(filename)
                except Exception as e:
                    # If an error occurs during download, delete partially downloaded file if exists
                    if os.path.exists(filename):
                        os.remove(filename)
                    status = f"Error downloading file from {download_url}: {e}"
                    file_size = 0

            # update urls.tsv and download-summary.tsv
            update_urls_file(output_path, url, status, file_size, summary_file)


def update_urls_file(output_path, url, status, file_size, summary_file):

    # Update download summary file
    with open(summary_file, 'a') as summary:
        summary.write(f"{output_path}\t{url}\t{status}\t{file_size}\n")

def sanitize_name(name):
    # replace suspicious characters with -
    return re.sub(r'[\\/:\*,?"<>|%.#!@$&\'\(\)\[\]{} ]', '-', name)

def write_summary_header(summary_file):
    summary_dir = os.path.dirname(summary_file)
    os.makedirs(summary_dir, exist_ok=True)  # create the dir

    with open(summary_file, 'w') as file:
        file.write("Path\tURL\tStatus\tFile Size\n")


def calculate_overall_size(summary_file):
    overall_size = 0
    with open(summary_file, 'r') as file:
        next(file)
        for line in file:
            _, _, _, file_size_str = line.strip().split('\t')
            overall_size += int(file_size_str)

    # write the overall summary to the first line of the table
    with open(summary_file, 'r+') as file:
        content = file.read()
        file.seek(0, 0)
        file.write(f"Overall\t\t\t{overall_size}\n{content}")


def main():
    start_time = time.time()

    parser = argparse.ArgumentParser(description='process data-library.yaml files and create output directory structure.')
    parser.add_argument('--input', dest='project_dir', required=True, help='path to the training-material directory')
    parser.add_argument('--output', dest='output_dir', required=True, help='path to the output directory where to '
                                                                           'download data and summary file')

    args = parser.parse_args()

    summary_file = os.path.join(args.output_dir, 'download-summary.tsv')
    write_summary_header(summary_file)

    for root, dirs, files in os.walk(args.project_dir):
        for file in files:
            if file == 'data-library.yaml':
                yaml_path = os.path.join(root, file)
                process_yaml(yaml_path, args.output_dir, summary_file)

    # sum up all values of file sizes
    calculate_overall_size(summary_file)

    end_time = time.time()
    print(f"Script run time: {end_time - start_time} seconds")

if __name__ == '__main__':
    main()
