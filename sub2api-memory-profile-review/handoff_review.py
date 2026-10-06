"""Offline source-ledger crosscheck only; historical native summaries are not fresh tests."""
import json,os,pathlib,shutil,subprocess,sys,tempfile
root=pathlib.Path(__file__).resolve().parent.parent;own=root/'sub2api-memory-profile-review';new=root/'.spike-inputs/candidate/sub2api-memory-profile';full=root/'.spike-inputs/original-inputs/original-inputs'
with tempfile.TemporaryDirectory(dir=own) as td:
 base=pathlib.Path(td);pkg=base/'sub2api-memory-profile';pkg.mkdir();(pkg/'evidence').mkdir()
 for p in new.iterdir():
  if p.is_file():shutil.copyfile(p,pkg/p.name)
 (base/'.spike-inputs').mkdir();(base/'.spike-inputs/original-inputs').symlink_to(full,target_is_directory=True)
 for name in ('sub2api-stream-memory-fork','sub2api-stream-memory-review'):(base/name).symlink_to(root/name,target_is_directory=True)
 cp=subprocess.run([sys.executable,str(pkg/'verify_handoff.py')],capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),timeout=30)
 (own/'reviewed-handoff.txt').write_text(cp.stdout+cp.stderr)
 for p in (pkg/'evidence').iterdir():shutil.copyfile(p,own/p.name)
 print('reviewed handoff returncode',cp.returncode)
 raise SystemExit(cp.returncode)
