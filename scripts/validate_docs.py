"""Check checked-in Markdown targets and showcase assets without network access."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def anchors(text):
    result, seen = set(), {}
    for line in text.splitlines():
        match = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line)
        if not match:
            continue
        title = re.sub(r'[`*_]', '', match[1]).lower()
        slug = re.sub(r'[^\w\-\s]', '', title).replace(' ', '-')
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(slug + (f'-{count}' if count else ''))
    result.update(re.findall(r'\bid=["\x27]([^"\x27]+)', text))
    return result


def check():
    import subprocess
    # Include newly authored, unignored docs before staging, exclude local reports.
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    docs = sorted({ROOT / n for n in names if n.endswith('.md')})
    failures, links = [], 0
    for path in docs:
        original = path.read_text(encoding='utf-8-sig')
        body = re.sub(r'```.*?```', '', original, flags=re.S)
        # Explicit links, images, and embedded HTML assets. Remote links are not fetched.
        targets = re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', body)
        targets += re.findall(r'\b(?:src|href)=["\x27]([^"\x27]+)', body)
        for raw in targets:
            raw = raw.strip('<>')
            parsed = urlsplit(raw)
            links += 1
            if parsed.scheme or parsed.netloc:
                if parsed.hostname in ('127.0.0.1', 'localhost') and re.search(r'[\u3400-\u9fff*]', raw):
                    failures.append(f'{path.relative_to(ROOT)}: malformed local URL {raw}')
                continue
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not target.is_relative_to(ROOT.resolve()) or not target.exists():
                failures.append(f'{path.relative_to(ROOT)}: missing/outside target {raw}')
            elif parsed.fragment and target.suffix == '.md':
                if unquote(parsed.fragment) not in anchors(target.read_text(encoding='utf-8-sig')):
                    failures.append(f'{path.relative_to(ROOT)}: missing anchor {raw}')
        bare = re.sub(r'\]\([^\s)]+(?:\s+"[^"]*")?\)', '', body)
        for raw in re.findall(r'https?://(?:127\.0\.0\.1|localhost)[^\s<>`]+', bare):
            if re.search(r'[\u3400-\u9fff*]', raw):
                failures.append(f'{path.relative_to(ROOT)}: ambiguous bare local URL; use explicit Markdown link')
    assets = ROOT / 'docs/assets/showcase'
    for name in ('research.jpg','product.jpg','cost-detail.jpg','feedback.jpg','review.jpg'):
        data = (assets / name).read_bytes()
        if not data.startswith(b'\xff\xd8') or len(data) < 1000:
            failures.append(f'invalid screenshot: {name}')
    for name in ('cover.svg', 'workflow.svg', 'architecture.svg'):
        root = ET.parse(assets / name).getroot()
        if root.tag != '{http://www.w3.org/2000/svg}svg' or not root.get('viewBox'):
            failures.append(f'invalid diagram: {name}')
        if root.find('{http://www.w3.org/2000/svg}title') is None:
            failures.append(f'missing accessible title: {name}')
    database=ET.parse(ROOT/'docs/assets/database-er.svg').getroot()
    if database.tag!='{http://www.w3.org/2000/svg}svg' or not database.get('viewBox'):
        failures.append('invalid database diagram')
    for name in ('docs/DATABASE_TOUR.html','database/migrations/002_relational_entities.sql','database/interview-queries.sql'):
        if not (ROOT/name).is_file():failures.append(f'missing database artifact: {name}')
    if failures:
        raise SystemExit('\n'.join(failures))
    print(f'Documentation OK: {len(docs)} Markdown files, {links} links, 5 screenshots, 4 SVG diagrams; external URLs not fetched.')


if __name__ == '__main__':
    check()
