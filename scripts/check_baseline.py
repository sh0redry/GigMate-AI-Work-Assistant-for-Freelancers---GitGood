"""Validate documentation/contracts only; never claim to test application behavior."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urldefrag, urlsplit

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
except ImportError:
    raise SystemExit('Missing schema validator. Install scripts/requirements-baseline.txt first.')


def require(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        errors.append(f'{path.relative_to(ROOT)}: {exc}')
        return None


def project_path(base: Path, target: str) -> Path:
    path = (base / unquote(target)).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Reference escapes the repository')
    return path


def slug(text: str) -> str:
    text = re.sub(r'[`*_]', '', text).strip().lower()
    return ''.join(c for c in text if unicodedata.category(c)[0] in 'LN' or c in ' -_').replace(' ', '-')


required_files = [
    'README.md', 'AGENTS.md', 'docs/en/README.md', 'docs/en/overview.md',
    'docs/en/architecture.md', 'docs/en/getting-started.md', 'docs/en/contributing.md',
    'docs/en/adr/README.md', 'docs/en/adr/0001-foundation.md',
    'docs/en/adr/0002-contract-authority.md', 'docs/en/adr/0003-approval-and-execution.md',
    'docs/zh/README.md', 'docs/zh/scope.md', 'docs/zh/engineering-standards.md',
    'docs/zh/domain-workflows.md', 'docs/zh/collaboration-checklist.md',
    'docs/zh/acceptance.md', 'docs/zh/roadmap.md', 'contracts/README.md',
    'contracts/api-v1.md', 'contracts/domain/models.schema.json',
    'contracts/events/message-event.schema.json', 'contracts/ai/change-proposal.schema.json',
    'contracts/examples/manifest.json', 'contracts/examples/scenarios.json',
    '.github/ISSUE_TEMPLATE/task.md', '.github/ISSUE_TEMPLATE/bug.md',
    '.github/pull_request_template.md', '.github/workflows/baseline.yml',
    'scripts/requirements-baseline.txt',
    'docs/en/implementation-status.md', 'docs/zh/progress.md', 'contracts/openapi.json',
    'apps/backend/pyproject.toml', 'apps/backend/requirements.lock', 'apps/backend/alembic.ini',
    'apps/web/package.json', 'apps/web/package-lock.json', 'apps/web/src/generated/api.d.ts',
    'infra/compose.yaml', 'scripts/export_contracts.py', 'scripts/check_web_contracts.mjs',
    'scripts/smoke_replay.py', '.github/workflows/skeleton.yml',
    'docs/zh/onboarding.md', 'docs/zh/onboarding-report-template.md',
    'docs/zh/team-governance.md', 'docs/en/team-governance.md',
    '.github/ISSUE_TEMPLATE/onboarding.md',
    'docs/en/adr/0004-equal-collaboration.md',
]
for item in required_files:
    require((ROOT / item).is_file(), f'Missing baseline file: {item}')

pin = (ROOT / 'scripts/requirements-baseline.txt').read_text(encoding='utf-8').strip().split('==')[-1]
require(importlib.metadata.version('jsonschema') == pin,
        f'jsonschema must match tooling pin {pin}; install scripts/requirements-baseline.txt')

markdown = sorted([ROOT / 'README.md', ROOT / 'AGENTS.md', *ROOT.glob('docs/**/*.md'),
                   *ROOT.glob('contracts/**/*.md'), *ROOT.glob('.github/**/*.md')])
link_count = 0
for path in markdown:
    raw = path.read_text(encoding='utf-8')
    require(raw.count('```') % 2 == 0, f'{path.relative_to(ROOT)}: unclosed code fence')
    text = re.sub(r'```.*?```', '', raw, flags=re.S)
    for target in re.findall(r'!?\[[^\]\n]+\]\(([^)]+)\)', text):
        target = target.strip().strip('<>')
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue  # External URLs require separate review; no network calls here.
        link_count += 1
        try:
            dest = project_path(path.parent, parsed.path) if parsed.path else path
            require(dest.exists(), f'{path.relative_to(ROOT)}: missing link {target}')
            if parsed.fragment and dest.is_file() and dest.suffix == '.md':
                headings = re.findall(r'^#{1,6}\s+(.+)$', dest.read_text(encoding='utf-8'), flags=re.M)
                counts: Counter[str] = Counter()
                anchors = set()
                for heading in headings:
                    base = slug(heading)
                    count = counts[base]
                    anchors.add(base if count == 0 else f'{base}-{count}')
                    counts[base] += 1
                require(unquote(parsed.fragment) in anchors, f'{path.relative_to(ROOT)}: missing anchor {target}')
        except ValueError as exc:
            errors.append(f'{path.relative_to(ROOT)}: {target}: {exc}')

readme = (ROOT / 'README.md').read_text(encoding='utf-8')
require('docs/zh' not in readme.replace('\\', '/').lower(), 'Root README must not reference Chinese documents')
require('not been implemented' in readme, 'Root README must accurately state implementation status')

all_json = sorted(ROOT.glob('contracts/**/*.json'))
data = {path: read_json(path) for path in all_json}
schema_paths = [path for path in all_json if path.name.endswith('.schema.json')]
registry = Registry()
for path in schema_paths:
    value = data[path]
    if value is None:
        continue
    try:
        Draft202012Validator.check_schema(value)
        registry = registry.with_resource(path.as_uri(), Resource.from_contents(value))
    except Exception as exc:
        errors.append(f'{path.relative_to(ROOT)}: invalid schema: {exc}')


def references(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == '$ref':
                yield child
            else:
                yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def schema_uri(base: Path, target: str) -> str:
    file, fragment = urldefrag(target)
    dest = project_path(base, file)
    require(dest in schema_paths, f'Schema reference not registered: {target}')
    return dest.as_uri() + ('#' + fragment if fragment else '')


for path in schema_paths:
    for reference in references(data[path]):
        try:
            if reference.startswith('#'):
                uri = path.as_uri() + reference
            else:
                uri = schema_uri(path.parent, reference)
            registry.resolver().lookup(uri)
        except Exception as exc:
            errors.append(f'{path.relative_to(ROOT)}: unresolved $ref {reference}: {exc}')

manifest = data.get(ROOT / 'contracts/examples/manifest.json') or {}
fixtures = manifest.get('fixtures', [])
require(manifest.get('data_classification') == 'synthetic', 'Manifest must classify fixtures as synthetic')
names = [item['file'] for item in fixtures]
require(len(names) == len(set(names)), 'Duplicate fixture names')
actual_examples = {p.name for p in ROOT.glob('contracts/examples/*.json')} - {'manifest.json', 'scenarios.json'}
require(set(names) == actual_examples, 'Every example must appear exactly once in the manifest')
positive = negative = 0
for item in fixtures:
    try:
        fixture_path = project_path(ROOT / 'contracts/examples', item['file'])
        uri = schema_uri(ROOT / 'contracts/examples', item['schema'])
        validator = Draft202012Validator({'$schema': 'https://json-schema.org/draft/2020-12/schema', '$ref': uri},
                                         registry=registry, format_checker=FormatChecker())
        failures = list(validator.iter_errors(data[fixture_path]))
        if item['valid']:
            positive += 1
            require(not failures, f'{item["file"]}: expected valid, got ' + '; '.join(e.message for e in failures))
        else:
            negative += 1
            require(bool(failures), f'{item["file"]}: invalid fixture unexpectedly accepted')
    except Exception as exc:
        errors.append(f'{item.get("file")}: fixture validation failed: {exc}')

samples = {path.name: value for path, value in data.items() if path.parent.name == 'examples'}
event = samples.get('message-reschedule.json') or {}
order = samples.get('work-order.json') or {}
proposal = samples.get('proposal-reschedule.json') or {}
action = samples.get('action-pending.json') or {}
command = samples.get('approve-command.json') or {}
scenarios_doc = samples.get('scenarios.json') or {}
scenarios = scenarios_doc.get('scenarios', [])
require({case['case_id'] for case in scenarios} == {f'AC-{i:03}' for i in range(1, 13)}, 'Expected all 12 unique acceptance case IDs')
require(len(scenarios) == 12, 'Expected exactly 12 acceptance scenarios')
for case in scenarios:
    require(case.get('classification') == 'synthetic' and case.get('execution_status') == 'not_implemented',
            f'{case["case_id"]}: scenarios must not claim executed results')
    require(bool(case.get('context')) and bool(case.get('steps')) and bool(case.get('must')) and bool(case.get('must_not')),
            f'{case["case_id"]}: incomplete input or expected behavior')
    for name in case.get('fixtures', []):
        require(name in names and next(item['valid'] for item in fixtures if item['file'] == name),
                f'{case["case_id"]}: unknown or invalid business fixture {name}')

try:
    require(event['account_id'] == order['account_id'] == action['account_id'], 'Linked examples have different accounts')
    require(event['conversation_id'] == proposal['conversation_id'] == action['conversation_id'], 'Conversation linkage mismatch')
    require(order['id'] == proposal['work_order_id'] == action['work_order_id'], 'Work order linkage mismatch')
    require(order['version'] == proposal['base_work_order_version'] == action['bound_work_order_version'] == command['expected_version'], 'Work order version mismatch')
    require(proposal['base_context_version'] == action['bound_context_version'] == command['expected_context_version'], 'Context version mismatch')
    require(command['expected_action_revision'] == action['revision'], 'Action revision mismatch')
    require(proposal['changes'][0]['sources'][0]['message_id'] == event['payload']['message_id'], 'Proposal provenance mismatch')
    require(proposal['changes'][0]['old_value'] == order['fields']['schedule']['value'], 'Proposal old value differs from confirmed schedule')
    original = samples['message-original.json']
    require(order['fields']['schedule']['sources'][0]['message_id'] == original['payload']['message_id'], 'Original confirmation source mismatch')
    keys = ['id', 'account_id', 'work_order_id', 'conversation_id', 'kind', 'revision', 'recipient', 'body',
            'bound_work_order_version', 'bound_context_version', 'expires_at', 'sources']
    for name in ['action-pending.json', 'action-unknown.json']:
        current = samples[name]
        projection = {key: current[key] for key in keys}
        digest = 'sha256:' + hashlib.sha256(json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        require(current['snapshot_hash'] == digest, f'{name}: snapshot does not match content')
    require(command['snapshot_hash'] == action['snapshot_hash'], 'Approval command hash mismatch')
    proposed = proposal['changes'][0]['new_value']
    start = datetime.fromisoformat(proposed['start_at'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(proposed['end_at'].replace('Z', '+00:00'))
    hong_kong_fixture_time = start.astimezone(timezone(timedelta(hours=8)))
    require(hong_kong_fixture_time.date() == date(2026, 10, 8) and hong_kong_fixture_time.hour == 15 and end > start,
            'Synthetic reschedule must be Oct 8 at 15:00 in Hong Kong with positive duration')
    require(scenarios[0]['context']['conflict'] == proposed, 'Conflict fixture must overlap the proposed appointment')
except (KeyError, TypeError, ValueError) as exc:
    errors.append(f'Linked fixture invariant failed: {exc}')

if errors:
    for error in errors:
        print('FAIL:', error)
    raise SystemExit(f'Baseline validation failed: {len(errors)} issue(s).')

print(f'PASS: {len(markdown)} Markdown files, {link_count} local links, {len(schema_paths)} schemas, '
      f'{positive} valid fixtures, {negative} rejected fixtures, {len(scenarios)} synthetic acceptance scenarios.')
print(f'Validator: jsonschema {importlib.metadata.version("jsonschema")}; application behavior and live integration not tested.')
