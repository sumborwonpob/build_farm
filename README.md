# Build Farm

A lightweight build orchestration UI for running repository test scripts, tracking build history, and monitoring Docker resources.

## Features

- Repository management (add, list, delete)
- Build execution with status tracking
- Build history with per-repository clearing
- Live stdout display for running builds on the dashboard
- Docker images/containers management and disk usage view

## Project Structure

```
build_farm/
├── README.md              # This file
├── install.sh             # Installation script (sets up venv and dependencies)
├── requirements.txt       # Python dependencies
├── venv/                  # Shared Python virtual environment (auto-created)
├── service/               # Service/systemd scripts
├── backend/               # Backend modules (core logic)
│   ├── __init__.py
│   ├── models.py         # Data models (Repository, Build)
│   ├── database.py       # SQLite database operations
│   ├── build_manager.py  # Build execution logic
│   └── workspace/        # Build execution directory (auto-created)
└── frontend/             # Streamlit UI
    ├── main.py           # Dashboard, Repositories, Build History, Docker Management
    ├── RUN_TEST_GUIDE.md # Test script requirements
    ├── run_test.sh.example         # Full example test runner
    ├── run_test_simple.sh.example  # Minimal example test runner
    ├── .streamlit/       # Streamlit configuration
    └── build_farm.db     # SQLite database (auto-created)
```

## Requirements

- Python 3.9+
- Git (for cloning repositories)
- Git credentials (SSH keys) already setup
- Docker (optional, for Docker Management page)

## Setup

1. Navigate to the project root:
   ```bash
   cd build_farm
   ```

2. Run the installation script to create the virtual environment and install dependencies:
   ```bash
   ./install.sh
   ```

3. Activate the virtual environment:
   ```bash
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

## Run

From the project root (with venv activated), start the Streamlit app:

```bash
cd frontend
streamlit run main.py
```

The app will be accessible at: **http://<machine_ip>:8080**

The app uses a local SQLite database file: `frontend/build_farm.db` (auto-created).
Build workspace: `backend/workspace/` (auto-created).

## Usage

Open your browser and navigate to **http://<machine_ip>:8080** to access the Build Farm UI.

### Add Repository

- Navigate to **Add Repository**.
- Provide name, SSH Git URL, branch, and optional description.
- The repository must contain a `run_test.sh` script in its root.

### Run Builds

- Use **Dashboard** or **Repositories** to trigger builds.
- The latest running build's stdout appears on the Dashboard under **Live Build Output**.

### Build History

- Filter by repository or view all builds.
- Clear build history for a specific repository using the **Clear Build History** action (confirmation required).

### Test Script Contract

Your repository must include a `run_test.sh` script. The script:

- Must exit with code `0` for success and non-zero for failure.
- Should optionally produce a `test_results.json` array containing:
  - `name` (string)
  - `success` (boolean)

See [frontend/RUN_TEST_GUIDE.md](frontend/RUN_TEST_GUIDE.md) for details.

## Notes

- Builds are executed in `backend/workspace/` and cleaned up after completion.
- For long-running builds, the UI auto-refreshes while builds are running.

## Service Scripts

The `service/` folder contains helper scripts to run the app as a system service.

## Troubleshooting

- If cloning fails, verify SSH keys and repository access.
- If builds hang, check the `run_test.sh` script for blocking commands.
- If `test_results.json` is invalid, the build will be marked as failed.
