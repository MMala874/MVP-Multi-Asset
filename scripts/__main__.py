from __future__ import annotations

import sys

if __name__ == "__main__":
    if len(sys.argv) > 0:
        script_name = sys.argv[0]
        if "run_tuning_mp" in script_name:
            from scripts.run_tuning_mp import main
        else:
            from scripts.run_tuning import main
        main()
    else:
        from scripts.run_tuning import main
        main()
