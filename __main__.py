# __main__.py
import sys
from csvprocessor import main as csvprocessor_main
from csvsplitter import main as csvsplitter_main
from csvsearch_ai import main as csvsearch_ai_main  # Renamed file: csvsearch+ai.py -> csvsearch_ai.py

if __name__ == "__main__":
    if "csvprocessor" in sys.argv:
        csvprocessor_main()
    elif "csvsplitter" in sys.argv:
        csvsplitter_main()
    elif "csvsearchai" in sys.argv:
        csvsearch_ai_main()
    else:
        print("Usage: python -m csvtools [csvprocessor|csvsplitter|csvsearchai]")
