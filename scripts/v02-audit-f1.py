"""Diagnostic only: reproduce F1 in an automatically removed synthetic library."""
import json
from pathlib import Path
import sqlite3
import tempfile
import gc
from contextlib import closing

from scientific_reading.library_service import LibraryService
from scientific_reading.models import PaperMetadata
from scientific_reading.xlsx_snapshot import XlsxSnapshotService

FIELDS = ('personal_thoughts', 'understanding_level', 'user_notes')
with tempfile.TemporaryDirectory(prefix='v02-audit-f1-') as folder:
    root = Path(folder)
    service = LibraryService(root)
    paper_id = service.ingest(PaperMetadata(title='V02-002 synthetic conflict', authors=['Synthetic Author'], doi='10.5555/v02.002.fixture'))['paper_id']
    service.close()
    def write(values):
        with closing(sqlite3.connect(root / 'library.sqlite')) as db:
            with db:
                db.execute('UPDATE items SET personal_thoughts=?, understanding_level=?, user_notes=? WHERE paper_id=?', (*values, paper_id))
    def read():
        with closing(sqlite3.connect(root / 'library.sqlite')) as db:
            return dict(zip(FIELDS, db.execute('SELECT personal_thoughts, understanding_level, user_notes FROM items WHERE paper_id=?', (paper_id,)).fetchone()))
    old = ('old thought', 'old understanding', 'old note')
    new = ('new thought', 'new understanding', 'new note')
    write(old)
    snapshot = XlsxSnapshotService(root)
    first = snapshot.refresh()
    write(new)
    before = read()
    refreshed = snapshot.refresh()
    after = read()
    # Persist no temporary root paths; the result is independent of user libraries.
    result = {'taskId': 'V02-002', 'fixture': 'synthetic direct SQL conflict, not UI editing',
              'firstRefreshStatus': first['status'], 'refreshStatus': refreshed['status'],
              'before': before, 'after': after, 'overwrittenFields': [f for f in FIELDS if before[f] != after[f]],
              'reproduced': tuple(after.values()) == old}
    assert result['reproduced'] and result['refreshStatus'] == 'success', result
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Existing engine sqlite context managers commit but leave GC to close handles.
    gc.collect()
