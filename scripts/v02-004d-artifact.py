"""Record exact candidate provenance and compare packaged Python source bytes."""
import hashlib, io, json, subprocess, tarfile, zipfile
from email.parser import BytesParser
from pathlib import Path
root=Path(__file__).resolve().parents[1]
archive=root/'dsh-external-dsh-scientific-reading-0.2.0-dev.3.tgz'
sha=lambda b:hashlib.sha256(b).hexdigest()
source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
with tarfile.open(archive) as tgz:
    assert tgz.extractfile('package/lib/client.js').read()==(root/'lib/client.js').read_bytes()
    pkg=json.load(tgz.extractfile('package/package.json'))
    assert pkg['version']=='0.2.0-dev.3'
    members=[m for m in tgz.getmembers() if m.name.endswith('.whl')]
    assert len(members)==1
    wheel=tgz.extractfile(members[0]).read()
    local=root/'dist/python'/Path(members[0].name).name
    assert wheel==local.read_bytes()
    with zipfile.ZipFile(io.BytesIO(wheel)) as z:
        expected={}
        for folder,prefix in [(root/'engine/src/scientific_reading','scientific_reading'),(root/'engine/reader','reader')]:
            for p in folder.rglob('*.py'): expected[prefix+'/'+p.relative_to(folder).as_posix()]=p.read_bytes()
        actual={n:z.read(n) for n in z.namelist() if n.endswith('.py')}
        assert set(actual)==set(expected)
        for n,b in expected.items(): assert actual[n]==b,n
        metadata=[n for n in z.namelist() if n.endswith('.dist-info/METADATA')]
        assert len(metadata)==1 and BytesParser().parsebytes(z.read(metadata[0]))['Version']=='0.2.0.dev2'
    record={'sourceCommit':source,'archive':str(archive),'sha256':sha(archive.read_bytes()),'wheel':str(local),'wheelSha256':sha(wheel),'npmVersion':pkg['version'],'pythonVersion':'0.2.0.dev2','pythonFilesByteMatched':len(expected),'moduleHashes':{n:sha(v) for n,v in actual.items()},'clientSha256':sha((root/'lib/client.js').read_bytes())}
(root/'docs/codex-v02/V02-004D-evidence/artifact.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record,indent=2))
