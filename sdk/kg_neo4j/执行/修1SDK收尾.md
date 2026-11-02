Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
(Get-Command python).Source
python -m pytest -q tests/test_lazy_import.py tests/test_kg_schema.py 2>&1 | Select-Object -Last 15
python -m pytest -q tests --continue-on-collection-errors 2>&1 | Select-Object -Last 15


Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
@'
import subprocess, sys, types
sys.path.insert(0, "src")
sys.modules["pptx"] = None
raw = subprocess.check_output(["git", "show", "HEAD:fwd-tap-ingest/src/tap_ingest_sdk/kg_schema.py"])
old = types.ModuleType("old_kg_schema")
sys.modules["old_kg_schema"] = old
exec(compile(raw.decode("utf-8"), "old_kg_schema", "exec"), old.__dict__)
import tap_ingest_sdk.kg_schema as new
for name in ["ENTITY_TYPES", "RELATION_TYPES", "ENTITY_TYPE_NAMES", "ENTITY_TYPE_ZH", "RELATION_ZH",
             "TRAVERSABLE_RELATIONS", "SCHEMA_ALLOWED_RELATIONS", "SCHEMA_LLM_RELATION_MAP"]:
    a, b = getattr(old, name, "<missing>"), getattr(new, name, "<missing>")
    print(name, "SAME" if repr(a) == repr(b) else "DIFFERENT")
'@ | python -


git --no-pager diff -- src/tap_ingest_sdk/sinks/_kg_schema.py


Set-Location C:\Users\234393\Desktop\tap-ai-backend
uv pip install --offline python-pptx


Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
python -m pytest -q tests 2>&1 | Select-Object -Last 15
