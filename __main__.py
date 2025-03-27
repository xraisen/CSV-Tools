# __main__.py
import sys
from csvprocessor import main as csvprocessor_main
from csvsplitter import main as csvsplitter_main

if __name__ == "__main__":
    if "csvprocessor" in sys.argv:
        csvprocessor_main()
    elif "csvsplitter" in sys.argv:
        csvsplitter_main()