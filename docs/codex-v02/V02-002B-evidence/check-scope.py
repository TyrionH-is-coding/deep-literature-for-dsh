import json
from pathlib import Path
import subprocess
base='d26cb9e88d0f7884db8e69a5a2d18286a62aaf83'
def old(path):
    return subprocess.check_output(['git','show',base+':'+path]).decode('utf-8').replace('\r\n','\n')
original=json.loads(old('package.json'))
current=json.loads(Path('package.json').read_text(encoding='utf-8'))
expected=json.loads(json.dumps(original))
expected['scripts']['test:offline']=expected['scripts']['test:offline'].replace('node tests/library-navigation-api.mjs && ', 'node tests/library-navigation-api.mjs && node tests/navigation-contract.mjs && ')
assert current==expected, 'Package changes exceed the single added default test'
before=old('tests/navigation-contract.mjs')
after=Path('tests/navigation-contract.mjs').read_text(encoding='utf-8')
expected_test=before.replace("year: 2024, folder: null", "year: 2024, journal: '', folder: null").replace("year: null, folder: null", "year: null, journal: '', folder: null").replace("last_error: '' },", "last_error: '', search_matches: [] },")
assert after==expected_test, 'Navigation test changes exceed the two exact expectations'
changed=subprocess.check_output(['git','diff','--name-only',base], text=True).splitlines()
untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
assert all(p in ['package.json','tests/navigation-contract.mjs'] or p.startswith('docs/codex-v02/V02-002B') for p in changed+untracked)
result={'baseCommit':base,'packageOnlyAddsNavigationToOffline':True,'testOnlyAddsJournalAndSearchMatchesToTwoExpectations':True,'allOtherAssertionsPreserved':True,'productionAndLockFilesUnchanged':True,'offlineCommandCount':len(current['scripts']['test:offline'].split(' && ')),'assetsCommandCount':len(current['scripts']['test:assets'].split(' && ')),'changedTrackedPaths':changed,'newPaths':untracked}
Path('docs/codex-v02/V02-002B-evidence/scope-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
