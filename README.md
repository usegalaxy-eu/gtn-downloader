# GTN Downloader

The GitHub Action automates the process of downloading data from the Galaxy Training Network (GTN) repository and transferring it to a cloud storage Onedata using Oneclient. 
Here's how it works:

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
