# 📊 CSV Tools by xRaisen

![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/xraisen/csv-tools/main.yml)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/xraisen/csv-tools)
![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS-lightgrey)
![License](https://img.shields.io/badge/license-MIT-blue)

Professional CSV processing utilities with a beautiful GUI - Processor and Splitter tools for Windows and macOS.

![CSV Tools Screenshot](screenshots/main_window.jpg)

---

## ✨ Features

### 🔧 CSV Processor

- **Consolidate duplicate rows** while preserving all unique emails/phones
- **Flexible output options**:
  - Combine emails/phones into comma-separated strings
  - Split into multiple rows
- **Smart column detection** for emails and phone numbers
- **Custom column selection** for output files

### ✂️ CSV Splitter

- **Split by row count** (e.g., 50,000 rows per file)
- **Split by file size** (e.g., 50MB max per file)
- **Progress tracking** with a visual indicator
- **Automatic output organization** in timestamped folders

---

## 📥 Installation

### Direct Download (Latest Release)

[![Windows Download](https://img.shields.io/badge/Download-Windows-blue?logo=windows)](https://github.com/xraisen/csv-tools/releases/latest/download/csvprocessor_windows.exe)
[![macOS Download](https://img.shields.io/badge/Download-macOS-silver?logo=apple)](https://github.com/xraisen/csv-tools/releases/latest/download/csvprocessor_macos)

### Using Package Managers

#### Windows (Chocolatey):
```powershell
choco install csv-tools
```

#### macOS (Homebrew):
```bash
brew tap xraisen/tools
brew install csv-tools
```

---

## 🚀 Usage

### CSV Processor

1. Click **"Browse"** to select your input CSV
2. Choose columns to include in output
3. Select processing options:
   - Streamline type (Email, Phone, Both)
   - Split mode (Comma-separated or Rows)
4. Click **"Process CSV"**

### CSV Splitter

1. Select your large CSV file
2. Choose a split method:
   - By rows (e.g., 50,000 rows per file)
   - By size (e.g., 50MB max per file)
3. Click **"Split CSV"**

---

## 🛠️ Development

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
git clone https://github.com/xraisen/csv-tools.git
cd csv-tools
pip install -r requirements.txt
```

### Building Executables

```bash
# Build both tools
python -m PyInstaller --onefile csvprocessor.py
python -m PyInstaller --onefile csvsplitter.py
```

### File Structure

```
csv-tools/
├── .github/            # GitHub Actions workflows
│   └── workflows/
│       └── main.yml    # CI/CD pipeline
├── icons/              # Application icons
│   ├── app.ico         # Windows icon
│   └── app.icns        # macOS icon
├── screenshots/        # Application screenshots
├── src/                # Core application code
│   ├── csvprocessor.py # Processor GUI and logic
│   └── csvsplitter.py  # Splitter GUI and logic
├── tests/              # Unit tests
├── version_info.txt    # Windows version metadata
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

---

## 🤝 Contributing

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

---

## 📧 Contact

xRaisen - [@xRaisen](https://twitter.com/xRaisen) - jpm.onestop@gmail.com

Project Link: [https://github.com/xraisen/csv-tools](https://github.com/xraisen/csv-tools)

