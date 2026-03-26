import os, json, sys
from urllib import request, error
from datetime import datetime, timezone, timedelta

NOTION_API_KEY = os.environ['NOTION_API_KEY']
ANTHROPIC_API_KEY = os.environ['ANTHROPIC_API_KEY']
ROOT_PAGE_ID = os.environ['NOTION_ROOT_PAGE_ID']
KST = timezone(timedelta(hours=9))
today = datetime.now(KST).date()

def notion_get(path):
    req = request.Request(
        "https://api.notion.com/v1/" + path,
        headers={
            "Authorization": "Bearer " + NOTION_API_KEY,
            "Notion-Version": "2022-06-28"
        }
    )
    with request.urlopen(req) as res:
        return json.loads(res.read())

def get_blocks_recursive(block_id):
    data = notion_get("blocks/" + block_id + "/children?page_size=100")
    lines = []
    for block in data.get('results', []):
        btype = block.get('type', '')
        obj = block.get(btype, {})
        rich = obj.get('rich_text', [])
        text = ''.join(t.get('plain_text', '') for t in rich)

        if btype == 'heading_1':
            lines.append("# " + text)
        elif btype == 'heading_2':
            lines.append("## " + text)
        elif btype == 'heading_3':
            lines.append("### " + text)
        elif btype in ('bulleted_list_item', 'numbered_list_item'):
            lines.append("- " + text)
        elif btype == 'toggle':
            lines.append("### " + text)
        elif btype == 'code':
            lang = obj.get('language', '')
            lines.append("```" + lang + "\n" + text + "\n```")
        elif btype == 'paragraph' and text:
            lines.append(text)
        elif btype == 'callout' and text:
            lines.append("> " + text)

        if block.get('has_children'):
            lines.extend(get_blocks_recursive(block['id']))

    return lines

# 루트 페이지 하위 페이지 수집
children = notion_get("blocks/" + ROOT_PAGE_ID + "/children?page_size=100")
all_content = []

for block in children.get('results', []):
    if block.get('type') != 'child_page':
        continue
    last_edited = block.get('last_edited_time', '')
    dt = datetime.fromisoformat(last_edited.replace('Z', '+00:00')).astimezone(KST)
    title = block['child_page']['title']
    print("페이지: " + title + " | 수정일: " + str(dt.date()), file=sys.stderr)

    if dt.date() != today:
        continue

    lines = get_blocks_recursive(block['id'])
    if lines:
        all_content.append("### 페이지: " + title + "\n" + '\n'.join(lines))

if not all_content:
    print("오늘 수정된 노션 페이지 내용이 없습니다.", file=sys.stderr)
    sys.exit(0)

notion_text = '\n\n'.join(all_content)
print("=== 수집된 노션 내용 ===", file=sys.stderr)
print(notion_text, file=sys.stderr)

date_str = datetime.now(KST).strftime('%Y-%m-%d')

prompt_lines = [
    "You are a TIL (Today I Learned) writer.",
    "Based on the Notion notes below, generate a TIL markdown in EXACTLY this format.",
    "Output ONLY the markdown, nothing else.",
    "",
    "# " + date_str,
    "",
    "## What I did",
    "",
    "- (오늘 한 일을 bullet point로 요약)",
    "",
    "## Key concepts learned",
    "",
    "- (배운 핵심 개념들을 bullet point로, 각 개념에 한 줄 설명 추가)",
    "",
    "## Commands / Configuration",
    "",
    "### (주제명)",
    "",
    "(코드나 설정이 있으면 여기, 없으면 이 섹션 전체 생략)",
    "",
    "## References",
    "",
    "- (관련 공식 문서나 링크)",
    "",
    "---",
    "",
    "Notion notes:",
    notion_text,
    "",
    "Rules:",
    "- Commands / Configuration 섹션은 코드나 설정이 있을 때만 포함",
    "- References는 실제 존재하는 공식 문서 링크만",
    "- 노션에 작성된 언어를 그대로 따를 것"
]
prompt = '\n'.join(prompt_lines)

payload = {
    "model": "claude-haiku-4-5",
    "max_tokens": 1500,
    "messages": [{"role": "user", "content": prompt}]
}
body = json.dumps(payload).encode('utf-8')

req = request.Request(
    "https://api.anthropic.com/v1/messages",
    data=body,
    method="POST",
    headers={
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
)

try:
    with request.urlopen(req) as res:
        result = json.loads(res.read())
except error.HTTPError as e:
    print("Claude API 오류: " + str(e), file=sys.stderr)
    print(e.read().decode(), file=sys.stderr)
    sys.exit(1)

til_content = result['content'][0]['text']
print("=== 생성된 TIL ===", file=sys.stderr)
print(til_content, file=sys.stderr)

year = datetime.now(KST).strftime('%Y')
os.makedirs("TIL/" + year, exist_ok=True)
filepath = "TIL/" + year + "/" + date_str + ".md"
with open(filepath, 'w') as f:
    f.write(til_content)
print("파일 생성 완료: " + filepath)
