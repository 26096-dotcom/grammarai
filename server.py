#!/usr/bin/env python3
import json, os, re, ssl
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib import request as urlreq, error as urlerr

# .env 파일 로드 (로컬 실행용)
if os.path.exists('.env'):
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

CLAUDE_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
SUPABASE_URL   = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY   = os.environ.get('SUPABASE_KEY', '')
PORT           = int(os.environ.get('PORT', 8000))
HOST           = os.environ.get('HOST', '0.0.0.0')

# SSL 컨텍스트 (certifi 있으면 사용, 없으면 시스템 기본값)
try:
    import certifi
    _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _ssl_ctx = ssl.create_default_context()

PROMPT_TEMPLATE = """다음 영어 지문을 분석하여 아래 JSON 형식으로만 응답해 주세요. JSON 외 다른 텍스트는 출력하지 마세요.

지문:
\"\"\"
{passage}
\"\"\"

JSON 형식:
{{
  "sentences": [
    {{
      "original": "원문 문장",
      "tagged": "성분별 span 태깅 HTML (class 속성에 s/v/o/c/m 사용, 예: <span class=\\"s\\">The cat</span> <span class=\\"v\\">sat</span>)",
      "form": "문장 형식 (예: 3형식)",
      "structure": "구조 요약 (예: S + V + O)",
      "grammar_note": "이 문장의 핵심 문법 포인트 2~3문장 설명"
    }}
  ],
  "grammar_points": [
    {{
      "type": "문법 유형 (관계사/분사/분사구문/시제/수동태/접속사/가정법/비교급/도치 중 하나)",
      "concept": "개념 설명 2~4문장",
      "example": "지문에서 발췌한 예문",
      "exam_tip": "수능 출제 팁 1~2문장"
    }}
  ],
  "questions": [
    {{
      "type": "밑줄 어법 | 어법 빈칸 | 어법 유형 분류",
      "question": "문제 지시문",
      "passage_text": "문제에 활용할 지문 텍스트 (밑줄 부분은 [U]단어[/U] 형식으로 표시)",
      "choices": ["① ...", "② ...", "③ ...", "④ ...", "⑤ ..."],
      "answer": 1,
      "explanation": "해설 (문법 규칙 근거로 정오답 설명)"
    }}
  ],
  "vocab": [
    {{
      "word": "단어",
      "pos": "품사 (n./v./adj./adv./prep. 등)",
      "meaning": "한국어 뜻",
      "example": "짧은 영어 예문"
    }}
  ]
}}

규칙:
- sentences: 지문 내 모든 문장 최대 6개, tagged에 반드시 HTML span 태그 사용
- grammar_points: 지문에서 추출한 4~5개 수능 빈출 문법 포인트
- questions: 어법 문제 정확히 3개 (answer는 1~5 정수)
- vocab: 수능 빈출 어휘 정확히 12개
- 반드시 유효한 JSON만 응답할 것"""


def build_prompt(passage):
    return PROMPT_TEMPLATE.format(passage=passage)


def _sb_headers():
    return {
        'Content-Type': 'application/json',
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
    }

def sb_insert(passage, data):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    preview = passage[:80].replace('\n', ' ')
    payload = json.dumps({'preview': preview, 'passage': passage, 'result': data}).encode('utf-8')
    req = urlreq.Request(
        f'{SUPABASE_URL}/rest/v1/analyses', data=payload,
        headers={**_sb_headers(), 'Prefer': 'return=representation'},
    )
    with urlreq.urlopen(req, timeout=10, context=_ssl_ctx) as r:
        rows = json.loads(r.read())
        return rows[0] if rows else None

def sb_list():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = f'{SUPABASE_URL}/rest/v1/analyses?select=id,preview,created_at&order=created_at.desc&limit=20'
    req = urlreq.Request(url, headers=_sb_headers())
    with urlreq.urlopen(req, timeout=10, context=_ssl_ctx) as r:
        return json.loads(r.read())

def sb_get(row_id):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    url = f'{SUPABASE_URL}/rest/v1/analyses?id=eq.{row_id}&select=*'
    req = urlreq.Request(url, headers=_sb_headers())
    with urlreq.urlopen(req, timeout=10, context=_ssl_ctx) as r:
        rows = json.loads(r.read())
        return rows[0] if rows else None

def sb_delete(row_id):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    url = f'{SUPABASE_URL}/rest/v1/analyses?id=eq.{row_id}'
    req = urlreq.Request(url, headers=_sb_headers(), method='DELETE')
    with urlreq.urlopen(req, timeout=10, context=_ssl_ctx):
        pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            try:
                with open('GrammarAI.html', 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self._cors()
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, 'GrammarAI.html을 같은 폴더에 놓아주세요.')

        elif self.path == '/api/history':
            try:
                rows = sb_list()
                self._json_ok({'rows': rows, 'db_connected': True})
            except Exception as e:
                self._json_ok({'rows': [], 'db_connected': False, 'error': str(e)})

        elif self.path.startswith('/api/history/'):
            row_id = self.path.split('/')[-1]
            try:
                row = sb_get(row_id)
                if row:
                    self._json_ok(row)
                else:
                    self._json_error(404, '데이터를 찾을 수 없습니다.')
            except Exception as e:
                self._json_error(500, str(e))
        else:
            self.send_error(404)

    def do_DELETE(self):
        if self.path.startswith('/api/history/'):
            row_id = self.path.split('/')[-1]
            try:
                sb_delete(row_id)
                self._json_ok({'ok': True})
            except Exception as e:
                self._json_error(500, str(e))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != '/api/analyze':
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            api_key = body.get('api_key', '').strip() or CLAUDE_API_KEY
            passage = body.get('passage', '').strip()

            if not api_key:
                self._json_error(400, 'API 키를 입력해 주세요.')
                return
            if not passage:
                self._json_error(400, '지문을 입력해 주세요.')
                return

            payload = json.dumps({
                'model': 'claude-sonnet-4-6',
                'max_tokens': 4096,
                'messages': [{'role': 'user', 'content': build_prompt(passage)}]
            }).encode('utf-8')

            req = urlreq.Request(
                'https://api.anthropic.com/v1/messages',
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                }
            )
            with urlreq.urlopen(req, timeout=90, context=_ssl_ctx) as resp:
                result = json.loads(resp.read())

            text = result['content'][0]['text'].strip()
            m = re.search(r'\{[\s\S]*\}', text)
            data = json.loads(m.group(0) if m else text)

            saved = None
            if SUPABASE_URL and SUPABASE_KEY:
                try:
                    saved = sb_insert(passage, data)
                except Exception:
                    pass

            self._json_ok({'data': data, 'saved': saved})

        except urlerr.HTTPError as e:
            err = e.read().decode('utf-8', errors='replace')
            try:
                msg = json.loads(err).get('error', {}).get('message', err)
            except Exception:
                msg = err
            self._json_error(e.code, f'Claude API 오류: {msg}')
        except json.JSONDecodeError as e:
            self._json_error(502, f'JSON 파싱 오류: {e}')
        except Exception as e:
            self._json_error(500, str(e))

    def _json_ok(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code, msg):
        body = json.dumps({'error': msg}, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._cors()
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    print(f'GrammarAI 서버 시작 → http://{HOST}:{PORT}')
    server = HTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('서버 종료')
