from flask import Flask, request, render_template_string, send_file
import os
import io
import glob

app = Flask(__name__)

# READ REQUIREMENTS.TXT FUNCTION (unchanged)
def read_requirements():
    if os.path.exists("requirements.txt"):
        with open("requirements.txt", "r") as f:
            return f.read().strip()
    return "No requirements.txt found."

# NEW FUNCTION: Scan current directory for all .py files
def get_all_python_files():
    # Use glob to list all python files in the current directory (non-recursive)
    py_files = glob.glob("*.py")
    # Return as a comma-separated string
    return ", ".join(py_files)

# Generate YAML content based on inputs (unchanged logic except for RELEASE_TOKEN addition)
def generate_yaml(python_version, build_os, include_release, script_files, release_token):
    # Mapping from our keys to GitHub Actions runner OS
    os_mapping = {
        "windows": "windows-latest",
        "macos": "macos-latest",
        "linux": "ubuntu-latest"
    }
    matrix_os = [os_mapping[os_key] for os_key in build_os]
    matrix_os_str = ", ".join([f"\"{item}\"" for item in matrix_os])
    
    # Convert script_files string (one per line or comma separated) into a list and trim whitespace
    scripts = [s.strip() for s in script_files.replace(",", "\n").split("\n") if s.strip()]
    # For display in bash loop we need a space-separated list
    scripts_str = " ".join(scripts)
    
    # Create OS-specific build steps for each OS
    build_steps = ""
    for os_key in build_os:
        if os_key == "windows":
            # Changed: Use single quotes inside f-string to avoid backslashes
            build_steps += f"""
      - name: 🏠 Build CSV Tools (Windows)
        if: runner.os == '{os_mapping[os_key]}'
        shell: pwsh
        run: |
          $ErrorActionPreference = "Stop"
          $scripts = @({", ".join([f'"{s}"' for s in scripts])})
          New-Item -ItemType Directory -Force -Path dist/windows | Out-Null
          foreach ($script in $scripts) {{
              $name = [System.IO.Path]::GetFileNameWithoutExtension($script)
              pyinstaller --onefile --noconsole --hidden-import=google --hidden-import=google.auth --hidden-import=google.auth.transport --hidden-import=google.auth.oauthlib --hidden-import=google.auth.httplib2 --hidden-import=googleapiclient --name $name --distpath dist/windows $script
              if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
          }}
          echo "Windows Build Output:"
          Get-ChildItem dist/windows -Recurse
"""
        elif os_key in ["macos", "linux"]:
            folder = os_key if os_key == "macos" else "linux"
            runner_os = os_mapping[os_key]
            build_steps += f"""
      - name: 🍏 Build CSV Tools ({os_key.capitalize()})
        if: runner.os == '{runner_os}'
        shell: bash
        env:
          LC_ALL: en_US.UTF-8
          LANG: en_US.UTF-8
          PYTHONIOENCODING: UTF-8
          PYTHONUTF8: 1
        run: |
          set -e
          # Force UTF-8 locale (critical for macOS)
          export LC_ALL=en_US.UTF-8
          export LANG=en_US.UTF-8
          # Verify locale settings
          locale
          # Create build directory
          mkdir -p dist/{folder}
          # Process each script with encoding safeguards
          for script in {scripts_str}; do
            name=$(basename "$script" .py)
            echo "Building $name with enforced UTF-8 encoding..."
            # Explicitly set encoding for all file operations
            PYTHONIOENCODING=UTF-8 python3 -c "import sys; print('Python Encoding:', sys.getdefaultencoding(), sys.stdout.encoding)"
            PYTHONIOENCODING=UTF-8 pyinstaller --onefile \
              --hidden-import=google \
              --hidden-import=google.auth \
              --hidden-import=google.auth.transport \
              --hidden-import=google.auth.oauthlib \
              --hidden-import=google.auth.httplib2 \
              --hidden-import=googleapiclient \
              --name "$name" \
              --distpath dist/{folder} \
              "$script"
          done
          echo "{os_key.capitalize()} Build Output:"
          ls -la dist/{folder}/
"""
    # Generate upload steps – one per OS
    upload_steps = ""
    for os_key in build_os:
        folder = "windows" if os_key == "windows" else ("macos" if os_key == "macos" else "linux")
        runner_os = os_mapping[os_key]
        upload_steps += f"""
      - name: 📚 Upload Build Artifacts ({os_key.capitalize()})
        uses: actions/upload-artifact@v4
        with:
          name: csv-tools-{runner_os}
          path: dist/{folder}/*
          retention-days: 5
"""
    
    # Create release job steps if requested
    release_job = ""
    if include_release:
        download_steps = ""
        for os_key in build_os:
            runner_os = os_mapping[os_key]
            folder = "windows" if os_key == "windows" else ("macos" if os_key == "macos" else "linux")
            download_steps += f"""
      - name: ⬇️ Download {os_key.capitalize()} Artifacts
        uses: actions/download-artifact@v4
        with:
          name: csv-tools-{runner_os}
          path: releases/{folder}
"""
        release_job = f"""
  release:
    needs: build
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/v') || github.ref == 'refs/tags/release' || github.event_name == 'workflow_dispatch'
    steps:
      - name: 📣 Checkout Repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
{download_steps}
      - name: 📋 Debug Downloaded Files
        run: |
          echo "Downloaded Artifacts:"
          ls -la releases/
      - name: 📦 Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
"""
        for os_key in build_os:
            folder = "windows" if os_key == "windows" else ("macos" if os_key == "macos" else "linux")
            release_job += f"            releases/{folder}/*\n"
        release_job += f"""          tag_name: ${{{{ github.ref_name }}}}
          name: CSV Tools ${{{{ github.ref_name }}}}
          body: |
            ## CSV Tools Release ${{{{ github.ref_name }}}}
            This release includes binaries for:
"""
        for os_key in build_os:
            release_job += f"            - {os_key.capitalize()} (64-bit)\n"
        release_job += """            ### Downloads
            See attached files below.
            ### Changes
            Automatically generated release notes follow below.
          draft: false
          prerelease: ${{{{ contains(github.ref_name, 'beta') || contains(github.ref_name, 'rc') }}}}
          generate_release_notes: true
        env:
          GITHUB_TOKEN: ${{ secrets.RELEASE_TOKEN }}
"""
    # Assemble the full YAML file including RELEASE_TOKEN in the environment if provided
    full_yaml = f"""name: Build CSV Tools ({', '.join([os_key.capitalize() for os_key in build_os])})

permissions:
  contents: write
  actions: read

on:
  push:
    tags:
      - 'v*'
      - 'release'
  workflow_dispatch:

jobs:
  build:
    strategy:
      matrix:
        os: [{matrix_os_str}]
    runs-on: ${{{{ matrix.os }}}}
    steps:
      - name: 📣 Checkout Repository
        uses: actions/checkout@v4

      - name: 🐍 Set Up Python
        uses: actions/setup-python@v5
        with:
          python-version: "{python_version}"
          cache: 'pip'

      - name: 📦 Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pyinstaller pillow
          pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
{build_steps}
{upload_steps}
{release_job}
"""
    # If RELEASE_TOKEN is provided, append its value as a comment at the top for clarity
    if release_token:
        full_yaml = f"# RELEASE_TOKEN: {release_token}\n" + full_yaml
    return full_yaml

