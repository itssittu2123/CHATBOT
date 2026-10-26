#!/usr/bin/env python3
"""Sittu AI portable starter server with web-search fallback. Python standard library only."""
import json, os, re, html, urllib.request, urllib.error
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, urlencode, urljoin

# .env file load karne ke liye basic support
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("SITTU_AI_HOST", "127.0.0.1")
PORT = int(os.environ.get("SITTU_AI_PORT", "8765"))
API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
MODEL = os.environ.get("SITTU_AI_MODEL", "gpt-6-luna").strip()
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b").strip()

SYSTEM_PROMPT = """You are Sittu AI, a helpful assistant. Use simple Hindi/Hinglish when the user does.
Help with general knowledge, programming, Python, BCA subjects, maths, writing and learning.
Match the user language: simple Hindi/Hinglish if they ask that way; English if they ask in English. Give a useful, properly explained answer, not a tiny one-liner. For learning questions, use headings, step-by-step explanation, examples, and a short recap when useful. For Python, include correct code and explain the logic. For BCA-level topics, teach at beginner level. Use supplied web search results when relevant, and separate current sourced information from general knowledge. Never claim you searched if no results were provided. Never reveal passwords, keys, or private personal information. If uncertain, say so clearly. Avoid padding and do not invent facts."""

class SearchParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._active = None
        self._capture = None
        self._text = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag == "a" and ("result__a" in cls or "result-link" in cls):
            self._active = {"title": "", "url": attrs.get("href", "")}
            self._capture = "title"
            self._text = []
        elif self._active and tag in ("div", "a") and ("result__snippet" in cls or "result-snippet" in cls):
            self._capture = "snippet"
            self._text = []
    def handle_data(self, data):
        if self._active and self._capture:
            self._text.append(data)
    def handle_endtag(self, tag):
        if not self._active:
            return
        text = " ".join(" ".join(self._text).split())
        if self._capture == "title" and tag == "a":
            self._active["title"] = text
            self._capture = None
            self._text = []
            self.results.append(self._active)
            self._active = None
        elif self._capture == "snippet" and tag == "div":
            if self.results and text:
                self.results[-1]["snippet"] = text
            self._capture = None
            self._text = []

def web_search(query, limit=5):
    """Best-effort public web search. Search engines can rate-limit/block requests."""
    url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8"
    })
    with urllib.request.urlopen(req, timeout=15) as response:
        page = response.read().decode("utf-8", "replace")
        parser = SearchParser()
        parser.feed(page)
        cleaned = []
        seen = set()
        for item in parser.results:
            title = item.get("title", "").strip()
            link = item.get("url", "").strip()
            if link.startswith("//"):
                link = "https:" + link
            if link and not link.startswith("http"):
                link = urljoin("https://duckduckgo.com", link)
            if title and link.startswith("http") and link not in seen:
                seen.add(link)
                cleaned.append({"title": title, "url": link, "snippet": item.get("snippet", "").strip()})
            if len(cleaned) >= limit:
                break
        return cleaned

def search_text(results):
    if not results:
        return ""
    return "\n\n".join(
        f"Result {i+1}: {r['title']}\nURL: {r['url']}\nSnippet: {r.get('snippet','')}"
        for i, r in enumerate(results)
    )

def openai_answer(question, history, results):
    messages = [{"role":"system","content":SYSTEM_PROMPT}]
    if results:
        messages.append({"role":"system","content":"Public web search results for the user's question (may be incomplete or noisy):\n" + search_text(results)})
    if isinstance(history, list):
        for item in history[-12:]:
            if isinstance(item, dict) and item.get("role") in ("user","assistant"):
                content = str(item.get("content",""))[:6000]
                if content:
                    messages.append({"role":item["role"],"content":content})
    messages.append({"role":"user","content":question})
    payload = {"model": MODEL, "input": messages}
    payload["tools"] = [{"type":"web_search"}]
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization":"Bearer " + API_KEY, "Content-Type":"application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        result = json.loads(response.read().decode("utf-8"))
        answer = result.get("output_text")
        if not answer:
            chunks = []
            for output in result.get("output", []):
                for content in output.get("content", []):
                    if content.get("type") == "output_text":
                        chunks.append(content.get("text",""))
            answer = "\n".join(chunks).strip()
        return answer or "I could not create an answer. Please try again."

