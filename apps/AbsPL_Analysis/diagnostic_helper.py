"""
Diagnostic helper for AbsPL analysis app.
Provides structured diagnostics output for a dashboard tile.
"""

import html
from datetime import datetime


class DiagnosticLogger:
    def __init__(self):
        self.messages = []

    def add(self, category, message, level="INFO"):
        self.messages.append(
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "category": str(category),
                "level": str(level).upper(),
                "message": str(message),
            }
        )

    def clear(self):
        self.messages = []

    def _level_color(self, level):
        if level == "ERROR":
            return "#b42318"
        if level == "WARNING":
            return "#b54708"
        if level == "SUCCESS":
            return "#027a48"
        return "#175cd3"

    def get_html(self):
        if not self.messages:
            return "<div style='padding:12px;color:#667085;'>No diagnostic messages yet.</div>"

        total = len(self.messages)
        errors = sum(1 for m in self.messages if m["level"] == "ERROR")
        warnings = sum(1 for m in self.messages if m["level"] == "WARNING")

        blocks = [
            "<div style='font-family:Segoe UI,Arial,sans-serif;background:#f8fafc;border:1px solid #e4e7ec;border-radius:10px;padding:12px;'>",
            f"<div style='display:flex;gap:14px;margin-bottom:10px;'><span><b>Total:</b> {total}</span><span><b>Warnings:</b> {warnings}</span><span><b>Errors:</b> {errors}</span></div>",
            "<div style='max-height:340px;overflow-y:auto;background:#fff;border:1px solid #eaecf0;border-radius:8px;padding:8px;'>",
        ]

        for m in reversed(self.messages[-200:]):
            color = self._level_color(m["level"])
            msg = html.escape(m["message"])
            cat = html.escape(m["category"])
            blocks.append(
                f"<div style='padding:6px 4px;border-bottom:1px solid #f2f4f7;'>"
                f"<span style='color:#667085;'>[{m['time']}]</span> "
                f"<span style='color:{color};font-weight:600;'>[{m['level']}]</span> "
                f"<span style='color:#344054;'>[{cat}]</span> "
                f"<span style='color:#101828;'>{msg}</span>"
                f"</div>"
            )

        blocks.append("</div></div>")
        return "".join(blocks)


debug_logger_abspl = DiagnosticLogger()
