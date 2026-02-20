import streamlit as st
from datetime import datetime
import time
import json
import subprocess
import shutil
import sys
from pathlib import Path

# Add parent directory to path to import backend module
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import Database, BuildManager

# Set page config
st.set_page_config(
    page_title="Build Farm",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database and build manager
db = Database()
build_manager = BuildManager()

# Cleanup stale running builds from previous crashes (only once per session)
if "cleanup_done" not in st.session_state:
    db.cleanup_stale_running_builds()
    st.session_state.cleanup_done = True

# Custom CSS
st.markdown("""
<style>
    .status-success { color: #00cc00; font-weight: bold; }
    .status-failed { color: #ff0000; font-weight: bold; }
    .status-running { color: #ff9900; font-weight: bold; }
    .status-pending { color: #666666; font-weight: bold; }
    .status-error { color: #cc0000; font-weight: bold; }
    .build-card {
        padding: 15px;
        border-radius: 5px;
        background-color: #f0f2f6;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar navigation
st.sidebar.title("🏗️ Build Farm")
page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Repositories", "Build History", "Add Repository", "Storage Management", "Settings"]
)

st.sidebar.divider()
st.sidebar.write(f"**Running Builds:** {build_manager.get_running_builds_count()}")


# Helper functions
def get_status_badge(status: str) -> str:
    """Return HTML badge for build status."""
    status_map = {
        'success': ('✅', 'status-success'),
        'failed': ('❌', 'status-failed'),
        'running': ('⏳', 'status-running'),
        'pending': ('⏸️', 'status-pending'),
        'error': ('💥', 'status-error'),
        'terminated': ('⏹️', 'status-error')
    }
    icon, css_class = status_map.get(status, ('❓', ''))
    return f'<span class="{css_class}">{icon} {status.upper()}</span>'


def format_duration(seconds: float) -> str:
    """Format duration in human readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def extract_latest_stdout(logs: str) -> str:
    """Extract stdout section from logs for live display."""
    if not logs:
        return ""
    if "=== STDOUT (live) ===" in logs:
        return logs.split("=== STDOUT (live) ===", 1)[1].strip()
    if "=== STDOUT ===" in logs:
        stdout_part = logs.split("=== STDOUT ===", 1)[1]
        if "=== STDERR ===" in stdout_part:
            stdout_part = stdout_part.split("=== STDERR ===", 1)[0]
        return stdout_part.strip()
    return logs.strip()


# Docker helper functions
def get_disk_space() -> dict:
    """Get disk space information in GB."""
    try:
        usage = shutil.disk_usage("/")
        return {
            "total": usage.total / (1024**3),
            "used": usage.used / (1024**3),
            "free": usage.free / (1024**3),
            "percent": (usage.used / usage.total) * 100
        }
    except Exception as e:
        return {"error": str(e)}


def get_docker_images() -> list:
    """Get list of all Docker images."""
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"],
            capture_output=True,
            text=True,
            check=True
        )
        images = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('\t')
                images.append({
                    "id": parts[0][:12],  # Short ID
                    "id_full": parts[0],
                    "repository": parts[1],
                    "tag": parts[2],
                    "size": parts[3],
                    "created": parts[4]
                })
        return images
    except Exception as e:
        return []


def get_docker_containers() -> list:
    """Get list of all Docker containers."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True,
            text=True,
            check=True
        )
        containers = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('\t')
                containers.append({
                    "id": parts[0][:12],  # Short ID
                    "id_full": parts[0],
                    "name": parts[1],
                    "image": parts[2],
                    "status": parts[3],
                    "ports": parts[4] if len(parts) > 4 else ""
                })
        return containers
    except Exception as e:
        return []


def delete_docker_image(image_id: str) -> tuple:
    """Delete a Docker image by ID. Returns (success, message)"""
    try:
        result = subprocess.run(
            ["docker", "rmi", "-f", image_id],
            capture_output=True,
            text=True,
            check=True
        )
        return True, f"Successfully deleted image {image_id}"
    except subprocess.CalledProcessError as e:
        return False, f"Failed to delete image: {e.stderr}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def stop_docker_container(container_id: str) -> tuple:
    """Stop a Docker container. Returns (success, message)"""
    try:
        result = subprocess.run(
            ["docker", "stop", container_id],
            capture_output=True,
            text=True,
            check=True
        )
        return True, f"Successfully stopped container {container_id}"
    except subprocess.CalledProcessError as e:
        return False, f"Failed to stop container: {e.stderr}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def delete_docker_container(container_id: str) -> tuple:
    """Delete a Docker container. Returns (success, message)"""
    try:
        result = subprocess.run(
            ["docker", "rm", "-f", container_id],
            capture_output=True,
            text=True,
            check=True
        )
        return True, f"Successfully deleted container {container_id}"
    except subprocess.CalledProcessError as e:
        return False, f"Failed to delete container: {e.stderr}"
    except Exception as e:
        return False, f"Error: {str(e)}"


# ==================== DASHBOARD PAGE ====================
if page == "Dashboard":
    st.title("📊 Build Dashboard")
    
    repos = db.get_all_repositories()
    
    if not repos:
        st.info("No repositories configured yet. Go to 'Add Repository' to get started.")
    else:
        # Metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Repositories", len(repos))
        with col2:
            recent_builds = db.get_recent_builds(limit=100)
            success_count = sum(1 for b in recent_builds if b.status == 'success')
            st.metric("Recent Successful Builds", success_count)
        with col3:
            st.metric("Running Builds", build_manager.get_running_builds_count())
        
        st.divider()

        # Live stdout for the latest running build
        running_build = db.get_latest_running_build()
        if running_build:
            repo = db.get_repository(running_build.repo_id)
            st.subheader("🟢 Live Build Output")
            st.caption(f"Build #{running_build.id} - {repo.name if repo else 'Unknown'} - Status: {running_build.status}")
            
            # Debug: show raw logs
            if running_build.logs:
                st.caption(f"Logs length: {len(running_build.logs)} chars")
                with st.expander("🔍 Debug: Raw logs"):
                    st.code(running_build.logs, language="text")
            
            stdout_text = extract_latest_stdout(running_build.logs or "")
            if not stdout_text:
                st.info("No stdout yet.")
            else:
                max_chars = 8000
                if len(stdout_text) > max_chars:
                    stdout_text = stdout_text[-max_chars:]
                st.code(stdout_text, language="bash")
            st.divider()
        
        # Repository status cards
        st.subheader("Repositories")
        
        for repo in repos:
            latest_build = db.get_latest_build_for_repo(repo.id)
            
            col1, col2, col3 = st.columns([3, 2, 1])
            
            with col1:
                st.markdown(f"### {repo.name}")
                st.caption(repo.git_url)
                if repo.description:
                    st.write(repo.description)
            
            with col2:
                if latest_build:
                    st.markdown("**Latest Build:**")
                    st.markdown(get_status_badge(latest_build.status), unsafe_allow_html=True)
                    if latest_build.commit_hash:
                        st.caption(f"Commit: {latest_build.commit_hash}")
                    if latest_build.start_time:
                        st.caption(f"Time: {latest_build.start_time.strftime('%Y-%m-%d %H:%M')}")
                else:
                    st.info("No builds yet")
            
            with col3:
                if st.button("🚀 Build", key=f"build_{repo.id}"):
                    build_id = build_manager.start_build(repo.id)
                    st.success(f"Build #{build_id} started!")
                    time.sleep(1)
                    st.rerun()
                
                # Show terminate button if build is running
                if latest_build and latest_build.status == 'running':
                    if st.button("⏹️ Terminate", key=f"term_{repo.id}"):
                        success = build_manager.terminate_build(latest_build.id)
                        if success:
                            st.warning(f"Termination signal sent for Build #{latest_build.id}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Could not terminate build")
                    st.rerun()
            
            st.divider()
        
        # Auto-refresh
        if build_manager.get_running_builds_count() > 0:
            st.info("🔄 Page will auto-refresh while builds are running...")
            time.sleep(5)
            st.rerun()


# ==================== REPOSITORIES PAGE ====================
elif page == "Repositories":
    st.title("📦 Repositories")
    
    repos = db.get_all_repositories()
    
    if not repos:
        st.info("No repositories configured.")
    else:
        for repo in repos:
            with st.expander(f"📦 {repo.name}"):
                st.write(f"**Git URL:** {repo.git_url}")
                st.write(f"**Branch:** {repo.branch}")
                if repo.description:
                    st.write(f"**Description:** {repo.description}")
                st.write(f"**Created:** {repo.created_at.strftime('%Y-%m-%d %H:%M') if repo.created_at else 'Unknown'}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🚀 Run Build", key=f"run_{repo.id}"):
                        build_id = build_manager.start_build(repo.id)
                        st.success(f"Build #{build_id} started!")
                        time.sleep(1)
                        st.rerun()
                
                with col2:
                    if st.button("🗑️ Delete", key=f"del_{repo.id}"):
                        db.delete_repository(repo.id)
                        st.success(f"Deleted {repo.name}")
                        time.sleep(1)
                        st.rerun()


# ==================== BUILD HISTORY PAGE ====================
elif page == "Build History":
    st.title("📜 Build History")
    
    # Filter options
    col1, col2 = st.columns([3, 1])
    with col1:
        repos = db.get_all_repositories()
        repo_options = {"All Repositories": None}
        repo_options.update({repo.name: repo.id for repo in repos})
        selected_repo = st.selectbox("Filter by Repository", list(repo_options.keys()))
    
    with col2:
        limit = st.number_input("Limit", min_value=10, max_value=500, value=50)

    # Clear build history for a specific repository
    repo_id = repo_options[selected_repo]
    if repo_id:
        st.warning("⚠️ This will permanently delete all build history for the selected repository.")
        confirm_clear = st.checkbox("I understand this cannot be undone", key="confirm_clear_build_history")
        if st.button("🧹 Clear Build History", key="clear_build_history"):
            if not confirm_clear:
                st.error("Please confirm before clearing build history.")
            else:
                db.clear_build_history_for_repo(repo_id)
                st.success("Build history cleared.")
                time.sleep(1)
                st.rerun()
    
    # Get builds
    if repo_id:
        builds = db.get_builds_for_repo(repo_id, limit=limit)
    else:
        builds = db.get_recent_builds(limit=limit)
    
    if not builds:
        st.info("No builds found.")
    else:
        for build in builds:
            repo = db.get_repository(build.repo_id)
            
            with st.expander(
                f"{get_status_badge(build.status)} Build #{build.id} - {repo.name if repo else 'Unknown'} "
                f"({build.start_time.strftime('%Y-%m-%d %H:%M') if build.start_time else 'No time'})",
                expanded=False
            ):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Repository:** {repo.name if repo else 'Unknown'}")
                    st.write(f"**Status:** {build.status}")
                    st.write(f"**Exit Code:** {build.exit_code if build.exit_code is not None else 'N/A'}")
                
                with col2:
                    if build.commit_hash:
                        st.write(f"**Commit:** {build.commit_hash}")
                    if build.commit_message:
                        st.write(f"**Message:** {build.commit_message}")
                    if build.duration:
                        st.write(f"**Duration:** {format_duration(build.duration)}")
                    if build.test_duration:
                        st.write(f"**Test Duration:** {format_duration(build.test_duration)}")
                
                # Display individual test results if available
                if build.test_results:
                    try:
                        test_results = json.loads(build.test_results)
                        st.markdown("**Test Results:**")
                        
                        # Display as a table
                        for test in test_results:
                            test_name = test.get('name', 'Unknown')
                            test_success = test.get('success', False)
                            status_icon = '✅' if test_success else '❌'
                            st.write(f"{status_icon} {test_name}")
                    except Exception as e:
                        st.caption(f"Could not parse test results: {e}")
                
                if build.logs:
                    st.markdown("**Logs:**")
                    st.code(build.logs, language="bash")


# ==================== ADD REPOSITORY PAGE ====================
elif page == "Add Repository":
    st.title("➕ Add Repository")
    
    with st.form("add_repo_form"):
        name = st.text_input("Repository Name", placeholder="my-project")
        git_url = st.text_input(
            "Git URL (SSH)", 
            placeholder="git@github.com:user/repo.git"
        )
        branch = st.text_input("Branch", value="main")
        description = st.text_area("Description (optional)")
        
        submitted = st.form_submit_button("Add Repository")
        
        if submitted:
            if not name or not git_url:
                st.error("Name and Git URL are required!")
            else:
                try:
                    repo_id = db.add_repository(name, git_url, branch, description)
                    st.success(f"✅ Repository '{name}' added successfully!")
                    st.info("Make sure your repository contains a `run_test.sh` script.")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding repository: {e}")
    
    st.divider()
    
    # Read RUN_TEST_GUIDE.md and display it
    try:
        from pathlib import Path
        guide_path = Path(__file__).parent / "RUN_TEST_GUIDE.md"
        with open(guide_path, 'r') as f:
            guide_content = f.read()
        st.markdown(guide_content)
    except Exception as e:
        st.error(f"Error loading guide: {e}")
        st.markdown("""
        ### Requirements
        - Repository must be accessible via SSH (SSH key already configured)
        - Repository must contain a `run_test.sh` script in the root
        - The test script should exit with code 0 for success, non-zero for failure
        - Must create `test_results.json` with test results
        """)


# ==================== STORAGE MANAGEMENT PAGE ====================
elif page == "Storage Management":
    st.title("💾 Storage Management")
    
    # Workspace section
    st.subheader("📁 Build Workspace")
    
    try:
        workspace_folders = build_manager.get_workspace_info()
        
        if not workspace_folders:
            st.info("No workspace folders found.")
        else:
            total_size_bytes = sum(f['size_bytes'] for f in workspace_folders)
            total_size_display = build_manager._format_size(total_size_bytes)
            
            st.write(f"**Total: {len(workspace_folders)} folder(s), {total_size_display}**")
            
            # Show folders in a table
            for folder in workspace_folders:
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**{folder['name']}**")
                    st.caption(f"Size: {folder['size_display']}")
                
                with col2:
                    st.write("")  # Spacing
                
                st.divider()
        
        # Cleanup button
        st.write("")
        if st.button("🗑️ Clean Up Workspace", help="Delete all folders except those with running builds"):
            with st.spinner("Cleaning up workspace..."):
                deleted, kept, msg = build_manager.cleanup_workspace()
                if deleted > 0:
                    st.success(f"✅ {msg}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.info(msg)
    
    except Exception as e:
        st.error(f"❌ Error managing workspace: {str(e)}")
    
    st.divider()
    
    # Disk space section
    st.subheader("💾 System Disk Space")
    disk_info = get_disk_space()
    
    if "error" in disk_info:
        st.error(f"Error getting disk space: {disk_info['error']}")
    else:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total", f"{disk_info['total']:.1f} GB")
        with col2:
            st.metric("Used", f"{disk_info['used']:.1f} GB")
        with col3:
            st.metric("Free", f"{disk_info['free']:.1f} GB")
        with col4:
            st.metric("Usage %", f"{disk_info['percent']:.1f}%")
        
        # Progress bar
        st.progress(disk_info['percent'] / 100)
    
    st.divider()
    
    # Docker images section
    st.subheader("🖼️ Docker Images")
    
    if st.button("🔄 Refresh Images"):
        st.rerun()
    
    images = get_docker_images()
    
    if not images:
        st.info("No Docker images found.")
    else:
        st.write(f"**Total: {len(images)} image(s)**")
        
        for img in images:
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
            
            with col1:
                st.write(f"**{img['repository']}:{img['tag']}**")
                st.caption(f"ID: {img['id']}")
            
            with col2:
                st.write(f"Size: {img['size']}")
                st.caption(f"Created: {img['created']}")
            
            with col3:
                st.write("")
            
            with col4:
                st.write("")
            
            with col5:
                if st.button("🗑️ Delete", key=f"del_img_{img['id_full']}"):
                    success, msg = delete_docker_image(img['id_full'])
                    if success:
                        st.success(msg)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
            
            st.divider()
    
    st.divider()
    
    # Docker containers section
    st.subheader("📦 Docker Containers")
    
    if st.button("🔄 Refresh Containers"):
        st.rerun()
    
    containers = get_docker_containers()
    
    if not containers:
        st.info("No Docker containers found.")
    else:
        st.write(f"**Total: {len(containers)} container(s)**")
        
        for cont in containers:
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            
            with col1:
                st.write(f"**{cont['name']}**")
                st.caption(f"ID: {cont['id']}")
            
            with col2:
                st.write(f"Image: {cont['image']}")
                st.caption(f"Status: {cont['status']}")
            
            with col3:
                if "Up" in cont['status']:
                    if st.button("⏸️ Stop", key=f"stop_cont_{cont['id_full']}"):
                        success, msg = stop_docker_container(cont['id_full'])
                        if success:
                            st.success(msg)
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(msg)
            
            with col4:
                if st.button("🗑️ Delete", key=f"del_cont_{cont['id_full']}"):
                    success, msg = delete_docker_container(cont['id_full'])
                    if success:
                        st.success(msg)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
            
            st.divider()

elif page == "Settings":
    st.title("⚙️ Settings")
    
    st.markdown("""
    Manage Build Farm settings and perform maintenance operations.
    """)
    
    st.divider()
    
    # Factory Reset Section
    st.subheader("🔄 Factory Reset")
    st.markdown("""
    This will delete all repositories and build history, resetting the database to its initial state.
    **This action cannot be undone.**
    """)
    
    # Initialize session state for factory reset
    if "factory_reset_confirmed" not in st.session_state:
        st.session_state.factory_reset_confirmed = False
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.warning("⚠️ Factory reset will delete all data including repositories and build history.")
    
    with col2:
        if not st.session_state.factory_reset_confirmed:
            if st.button("🗑️ Factory Reset Database", key="factory_reset_btn"):
                st.session_state.factory_reset_confirmed = True
                st.rerun()
        else:
            st.write("**Are you sure? This cannot be undone.**")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("✅ Yes, delete everything", key="confirm_factory_reset"):
                    try:
                        db.factory_reset()
                        st.session_state.factory_reset_confirmed = False
                        st.success("✅ Database has been factory reset!")
                        st.info("The database has been reset to its initial state. All data has been deleted.")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error during factory reset: {str(e)}")
                        st.session_state.factory_reset_confirmed = False
            
            with col_no:
                if st.button("❌ No, cancel", key="cancel_factory_reset"):
                    st.session_state.factory_reset_confirmed = False
                    st.rerun()
    
    st.divider()
    
    # Database Info Section
    st.subheader("📊 Database Information")
    
    try:
        repos = db.get_all_repositories()
        builds = db.get_all_builds()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Repositories", len(repos))
        
        with col2:
            st.metric("Total Builds", len(builds))
        
        with col3:
            running_builds = build_manager.get_running_builds_count()
            st.metric("Running Builds", running_builds)
    
    except Exception as e:
        st.error(f"Could not retrieve database information: {str(e)}")
