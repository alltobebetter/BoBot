"""动态帮助（按分类）。"""
from __future__ import annotations


def register(router):
    @router.command("help", "menu", help="显示帮助", category="其他")
    def help_cmd(ctx):
        entries = router.help_entries()
        cats = {}
        for name, info in entries.items():
            cats.setdefault(info["category"], []).append((name, info["help"]))
        lines = [f"[INFO] {ctx.bot.config.bot.name} 命令帮助"]
        for cat in sorted(cats):
            lines.append(f"\n【{cat}】")
            for name, h in sorted(cats[cat]):
                lines.append(f"{name} - {h}" if h else f"{name}")
        lines.append(f"\n网页版：{ctx.bot.config.bot.web_url}")
        ctx.reply_smart("\n".join(lines))
