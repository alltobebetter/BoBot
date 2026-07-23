"""CodeAgent - AI 代码生成 Agent，操作 Supabase Storage。

用户输入需求 → AI 通过 tool-calling 创建/编辑文件 → 用户在线预览。
复用 AIService 的多 Provider fallback 机制。
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, List

import httpx

from config import config
from core.result import Result
from utils.logger import log
from utils.text import user_key


def _project_code(nick: str, trip: str) -> str:
    """根据用户身份生成固定的项目目录名（10 位 hex）。"""
    raw = user_key(nick, trip)
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


# ============ Supabase Storage ============

class SupabaseStorage:
    """Supabase Storage REST API 封装。"""

    def __init__(self):
        self.url = config.api.supabase_url
        self.key = config.api.supabase_key
        self.bucket = config.api.supabase_bucket
        self._headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}

    @property
    def available(self) -> bool:
        return bool(self.url and self.key)

    def _mime(self, path: str) -> str:
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else "txt"
        return {
            "html": "text/html", "css": "text/css", "js": "application/javascript",
            "json": "application/json", "md": "text/markdown", "svg": "image/svg+xml",
            "py": "text/plain", "ts": "text/plain", "txt": "text/plain",
        }.get(ext, "text/plain")

    def list_files(self, project: str, prefix: str = "") -> Dict:
        full = f"{project}/{prefix}" if prefix else f"{project}/"
        r = httpx.post(
            f"{self.url}/storage/v1/object/list/{self.bucket}",
            headers={**self._headers, "Content-Type": "application/json"},
            json={"prefix": full, "limit": 200},
            timeout=15.0,
        )
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
        items = []
        for item in r.json():
            name = item.get("name", "")
            if not name or name == ".emptyFolderPlaceholder":
                continue
            items.append({"name": name, "type": "dir" if item.get("id") is None else "file"})
        return {"files": items}

    def read_file(self, project: str, path: str) -> Dict:
        r = httpx.get(
            f"{self.url}/storage/v1/object/{self.bucket}/{project}/{path}",
            headers=self._headers, timeout=15.0,
        )
        if r.status_code == 200:
            return {"content": r.text}
        return {"error": f"HTTP {r.status_code}"}

    def write_file(self, project: str, path: str, content: str) -> Dict:
        r = httpx.post(
            f"{self.url}/storage/v1/object/{self.bucket}/{project}/{path}",
            headers={**self._headers, "Content-Type": self._mime(path), "x-upsert": "true"},
            content=content.encode("utf-8"), timeout=15.0,
        )
        if r.status_code in (200, 201):
            return {"ok": True, "message": f"已写入 {path}"}
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}

    def delete_file(self, project: str, path: str) -> Dict:
        r = httpx.request("DELETE",
            f"{self.url}/storage/v1/object/{self.bucket}",
            headers={**self._headers, "Content-Type": "application/json"},
            json={"prefixes": [f"{project}/{path}"]}, timeout=15.0,
        )
        if r.status_code == 200:
            return {"ok": True, "message": f"已删除 {path}"}
        return {"error": f"HTTP {r.status_code}"}

    def move_file(self, project: str, src: str, dst: str) -> Dict:
        r = httpx.post(
            f"{self.url}/storage/v1/object/move",
            headers={**self._headers, "Content-Type": "application/json"},
            json={"bucketId": self.bucket,
                  "sourceKey": f"{project}/{src}", "destinationKey": f"{project}/{dst}"},
            timeout=15.0,
        )
        if r.status_code == 200:
            return {"ok": True, "message": f"已移动 {src} → {dst}"}
        return {"error": f"HTTP {r.status_code}"}

    def edit_file(self, project: str, path: str, old: str, new: str) -> Dict:
        rd = self.read_file(project, path)
        if "error" in rd:
            return rd
        content = rd["content"]
        count = content.count(old)
        if count == 0:
            return {"error": "未找到要替换的内容"}
        if count > 1:
            return {"error": f"找到 {count} 处匹配，请提供更精确的内容"}
        return self.write_file(project, path, content.replace(old, new, 1))

    def file_tree(self, project: str, prefix: str = "", depth: int = 0,
                  max_items: int = 50) -> Tuple[List[str], int]:
        result = self.list_files(project, prefix)
        if "error" in result:
            return [], 0
        lines, count = [], 0
        indent = "  " * depth
        for item in result["files"]:
            if count >= max_items:
                lines.append(f"{indent}... (已省略)")
                break
            name = item["name"]
            if item["type"] == "dir":
                lines.append(f"{indent}{name}/")
                count += 1
                sub = f"{prefix}{name}/" if prefix else f"{name}/"
                sl, sc = self.file_tree(project, sub, depth + 1, max_items - count)
                lines.extend(sl)
                count += sc
            else:
                lines.append(f"{indent}{name}")
                count += 1
        return lines, count


# ============ Code Tools ============

CODE_TOOLS = [
    {"type": "function", "function": {
        "name": "list_files", "description": "列出项目目录下的文件和文件夹",
        "parameters": {"type": "object",
            "properties": {"prefix": {"type": "string", "description": "子目录路径，留空列根目录"}}}}},
    {"type": "function", "function": {
        "name": "read_file", "description": "读取指定文件的文本内容",
        "parameters": {"type": "object", "required": ["file_path"],
            "properties": {"file_path": {"type": "string", "description": "文件路径"}}}}},
    {"type": "function", "function": {
        "name": "create_file", "description": "创建或覆盖文件",
        "parameters": {"type": "object", "required": ["file_path", "content"],
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "edit_file", "description": "局部编辑：查找 old_str 替换为 new_str（须唯一匹配）",
        "parameters": {"type": "object", "required": ["file_path", "old_str", "new_str"],
            "properties": {"file_path": {"type": "string"},
                "old_str": {"type": "string"}, "new_str": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "delete_file", "description": "删除文件",
        "parameters": {"type": "object", "required": ["file_path"],
            "properties": {"file_path": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "move_file", "description": "移动或重命名文件",
        "parameters": {"type": "object", "required": ["from_path", "to_path"],
            "properties": {"from_path": {"type": "string"}, "to_path": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "web_search", "description": "搜索互联网获取技术文档等",
        "parameters": {"type": "object", "required": ["query"],
            "properties": {"query": {"type": "string"},
                "max_results": {"type": "integer", "default": 3}}}}},
]

CODE_PROMPT = """你是 BoB CodeAgent，专业代码生成助手。
工作目录：项目 {project}
预览地址：{preview_url}

