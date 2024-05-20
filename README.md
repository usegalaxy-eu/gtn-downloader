# GTN Downloader

The GitHub Action automates the process of downloading data from the Galaxy Training Network (GTN) repository and transferring it to a cloud storage Onedata using Oneclient.

## How to access the data

The GTN data provided by the OneData store is accessible via:

* [OneData share](https://datahub.egi.eu/share/2697e33bd34f1870b0961414b8c77753chf583)
* via the OneData client and an read-only accessToken (see below)
* or via the OneData file-source plugin for example via the [European Galaxy server](https://usegalaxy.eu/)

To access the GTN vie OneData or include it in your Galaxy server use the following public read-only accessToken and configuration.
```yaml
- type: onedata
  id: gtn_public_onedata
  label: GTN training data
  doc: Training data from the Galaxy Training Network (powered by Onedata)
  # The access Token is public and can be shared
  accessToken: "MDAxY2xvY2F00aW9uIGRhdGFodWIuZWdpLmV1CjAwNmJpZGVudGlmaWVyIDIvbm1kL3Vzci00yNmI4ZTZiMDlkNDdjNGFkN2E3NTU00YzgzOGE3MjgyY2NoNTNhNS9hY3QvMGJiZmY1NWU4NDRiMWJjZGEwNmFlODViM2JmYmRhNjRjaDU00YjYKMDAxNmNpZCBkYXRhLnJlYWRvbmx5CjAwNDljaWQgZGF00YS5wYXRoID00gTHpaa1pUTTROMkl4WmpjMllXVmpOMlU00WWpreU5XWmtNV00ZpT1RKbU1ETXlZMmhoWTJReAowMDJmc2lnbmF00dXJlIIQvnXp01Oey02LnaNwEkFJAyArzhHN8SlXSYFsBbSkqdqCg"
  onezoneDomain: "datahub.egi.eu"
```

## How this repo works

1. **Triggering**: The action is triggered on a schedule (first day of each month at 23:30) 

2. **Environment Setup**: It runs on a Ubuntu environment and sets up necessary environment variables like `ONECLIENT_ACCESS_TOKEN` and `ONECLIENT_PROVIDER_HOST`, which are required for accessing the remote storage via Oneclient. These variables are retrieved from repository secrets.

3. **Workflow Steps**:
   - **Checkout Repository**: It checks out the current repository to access its contents.
   - **Clone GTN Repository**: It clones the GTN repository (`galaxyproject/training-material`) into the workspace for accessing the training materials.
   - **Set up Python**: Configures the Python environment.
   - **Install Dependencies**: Installs the Python dependencies listed in `requirements.txt`.
   - **Create Mount Directory**: Creates a directory (`$HOME/remote_storage_mount`) for mounting the remote storage.
   - **Install Oneclient**: Installs Oneclient using a bash script fetched from a specified URL.
   - **Set up Environment Variables**: Sets up environment variables required for Oneclient to access the remote storage.
   - **Mount Remote Storage**: Mounts the remote storage location using Oneclient.
   - **Run GTN-downloader Script**: Executes the Python script `bin/data-library-download.py`, which downloads GTN data from the cloned repository (`$GITHUB_WORKSPACE/training-material`) and saves it to the mounted remote storage location (`$HOME/remote_storage_mount/GTN data`).
   - **Unmount Remote Storage**: Unmounts the remote storage after the download process is complete.
