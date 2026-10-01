import os
import sys
if '--self-test' in sys.argv:
    from pathlib import Path
    report = Path(sys.argv[sys.argv.index('--self-test') + 1])
    diagnostic = report.with_suffix('.log')
    sys.stdout = sys.stderr = diagnostic.open('w', encoding='utf8', buffering=1)
    print('Frozen Python runtime initialized.', flush=True)
    def report_error(kind, value, trace):
        import json
        import traceback
        traceback.print_exception(kind, value, trace)
        report.write_text(json.dumps(dict(success=False,error=str(value)),indent=2),encoding='utf8')
        sys.stderr.flush()
        os._exit(1)
    sys.excepthook = report_error