可用工具：list_files, read_file, create_file, edit_file, delete_file, move_file, web_search

原则：
- 直接开始编写代码，不需询问确认
- 创建完整可运行项目，HTML 项目以 index.html 为入口
- 修改已有文件优先用 edit_file 局部编辑
- 完成后只输出一句简洁总结，不解释代码细节
"""


class CodeAgent:
    """代码生成 Agent。"""

    MAX_ROUNDS = 15

    def __init__(self, app):
        self.app = app
        self.storage = SupabaseStorage()

    @property
    def available(self) -> bool:
        return self.storage.available and self.app.ai.enabled

    @property
    def preview_base(self) -> str:
        return config.api.code_preview_base

    def preview_url(self, nick: str, trip: str) -> str:
        return f"{self.preview_base}/{_project_code(nick, trip)}"

    def _execute_tool(self, project: str, name: str, args: Dict) -> str:
        s = self.storage
        if name == "list_files":
            result = s.list_files(project, args.get("prefix", ""))
        elif name == "read_file":
            result = s.read_file(project, args["file_path"])
        elif name == "create_file":
            result = s.write_file(project, args["file_path"], args["content"])
        elif name == "edit_file":
            result = s.edit_file(project, args["file_path"], args["old_str"], args["new_str"])
        elif name == "delete_file":
            result = s.delete_file(project, args["file_path"])
        elif name == "move_file":
            result = s.move_file(project, args["from_path"], args["to_path"])
        elif name == "web_search":
            result = self.app.ai.web_search(args.get("query", ""))
        else:
            result = {"error": f"未知工具: {name}"}
        return json.dumps(result, ensure_ascii=False)

    def run(self, nick: str, trip: str, prompt: str) -> Result:
        """执行代码生成，返回 Result（reply 在 message）。"""
        if not self.available:
            return Result.fail("CodeAgent 未配置（需要 Supabase + AI）")

        project = _project_code(nick, trip)
        preview = f"{self.preview_base}/{project}"

        system = CODE_PROMPT.format(project=project, preview_url=preview)
        tree_lines, _ = self.storage.file_tree(project, max_items=50)
        if tree_lines:
            system += f"\n\n当前项目文件结构:\n```\n" + "\n".join(tree_lines) + "\n```"
        else:
            system += "\n\n当前项目为空。"

        messages: List[Dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        # 复用 AIService 的 provider fallback + 并发控制
        for provider in self.app.ai.providers:
            client = self.app.ai.get_client(provider)
            if client is None:
                continue
            try:
                with self.app.ai.concurrency_slot():
                    reply = self._run_loop(client, provider, project, messages)
                return Result.ok(reply, {"preview": preview})
            except Exception as e:
                log.warning("CodeAgent provider 失败，尝试下一个",
                           provider=provider.name, error=str(e))
                continue
        return Result.fail("CodeAgent 执行失败（所有 provider 不可用）")

    def _run_loop(self, client, provider, project: str,
                  messages: List[Dict]) -> str:
        for _ in range(self.MAX_ROUNDS):
            resp = self.app.ai.request_with_tools(
                client, provider, messages, CODE_TOOLS,
                temperature=0.3,
            )
            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                return msg.content or "完成"

            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                result = self._execute_tool(project, tc.function.name, args)
                messages.append({
                    "role": "tool", "tool_call_id": tc.id, "content": result,
                })

        return "已完成（工具调用轮次较多）"