# Enhanced HTML template with minimalist styling, title, description, and RELEASE_TOKEN input
html_template = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>GitHub Actions main.yml Generator</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
    .container { max-width: 800px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    h1 { color: #333; }
    label { font-weight: bold; display: block; margin-top: 10px; }
    input[type="text"], textarea { width: 100%; padding: 8px; margin-top: 5px; border: 1px solid #ccc; border-radius: 4px; }
    input[type="checkbox"] { margin-right: 5px; }
    input[type="submit"] { background: #007BFF; color: #fff; border: none; padding: 10px 20px; border-radius: 4px; margin-top: 20px; cursor: pointer; }
    input[type="submit"]:hover { background: #0056b3; }
    pre { background: #eee; padding: 10px; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>GitHub Actions main.yml Generator</h1>
    <p>This tool generates a GitHub Actions workflow file (main.yml) for building CSV Tools. It scans your project for Python files, reads your requirements.txt, and lets you customize build options and release settings. Enter your configuration below and click "Generate main.yml" to download the file.</p>
    <p><strong>Detected Dependencies from requirements.txt:</strong></p>
    <pre>{{ requirements }}</pre>
    <form method="POST">
      <label for="python_version">Python Version:</label>
      <input type="text" name="python_version" value="3.11" required>
      
      <label>Choose Build OS (check all that apply):</label>
      <input type="checkbox" name="build_os" value="windows" checked> Windows<br>
      <input type="checkbox" name="build_os" value="macos" checked> macOS<br>
      <input type="checkbox" name="build_os" value="linux"> Linux<br>
      
      <label for="script_files">Script Files (separated by newlines or commas):</label>
      <textarea name="script_files" rows="4" cols="50">{{ default_scripts }}</textarea>
      
      <label for="include_release">Include Release Job?</label>
      <input type="checkbox" name="include_release" value="yes" checked>
      
      <label for="release_token">RELEASE_TOKEN (optional):</label>
      <input type="text" name="release_token" value="">
      
      <input type="submit" value="Generate main.yml">
    </form>
  </div>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    reqs = read_requirements()
    # NEW: Preload default script files by scanning the current directory for .py files
    default_scripts = get_all_python_files()
    if request.method == "POST":
        python_version = request.form.get("python_version", "3.11")
        build_os = request.form.getlist("build_os")
        include_release = request.form.get("include_release") == "yes"
        script_files = request.form.get("script_files", "")
        release_token = request.form.get("release_token", "")
        yml_content = generate_yaml(python_version, build_os, include_release, script_files, release_token)
        return send_file(io.BytesIO(yml_content.encode('utf-8')),
                         mimetype="text/yaml",
                         as_attachment=True,
                         download_name="main.yml")
    return render_template_string(html_template, requirements=reqs, default_scripts=default_scripts)

if __name__ == "__main__":
    app.run(debug=True)
