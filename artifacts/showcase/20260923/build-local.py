"""Use only verified local locked dependencies; build current source and frontend dist."""
import hashlib,json,subprocess
from pathlib import Path
root=Path.cwd();out=root/'artifacts/showcase/20260923'
backend='charge-ops-backend:test-94f8cb9ab56df832';frontend='charge-ops-frontend:test-94f8cb9ab56df832'
for name in ('uv.lock','pyproject.toml'):
 data=subprocess.check_output(['docker','run','--rm','--entrypoint','cat',backend,'/app/'+name]);assert data==(root/name).read_bytes(),name
sources=sorted([p for folder in ('backend','simulator','knowledge','tests/support','deploy','frontend/src') for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]+[root/p for p in ('pyproject.toml','uv.lock','frontend/package.json','frontend/package-lock.json','frontend/vite.config.ts','frontend/tsconfig.json','frontend/index.html')])
digest=hashlib.sha256(b''.join(str(p.relative_to(root)).encode()+p.read_bytes() for p in sources)).hexdigest()[:16]
for role,base,body in [('backend',backend,'COPY backend backend\nCOPY simulator simulator\nCOPY knowledge knowledge\nCOPY tests/support tests/support\nRUN uv sync --offline --locked --no-dev\n'),('frontend',frontend,'COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf\nCOPY frontend/dist/ /usr/share/nginx/html/\n')]:
 path=out/(role+'.Dockerfile');path.write_text('FROM '+base+'\n'+body)
 if role=='frontend': Path(str(path)+'.dockerignore').write_text('**\n!frontend\n!frontend/dist\n!frontend/dist/**\n!deploy\n!deploy/nginx.conf\n')
 subprocess.run(['docker','build','--network=none','-f',str(path),'-t',f'charge-ops-{role}:test-{digest}','-t',f'charge-ops-{role}:showcase-20260923','.'],check=True)
(out/'local-build.json').write_text(json.dumps({'status':'PASS','source_digest':digest,'dependency_image':backend,'frontend_base':frontend,'uv_lock_and_pyproject':'exact byte match','frontend_build':'npm run typecheck && npm run build, existing locked node_modules','network':'none for Docker builds'},indent=2)+'\n')
