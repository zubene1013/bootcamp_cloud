import os, json, sys
from urllib import request, error
from datetime import datetime, timezone, timedelta

NOTION_API_KEY = os.environ['NOTION_API_KEY']
ANTHROPIC_API_KEY = os.environ['ANTHROPIC_API_KEY']
ROOT_PAGE_ID = os.environ['NOTION_ROOT_PAGE_ID']
KST = timezone(timedelta(hours=9))
today = datetime.now(KST).date()
SNAPSHOT_FILE = "scripts/.notion_snapshot.json"

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

# 현재 노션 전체 내용 가져오기
children = notion_get("blocks/" + ROOT_PAGE_ID + "/children?page_size=100")
current_snapshot = {}

for block in children.get('results', []):
    if block.get('type') != 'child_page':
        continue
    title = block['child_page']['title']
    lines = get_blocks_recursive(block['id'])
    current_snapshot[title] = lines
    print("페이지 읽음: " + title, file=sys.stderr)

# 이전 snapshot 불러오기
previous_snapshot = {}
if os.path.exists(SNAPSHOT_FILE):
    with open(SNAPSHOT_FILE, 'r') as f:
        previous_snapshot = json.load(f)
    print("이전 snapshot 불러옴", file=sys.stderr)
else:
    print("이전 snapshot 없음 - 첫 실행", file=sys.stderr)

# 변경된 내용 추출
diff_content = []
for title, current_lines in current_snapshot.items():
    previous_lines = previous_snapshot.get(title, [])
    current_set = set(current_lines)
    previous_set = set(previous_lines)
    new_lines = [line for line in current_lines if line not in previous_set]

    if new_lines:
        print("변경 감지: " + title + " (" + str(len(new_lines)) + "줄 추가)", file=sys.stderr)
        diff_content.append("### 페이지: " + title + "\n" + '\n'.join(new_lines))

if not diff_content:
    print("새로 추가된 내용이 없습니다.", file=sys.stderr)
    # snapshot은 업데이트
    with open(SNAPSHOT_FILE, 'w') as f:
        json.dump(current_snapshot, f, ensure_ascii=False, indent=2)
    sys.exit(0)

notion_text = '\n\n'.join(diff_content)
print("=== 새로 추가된 내용 ===", file=sys.stderr)
print(notion_text, file=sys.stderr)

date_str = datetime.now(KST).strftime('%Y-%m-%d')

prompt_lines = [
    "You are a TIL (Today I Learned) writer.",
    "Based on the NEW content added to Notion today, generate a TIL markdown in EXACTLY this format.",
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
    "New content added today:",
    notion_text,
    "",
    "Rules:",
    "- Commands / Configuration 섹션은 코드나 설정이 있을 때만 포함",
    "- References는 실제 존재하는 공식 문서 링크만",
    "- 노션에 작성된 언어를 그대로 따를 것",
    "- 오늘 새로 추가된 내용만 기반으로 작성할 것"
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

# TIL 파일 저장
year = datetime.now(KST).strftime('%Y')
os.makedirs("TIL/" + year, exist_ok=True)
filepath = "TIL/" + year + "/" + date_str + ".md"
with open(filepath, 'w') as f:
    f.write(til_content)
print("TIL 생성 완료: " + filepath)

# snapshot 업데이트
with open(SNAPSHOT_FILE, 'w') as f:
    json.dump(current_snapshot, f, ensure_ascii=False, indent=2)
print("snapshot 업데이트 완료")
