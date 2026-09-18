"""Create only synthetic metadata and queued parents; no provider or model."""
import json
import pathlib
import sys
from scientific_reading.library_service import LibraryService
from scientific_reading.models import PaperMetadata
from scientific_reading.reading_pipeline import ReadingPipeline
from scientific_reading.scope import use_scope

root = pathlib.Path(sys.argv[1]).resolve()
assert not root.exists(), 'fixture must be fresh'
library = LibraryService(root)
folder = library.create_folder('V02-004I synthetic')['folder_id']
other = library.create_folder('V02-004I other')['folder_id']
paper = library.ingest(PaperMetadata(title='V02-004I synthetic paper'))['paper_id']
second = library.ingest(PaperMetadata(title='V02-004I second paper'))['paper_id']
library.move_items([paper, second], folder)
scope = dict(instanceId='v02-004i', scopeSessionId='synthetic-session', scopeFolderId=folder)
with use_scope(scope):
    pipeline = ReadingPipeline(root)
    job = pipeline.start(paper, 'none').parent_job_id
library.close()
print(json.dumps(dict(root=str(root), job=job, paper=paper, second=second, folder=folder, other=other, scope=scope)))
