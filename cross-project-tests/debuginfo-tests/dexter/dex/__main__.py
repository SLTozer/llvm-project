import sys
from dex.tools import main

def run_main():
    return_code = main()
    sys.exit(return_code.value)

if __name__ == "__main__":
    run_main()