def ollama_is_available():
    try:
        req = urllib.request.Request(OLLAMA_URL + "/api/tags", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8"))
            names = [m.get("name", "") for m in data.get("models", [])]
            return any(n == OLLAMA_MODEL or n.startswith(OLLAMA_MODEL + ":") for n in names), names
    except Exception:
        return False, []

def ollama_answer(question, history, results):
    system = SYSTEM_PROMPT + "\n\nAnswer style rules: be clear, warm, and naturally conversational. For a simple factual question, answer directly with enough context. For a 'explain' or study question, explain in detail with headings/bullets and examples. In Hindi/Hinglish, use easy everyday language and keep important English terms in brackets. In English, use simple correct English. Do not switch languages unnecessarily. If web results are provided, use them as clues, cite the site names/URLs in a Sources section, and say if results are incomplete. Do not pretend that search snippets prove more than they do."
    msgs = [{"role":"system", "content":system}]
    if results:
        msgs.append({"role":"system", "content":"Live web search results (may be incomplete):\n" + search_text(results)})
    if isinstance(history, list):
        for item in history[-10:]:
            if isinstance(item, dict) and item.get("role") in ("user", "assistant"):
                content = str(item.get("content", ""))[:5000]
                if content:
                    msgs.append({"role":item["role"], "content":content})
    msgs.append({"role":"user", "content":question})
    payload = {"model": OLLAMA_MODEL, "messages": msgs, "stream": False,
               "options": {"temperature": 0.55, "num_predict": 1200}}
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as response:
        data = json.loads(response.read().decode("utf-8"))
        answer = data.get("message", {}).get("content", "").strip()
        if results and answer:
            answer += "\n\nSources to check:\n" + "\n".join(f"• {r['title']} — {r['url']}" for r in results[:5])
        return answer or "Maaf kijiye, is baar answer generate nahi hua. Dobara try karein."

def web_only_answer(question, results):
    if not results:
        return ("Internet search abhi results nahi la saka. Network check karo ya kuch der baad try karo. "
                "Real AI-generated answers ke liye OPENAI_API_KEY configure karna hoga.")
    lines = ["Mere paas abhi real AI API key configured nahi hai, isliye main internet par mile relevant results dikha raha hoon. "
             "Links kholkar information verify kar lena:\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n{r.get('snippet') or 'Snippet available nahi hai.'}\n{r['url']}")
    lines.append("\nNote: Ye search results hain, AI ka verified final summary nahi.")
    return "\n\n".join(lines)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "static"), **kwargs)
    def _json(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if urlparse(self.path).path == "/api/status":
            ollama_ok, models = ollama_is_available()
            self._json(200, {"ok": True, "ai_connected": bool(API_KEY) or ollama_ok,
                             "ollama_connected": ollama_ok, "web_search": True,
                             "model": MODEL if API_KEY else (OLLAMA_MODEL if ollama_ok else None),
                             "ollama_installed_models": models})
            return
        return super().do_GET()
    def do_POST(self):
        if urlparse(self.path).path != "/api/chat":
            self._json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                return self._json(413, {"error": "Message too large"})
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            question = str(body.get("question", "")).strip()
            history = body.get("history", [])
            if not question:
                return self._json(400, {"error": "Please enter a question."})
            results = []
            search_error = None
            try:
                results = web_search(question, limit=5)
            except Exception as e:
                search_error = f"{type(e).__name__}: {e}"
            if API_KEY:
                try:
                    answer = openai_answer(question, history, results)
                    self._json(200, {"answer": answer, "sources": results, "mode": "cloud_ai"})
                    return
                except Exception:
                    pass
            ollama_ok, _ = ollama_is_available()
            if ollama_ok:
                try:
                    answer = ollama_answer(question, history, results)
                    self._json(200, {"answer": answer, "sources": results, "mode": "ollama_ai"})
                    return
                except Exception as e:
                    if results:
                        self._json(200, {"answer": web_only_answer(question, results) +
                            f"\n\nLocal AI error: {type(e).__name__}. Check that Ollama is running and model {OLLAMA_MODEL} is installed.", "sources": results, "mode":"web_fallback"})
                    else:
                        self._json(502, {"error": f"Ollama could not answer. Check Ollama and install model {OLLAMA_MODEL}. Details: {e}"})
                    return
            if results:
                self._json(200, {"answer": web_only_answer(question, results) +
                    f"\n\nFor detailed AI answers, install/run Ollama and download model {OLLAMA_MODEL} (free, but needs disk space).", "sources": results, "mode":"web_only"})
            else:
                self._json(200, {"answer": "Internet search abhi fail hua. " + (search_error or "") +
                    f"\n\nDetailed AI answers ke liye Ollama install karke model {OLLAMA_MODEL} download karein, ya server par API key configure karein.", "sources": [], "mode":"offline"})
        except Exception as e:
            self._json(500, {"error": f"Could not answer: {type(e).__name__}: {e}"})

if __name__ == "__main__":
    print("\nSittu AI portable server")
    print(f"Open http://{HOST}:{PORT} in your browser")
    print("AI connection:", "configured" if API_KEY else "No API key: web-search-only fallback")
    print("Web search: enabled (best-effort; search engine/network may block requests)")
    print("Stop server with Ctrl+C.\n") 
    import webbrowser
    webbrowser.open(f"http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
   