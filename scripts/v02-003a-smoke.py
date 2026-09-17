"""Synthetic F1 + conflict verification, usable against source or installed wheel."""
import argparse
from contextlib import closing
import gc
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

import openpyxl
import scientific_reading.xlsx_snapshot as module
from scientific_reading.library_service import LibraryService
from scientific_reading.models import PaperMetadata
from scientific_reading.xlsx_snapshot import XlsxSnapshotService, XLSX_COLUMNS

parser = argparse.ArgumentParser()
parser.add_argument('--installed', action='store_true')
args = parser.parse_args()
if args.installed:
    assert Path(sys.prefix).resolve() in Path(module.__file__).resolve().parents
    assert 'site-packages' in Path(module.__file__).parts
with tempfile.TemporaryDirectory(prefix='v02-003a-smoke-') as folder:
    root = Path(folder)
    library = LibraryService(root)
    paper_id = library.ingest(PaperMetadata(title='Synthetic V02-003A', doi='10.5555/v02.003a'))['paper_id']
    library.close()
    def write(values):
        with closing(sqlite3.connect(root / 'library.sqlite')) as conn, conn:
            conn.execute('UPDATE items SET personal_thoughts=?, understanding_level=?, user_notes=?', values)
    def read():
        with closing(sqlite3.connect(root / 'library.sqlite')) as conn:
            assert conn.execute('PRAGMA user_version').fetchone()[0] == 4
            return conn.execute('SELECT personal_thoughts, understanding_level, user_notes FROM items').fetchone()
    old = ('old thought', 'old understanding', 'old note')
    new = ('new thought', 'new understanding', 'new note')
    write(old)
    snapshot = XlsxSnapshotService(root)
    assert snapshot.refresh()['status'] == 'success'
    write(new)
    assert snapshot.refresh()['status'] == 'success'
    assert read() == new
    workbook = openpyxl.load_workbook(snapshot.target)
    workbook['文献'].cell(2, XLSX_COLUMNS.index('用户笔记') + 1, 'Excel change')
    workbook.save(snapshot.target)
    workbook.close()
    write((*new[:2], 'DB change'))
    original = snapshot.target.read_bytes()
    for _ in range(2):
        # Separate CLI processes verify that no in-memory conflict cache is needed.
        run = subprocess.run([sys.executable, '-m', 'scientific_reading', '--data-root', str(root), 'xlsx-refresh'], capture_output=True, text=True, encoding='utf-8', check=True)
        result = json.loads(run.stdout)
        assert result['status'] == 'pending', result
        assert result['updated'] == 0
        assert result['conflict_details'] == [{'paper_id': paper_id, 'field': 'user_notes', 'code': 'user_field_conflict'}]
        assert snapshot.target.read_bytes() == original
        assert read() == (*new[:2], 'DB change')
    print(json.dumps({'f1_preserves_new_sqlite': True, 'conflict_preserves_both_sides': True,
        'fresh_cli_retries': 2, 'schema': 4, 'installed': args.installed,
        'python': sys.executable, 'module': module.__file__}, indent=2))
    gc.collect()
