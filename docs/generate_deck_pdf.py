#!/usr/bin/env python3
"""Generate a presentation PDF for the Macro Sign Service demo deck.
Uses only Python standard library -no external dependencies."""

import zlib
import datetime

class PDFWriter:
    """Minimal PDF writer using raw PDF operators."""

    def __init__(self):
        self.objects = []
        self.pages = []
        self.page_width = 792   # 11 inches (landscape)
        self.page_height = 612  # 8.5 inches (landscape)
        self.fonts = {}
        self._setup_fonts()

    # ── fonts ──────────────────────────────────────────────────────
    def _setup_fonts(self):
        self.fonts["F1"] = self._add_obj(
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        )
        self.fonts["F2"] = self._add_obj(
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
        )
        self.fonts["F3"] = self._add_obj(
            "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
        )
        self.fonts["F4"] = self._add_obj(
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>"
        )

    def _add_obj(self, content):
        idx = len(self.objects) + 1
        self.objects.append(content)
        return idx

    # ── helpers ────────────────────────────────────────────────────
    @staticmethod
    def _escape(text):
        # Replace non-ASCII chars with safe ASCII equivalents for Type1 fonts
        text = text.replace("\u2014", " - ")   # em-dash
        text = text.replace("\u2013", " - ")   # en-dash
        text = text.replace("\u2018", "'")      # left single quote
        text = text.replace("\u2019", "'")      # right single quote
        text = text.replace("\u201c", '"')      # left double quote
        text = text.replace("\u201d", '"')      # right double quote
        text = text.replace("\u2022", "-")      # bullet
        text = text.replace("\u2026", "...")    # ellipsis
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def _text_width(self, text, size, bold=False):
        avg = 0.58 if not bold else 0.62
        return len(text) * size * avg

    # ── drawing primitives ─────────────────────────────────────────
    def _draw_rect(self, s, x, y, w, h, r, g, b, fill=True):
        s.append(f"{r:.2f} {g:.2f} {b:.2f} rg")
        s.append(f"{x:.1f} {y:.1f} {w:.1f} {h:.1f} re")
        s.append("f" if fill else "S")

    def _draw_line(self, s, x1, y1, x2, y2, r=0.7, g=0.7, b=0.7, width=0.5):
        s.append(f"{width:.1f} w")
        s.append(f"{r:.2f} {g:.2f} {b:.2f} RG")
        s.append(f"{x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def _draw_text(self, s, x, y, text, font="F1", size=12, r=0, g=0, b=0):
        s.append("BT")
        s.append(f"  /{font} {size} Tf")
        s.append(f"  {r:.2f} {g:.2f} {b:.2f} rg")
        s.append(f"  {x:.1f} {y:.1f} Td")
        s.append(f"  ({self._escape(text)}) Tj")
        s.append("ET")

    def _draw_bullet(self, s, x, y, text, size=14, color=(0.2, 0.2, 0.2), indent=20):
        self._draw_text(s, x, y, "\x95", "F1", size, *color)
        self._draw_text(s, x + indent, y, text, "F1", size, *color)

    # ── page helpers ───────────────────────────────────────────────
    def _slide_bg(self, s):
        self._draw_rect(s, 0, 0, self.page_width, self.page_height, 1, 1, 1)

    def _slide_header_bar(self, s, title, subtitle=None):
        self._draw_rect(s, 0, self.page_height - 90, self.page_width, 90, 0.12, 0.15, 0.28)
        self._draw_text(s, 50, self.page_height - 55, title, "F2", 28, 1, 1, 1)
        if subtitle:
            self._draw_text(s, 50, self.page_height - 78, subtitle, "F4", 14, 0.75, 0.8, 0.9)

    def _slide_footer(self, s, page_num, total):
        self._draw_rect(s, 0, 0, self.page_width, 30, 0.95, 0.95, 0.95)
        self._draw_line(s, 0, 30, self.page_width, 30, 0.85, 0.85, 0.85, 0.5)
        self._draw_text(s, 50, 10, "Macro Sign Service | Demo Deck | March 2026", "F4", 9, 0.5, 0.5, 0.5)
        self._draw_text(s, self.page_width - 70, 10, f"{page_num} / {total}", "F1", 9, 0.5, 0.5, 0.5)

    def _section_label(self, s, x, y, text):
        w = self._text_width(text, 10, bold=True) + 16
        self._draw_rect(s, x, y - 4, w, 20, 0.18, 0.35, 0.72)
        self._draw_text(s, x + 8, y, text, "F2", 10, 1, 1, 1)

    def _draw_table(self, s, x, y, headers, rows, col_widths, row_height=22, font_size=11):
        # header row
        total_w = sum(col_widths)
        self._draw_rect(s, x, y - 2, total_w, row_height, 0.18, 0.35, 0.72)
        cx = x
        for i, h in enumerate(headers):
            self._draw_text(s, cx + 6, y + 4, h, "F2", font_size - 1, 1, 1, 1)
            cx += col_widths[i]
        # data rows
        for ri, row in enumerate(rows):
            ry = y - (ri + 1) * row_height
            bg = (0.96, 0.96, 0.98) if ri % 2 == 0 else (1, 1, 1)
            self._draw_rect(s, x, ry - 2, total_w, row_height, *bg)
            cx = x
            for ci, cell in enumerate(row):
                bold = ci == 0
                f = "F2" if bold else "F1"
                self._draw_text(s, cx + 6, ry + 4, str(cell), f, font_size - 1, 0.15, 0.15, 0.15)
                cx += col_widths[ci]
        # border
        self._draw_line(s, x, y + row_height - 2, x + total_w, y + row_height - 2, 0.18, 0.35, 0.72, 0.8)

    # ── slide builders ─────────────────────────────────────────────
    def _make_slide(self, builder, page_num, total):
        s = []
        self._slide_bg(s)
        builder(s)
        self._slide_footer(s, page_num, total)
        return "\n".join(s)

    # SLIDE 1 -Title
    def slide_title(self, s):
        self._draw_rect(s, 0, 0, self.page_width, self.page_height, 0.12, 0.15, 0.28)
        # accent bar
        self._draw_rect(s, 50, 280, 120, 5, 0.3, 0.56, 0.94)
        self._draw_text(s, 50, 370, "Macro Sign Service", "F2", 44, 1, 1, 1)
        self._draw_text(s, 50, 330, "Automated VBA Macro Signing for Enterprise", "F1", 22, 0.75, 0.8, 0.9)
        self._draw_text(s, 50, 240, "Presented to:  CISO  |  UK Macro Signing Team  |  Switzerland Team", "F1", 15, 0.6, 0.65, 0.75)
        self._draw_text(s, 50, 210, "March 2026", "F4", 14, 0.5, 0.55, 0.65)
        # bottom tagline
        self._draw_rect(s, 0, 50, self.page_width, 50, 0.08, 0.1, 0.2)
        self._draw_text(s, 50, 67, "One service.  Two entities.  Zero manual effort.", "F2", 16, 0.3, 0.56, 0.94)

    # SLIDE 2 -Agenda
    def slide_agenda(self, s):
        self._slide_header_bar(s, "Agenda")
        items = [
            ("01", "The Problem", "Current state & pain points of manual macro signing"),
            ("02", "The Solution", "Macro Sign Service -what it does and how"),
            ("03", "Value Stream & Benefits", "Quantified impact and strategic advantages"),
            ("04", "Architecture Deep Dive", "System components, flows, security, tech stack"),
            ("05", "Live Demo", "End-to-end signing in action"),
            ("06", "Next Steps", "PoC to Group Service roadmap"),
        ]
        y = 460
        for num, title, desc in items:
            self._draw_rect(s, 50, y - 5, 45, 35, 0.18, 0.35, 0.72)
            self._draw_text(s, 60, y + 5, num, "F2", 18, 1, 1, 1)
            self._draw_text(s, 115, y + 8, title, "F2", 18, 0.15, 0.15, 0.15)
            self._draw_text(s, 115, y - 8, desc, "F1", 12, 0.45, 0.45, 0.45)
            y -= 60

    # SLIDE 3 -The Problem: Current Manual Workflow
    def slide_problem_workflow(self, s):
        self._slide_header_bar(s, "The Problem -Current Manual Workflow", "How macro signing works today (UK)")
        y = 470
        self._section_label(s, 50, y, "CURRENT PROCESS")
        y -= 40
        steps = [
            ("1", "Developer uploads .vba file to ServiceNow"),
            ("2", "SNOW ticket created and assigned to UK signing team"),
            ("3", "Team member manually reviews the macro"),
            ("4", "Team member manually signs with certificate tooling"),
            ("5", "Team member uploads signed file back to SNOW"),
            ("6", "Developer downloads signed file -hours to days later"),
        ]
        for num, text in steps:
            self._draw_rect(s, 70, y - 2, 28, 24, 0.9, 0.35, 0.25)
            self._draw_text(s, 79, y + 3, num, "F2", 14, 1, 1, 1)
            self._draw_text(s, 110, y + 3, text, "F1", 14, 0.2, 0.2, 0.2)
            if num != "6":
                self._draw_text(s, 82, y - 18, "|", "F1", 14, 0.7, 0.7, 0.7)
            y -= 42

        # CH callout
        y -= 15
        self._draw_rect(s, 50, y - 8, 690, 38, 1.0, 0.95, 0.9)
        self._draw_rect(s, 50, y - 8, 5, 38, 0.9, 0.55, 0.1)
        self._draw_text(s, 70, y + 10, "Switzerland (CH):", "F2", 14, 0.8, 0.4, 0.0)
        self._draw_text(s, 220, y + 10, "No macro signing solution exists -macros are unsigned or risk-accepted", "F1", 13, 0.5, 0.3, 0.05)

    # SLIDE 4 -The Problem: Bottlenecks
    def slide_problem_bottlenecks(self, s):
        self._slide_header_bar(s, "The Problem -Bottlenecks & Costs")
        headers = ["Bottleneck", "Impact"]
        rows = [
            ["Manual handoff", "Developer uploads -> waits -> team picks up -> signs -> returns"],
            ["Time delay", "Hours to days turnaround per signing request"],
            ["Human error", "Wrong certificate, missed files, copy-paste mistakes"],
            ["No audit trail", "Limited traceability of who signed what and when"],
            ["Scaling cost", "Dedicated team members tied up with repetitive tasks"],
            ["No CI/CD integration", "Macros in repos remain unsigned until manual process completes"],
            ["Single point of failure", "Key team members on leave = signing queue stalls"],
        ]
        self._draw_table(s, 50, 440, headers, rows, [190, 500], row_height=26, font_size=13)

        # cost callout
        y = 195
        self._draw_rect(s, 50, y, 690, 40, 0.95, 0.92, 0.92)
        self._draw_rect(s, 50, y, 5, 40, 0.85, 0.2, 0.2)
        self._draw_text(s, 70, y + 18, "Result:", "F2", 14, 0.7, 0.15, 0.15)
        self._draw_text(s, 140, y + 18, "Slow, error-prone, costly, unscalable, no CH coverage", "F1", 14, 0.4, 0.15, 0.15)

    # SLIDE 5 -The Solution
    def slide_solution(self, s):
        self._slide_header_bar(s, "The Solution -Macro Sign Service")

        self._draw_text(s, 50, 475, "An enterprise-grade, automated macro signing service", "F2", 18, 0.18, 0.35, 0.72)
        self._draw_text(s, 50, 453, "that eliminates manual signing workflows entirely.", "F2", 18, 0.18, 0.35, 0.72)

        # Two boxes side by side
        # Box 1: SNOW Sync
        bx, by, bw, bh = 50, 280, 335, 145
        self._draw_rect(s, bx, by, bw, bh, 0.94, 0.96, 1.0)
        self._draw_rect(s, bx, by + bh - 35, bw, 35, 0.18, 0.35, 0.72)
        self._draw_text(s, bx + 15, by + bh - 25, "ServiceNow  (Synchronous)", "F2", 15, 1, 1, 1)
        self._draw_text(s, bx + 15, by + 85, "Submit macro via SNOW form", "F1", 13, 0.2, 0.2, 0.2)
        self._draw_text(s, bx + 15, by + 62, "Signed content returned instantly", "F2", 13, 0.15, 0.5, 0.15)
        self._draw_text(s, bx + 15, by + 40, "Single HTTP call, 200 OK response", "F1", 12, 0.4, 0.4, 0.4)
        self._draw_text(s, bx + 15, by + 15, "Sub-second turnaround", "F1", 12, 0.4, 0.4, 0.4)

        # Box 2: CI/CD Async
        bx2 = 405
        self._draw_rect(s, bx2, by, bw, bh, 0.94, 1.0, 0.95)
        self._draw_rect(s, bx2, by + bh - 35, bw, 35, 0.15, 0.5, 0.25)
        self._draw_text(s, bx2 + 15, by + bh - 25, "CI/CD Pipeline  (Asynchronous)", "F2", 15, 1, 1, 1)
        self._draw_text(s, bx2 + 15, by + 85, "Auto-sign on git push / PR merge", "F1", 13, 0.2, 0.2, 0.2)
        self._draw_text(s, bx2 + 15, by + 62, "GitHub Actions, Azure DevOps, Jenkins", "F2", 13, 0.15, 0.4, 0.15)
        self._draw_text(s, bx2 + 15, by + 40, "202 Accepted -> poll -> completed", "F1", 12, 0.4, 0.4, 0.4)
        self._draw_text(s, bx2 + 15, by + 15, "Webhook notifications supported", "F1", 12, 0.4, 0.4, 0.4)

        # Before / After
        y = 240
        self._draw_line(s, 50, y, 740, y, 0.85, 0.85, 0.85, 0.8)
        y -= 30
        self._draw_text(s, 50, y, "BEFORE", "F2", 14, 0.75, 0.25, 0.25)
        self._draw_text(s, 180, y, "Upload -> Wait hours/days -> Manual sign -> Return", "F1", 13, 0.5, 0.3, 0.3)
        y -= 30
        self._draw_text(s, 50, y, "AFTER", "F2", 14, 0.15, 0.55, 0.25)
        self._draw_text(s, 180, y, "Upload -> Signed instantly  |  git push -> Signed automatically", "F1", 13, 0.2, 0.5, 0.2)

        y -= 50
        self._draw_rect(s, 50, y - 5, 690, 35, 0.93, 0.97, 0.93)
        self._draw_rect(s, 50, y - 5, 5, 35, 0.15, 0.6, 0.25)
        self._draw_text(s, 70, y + 7, "Zero human intervention.  24/7 availability.  Full audit trail.", "F2", 14, 0.1, 0.45, 0.15)

    # SLIDE 6 -Value Stream
    def slide_value_stream(self, s):
        self._slide_header_bar(s, "Value Stream & Benefits", "Quantified impact")
        headers = ["Metric", "Before (Manual)", "After (Automated)", "Improvement"]
        rows = [
            ["Turnaround time", "Hours to days", "Sub-second", "~99.9% faster"],
            ["Human effort", "15-30 min / signing", "0 min", "100% eliminated"],
            ["Error rate", "Manual mistakes", "Deterministic", "Near-zero"],
            ["Audit completeness", "Partial / manual", "Every op logged", "100% traceability"],
            ["Availability", "Business hours only", "24/7 automated", "Always-on"],
            ["CH coverage", "None", "Full capability", "New capability"],
        ]
        self._draw_table(s, 40, 440, headers, rows, [160, 170, 170, 175], row_height=26, font_size=12)

        y = 245
        self._section_label(s, 50, y, "STRATEGIC BENEFITS")
        y -= 35
        benefits = [
            "Security posture -every macro cryptographically signed; full compliance audit trail",
            "Developer velocity -no more waiting; signing in CI/CD or instant via SNOW",
            "Operational cost -frees signing team for higher-value security work",
            "Scalability -hundreds of requests/min; no human bottleneck",
            "Group standardization -one service for UK + CH (+ future entities)",
            "Risk reduction -eliminates unsigned macros in CH; reduces human error in UK",
        ]
        for b in benefits:
            self._draw_bullet(s, 60, y, b, 12, (0.2, 0.2, 0.2))
            y -= 24

    # SLIDE 7 -Architecture Overview
    def slide_architecture(self, s):
        self._slide_header_bar(s, "Architecture -System Overview")

        # Consumers row
        cy = 465
        self._section_label(s, 50, cy + 5, "CONSUMERS")
        boxes = [("ServiceNow", "Sync sign"), ("CI/CD Pipelines", "Async sign"), ("CLI / SDK", "Local dev"), ("Admin Dashboard", "Next.js :3000")]
        bx = 190
        for title, sub in boxes:
            self._draw_rect(s, bx, cy - 8, 130, 40, 0.92, 0.94, 0.98)
            self._draw_text(s, bx + 8, cy + 10, title, "F2", 10, 0.15, 0.15, 0.15)
            self._draw_text(s, bx + 8, cy - 3, sub, "F1", 9, 0.5, 0.5, 0.5)
            bx += 140

        # Arrow down
        self._draw_text(s, 400, cy - 25, "v", "F2", 16, 0.18, 0.35, 0.72)

        # API Server
        ay = 380
        self._draw_rect(s, 50, ay - 10, 690, 55, 0.18, 0.35, 0.72)
        self._draw_text(s, 65, ay + 25, "FastAPI  API  Server  (:8000)", "F2", 16, 1, 1, 1)
        endpoints = ["/snow/sign (sync)", "/sign (async)", "/auth/* (JWT+RBAC)", "/admin/*", "/webhooks"]
        ex = 65
        for ep in endpoints:
            self._draw_text(s, ex, ay - 2, ep, "F3", 8, 0.85, 0.9, 1.0)
            ex += 135

        # Arrow down
        self._draw_text(s, 400, ay - 28, "v", "F2", 16, 0.18, 0.35, 0.72)

        # Core Engine
        ey = 295
        self._draw_rect(s, 50, ey - 10, 340, 50, 0.94, 0.96, 1.0)
        self._draw_text(s, 65, ey + 20, "Signing Engine", "F2", 13, 0.15, 0.15, 0.15)
        self._draw_text(s, 65, ey + 2, "RSA / ECDSA  |  SHA-256/384/512", "F1", 10, 0.4, 0.4, 0.4)

        self._draw_rect(s, 400, ey - 10, 340, 50, 0.94, 0.96, 1.0)
        self._draw_text(s, 415, ey + 20, "Certificate Store (Pluggable)", "F2", 13, 0.15, 0.15, 0.15)
        self._draw_text(s, 415, ey + 2, "Local | Vault | AWS KMS | Azure KV", "F1", 10, 0.4, 0.4, 0.4)

        # Arrow down
        self._draw_text(s, 400, ey - 28, "v", "F2", 16, 0.18, 0.35, 0.72)

        # Data layer
        dy = 200
        infra = [
            ("Celery Workers", "Async tasks, retries", 50),
            ("PostgreSQL 16", "Users, jobs, audit", 240),
            ("Redis 7", "Broker, cache", 430),
            ("Prometheus+Grafana", "Metrics, dashboards", 600),
        ]
        for title, sub, ix in infra:
            self._draw_rect(s, ix, dy - 5, 155, 45, 0.95, 0.95, 0.95)
            self._draw_text(s, ix + 10, dy + 18, title, "F2", 11, 0.2, 0.2, 0.2)
            self._draw_text(s, ix + 10, dy + 2, sub, "F1", 9, 0.5, 0.5, 0.5)

        # Security callout
        sy = 130
        self._draw_rect(s, 50, sy, 690, 35, 0.93, 0.97, 0.93)
        self._draw_rect(s, 50, sy, 5, 35, 0.15, 0.6, 0.25)
        self._draw_text(s, 70, sy + 12, "Security:  JWT + API Keys  |  RBAC (4 roles)  |  Full audit trail  |  HMAC webhooks  |  Rate limiting  |  File validation", "F1", 11, 0.15, 0.45, 0.2)

    # SLIDE 8 -SNOW Signing Flow
    def slide_snow_flow(self, s):
        self._slide_header_bar(s, "Architecture -ServiceNow Signing Flow", "Synchronous -single HTTP call, instant response")

        steps = [
            ("SNOW Form", "POST /api/v1/snow/sign\nfile + requester_id + algorithm"),
            ("File Validator", "Extension check, size < 50 MB\nDangerous pattern scan"),
            ("Certificate Store", "get_or_create_certificate()\nAuto-provisions if missing"),
            ("Signing Engine", "SHA-256 hash of content\nRSA PKCS1v15 signature"),
            ("Audit Log", "User, IP, file hash\nCert fingerprint, timestamp"),
            ("200 OK Response", "signed_content_b64, signature\ncertificate_pem, signed_at"),
        ]

        bx = 60
        by = 430
        box_w = 200
        box_h = 60
        gap = 60

        for i, (title, desc) in enumerate(steps):
            col = i % 3
            row = i // 3
            x = bx + col * (box_w + 30)
            y = by - row * (box_h + gap)

            color = (0.18, 0.35, 0.72) if i < 5 else (0.15, 0.55, 0.25)
            self._draw_rect(s, x, y, box_w, box_h, *color)
            self._draw_text(s, x + 10, y + 38, title, "F2", 13, 1, 1, 1)
            lines = desc.split("\n")
            for li, line in enumerate(lines):
                self._draw_text(s, x + 10, y + 20 - li * 14, line, "F1", 9, 0.85, 0.9, 1.0)

            # Arrow
            if i < 5 and i != 2:
                ax = x + box_w + 5
                ay2 = y + box_h // 2
                self._draw_text(s, ax, ay2, "->", "F2", 14, 0.5, 0.5, 0.5)

        # Result box
        ry = 155
        self._draw_rect(s, 60, ry, 680, 80, 0.96, 0.98, 0.96)
        self._draw_text(s, 75, ry + 55, "Response (200 OK):", "F2", 13, 0.15, 0.5, 0.2)
        response_fields = [
            '"status": "signed"     "signature": "<hex>"     "file_hash": "<hex>"',
            '"certificate_fingerprint": "AB:CD:..."     "certificate_pem": "-----BEGIN..."     "signed_at": "..."',
        ]
        for i, line in enumerate(response_fields):
            self._draw_text(s, 75, ry + 30 - i * 18, line, "F3", 10, 0.3, 0.3, 0.3)

    # SLIDE 9 -Tech Stack & Security
    def slide_tech_security(self, s):
        self._slide_header_bar(s, "Technology Stack & Security Controls")

        # Tech stack table
        self._section_label(s, 50, 470, "TECH STACK")
        headers = ["Layer", "Technology"]
        rows = [
            ["API", "Python 3.11+, FastAPI, Uvicorn"],
            ["Task Queue", "Celery + Redis broker"],
            ["Database", "PostgreSQL 16, SQLAlchemy (async)"],
            ["Crypto", "RSA, ECDSA, X.509, SHA-256/384/512"],
            ["Auth", "JWT (30 min) + API Keys + RBAC"],
            ["Dashboard", "Next.js 14, React 18, Tailwind CSS"],
            ["Cert Backends", "Local | Vault | AWS KMS | Azure KV"],
            ["Monitoring", "Prometheus + Grafana"],
            ["Deployment", "Docker Compose (dev), K8s + Helm (prod)"],
        ]
        self._draw_table(s, 50, 440, headers, rows, [130, 320], row_height=22, font_size=11)

        # Security column
        sx = 520
        self._section_label(s, sx, 470, "SECURITY")
        security = [
            "Private keys never leave Vault / KMS",
            "JWT tokens (30 min expiry) + refresh",
            "API keys with mss_ prefix (secrets scan)",
            "RBAC: Admin, Manager, Developer, Viewer",
            "Full audit: user, IP, hash, cert, timestamp",
            "File validation: ext, size, pattern scan",
            "HMAC-SHA256 signed webhook payloads",
            "Rate limiting: 60 req/min per user",
            "Bcrypt password hashing (cost 12)",
        ]
        sy = 440
        for item in security:
            self._draw_bullet(s, sx + 10, sy + 4, item, 10, (0.2, 0.2, 0.2), 12)
            sy -= 22

    # SLIDE 10 -Live Demo
    def slide_demo(self, s):
        self._slide_header_bar(s, "Live Demo")
        self._draw_text(s, 50, 475, "What we will demonstrate:", "F2", 16, 0.2, 0.2, 0.2)

        demos = [
            ("1", "Service Startup", "docker-compose up -all services come online"),
            ("2", "Health Check", "curl /api/v1/health -confirms DB + Redis connectivity"),
            ("3", "SNOW Sync Signing", "POST .vba to /snow/sign -signed content back instantly (200 OK)"),
            ("4", "Signature Verification", "POST file + signature to /snow/verify -confirms is_valid: true"),
            ("5", "CI/CD Async Signing", "POST /sign -> job_id -> poll /status/{job_id} -> completed"),
            ("6", "Admin Dashboard", "Web UI: signing jobs, audit logs, certificates, users/teams"),
            ("7", "Audit Trail", "Full log: who signed, when, file hash, which certificate"),
            ("8", "Certificate Mgmt", "List certs, view details, auto-provisioning"),
        ]

        y = 435
        for num, title, desc in demos:
            self._draw_rect(s, 60, y - 2, 30, 26, 0.18, 0.35, 0.72)
            self._draw_text(s, 70, y + 5, num, "F2", 13, 1, 1, 1)
            self._draw_text(s, 105, y + 6, title, "F2", 14, 0.15, 0.15, 0.15)
            self._draw_text(s, 290, y + 6, desc, "F1", 12, 0.4, 0.4, 0.4)
            y -= 38

        # Key demo command
        y -= 20
        self._draw_rect(s, 50, y - 10, 690, 50, 0.15, 0.15, 0.2)
        self._draw_text(s, 65, y + 20, "# Sign a macro -instant response", "F3", 10, 0.5, 0.7, 0.5)
        self._draw_text(s, 65, y + 2, 'curl -X POST http://localhost:8000/api/v1/snow/sign -F "file=@macro.vba"', "F3", 10, 0.3, 0.9, 0.3)

    # SLIDE 11 -Next Steps: Entity Coverage
    def slide_next_steps_entities(self, s):
        self._slide_header_bar(s, "Next Steps -Entity Coverage")

        headers = ["Entity", "Current State", "With Macro Sign Service"]
        rows = [
            ["UK", "Manual SNOW workflow", "Automated signing via SNOW + CI/CD"],
            ["Switzerland (CH)", "No solution exists", "Full signing capability -same standards"],
            ["Future entities", "No standardization", "Onboard to the same group service"],
        ]
        self._draw_table(s, 50, 455, headers, rows, [150, 230, 310], row_height=28, font_size=13)

        # Key message
        y = 310
        self._draw_rect(s, 50, y, 690, 40, 0.93, 0.96, 1.0)
        self._draw_rect(s, 50, y, 5, 40, 0.18, 0.35, 0.72)
        self._draw_text(s, 70, y + 14, "This is not just a UK tool - it is a Group Service opportunity.", "F2", 15, 0.18, 0.35, 0.72)

        # Stakeholder table
        y = 260
        self._section_label(s, 50, y, "KEY STAKEHOLDERS")
        y -= 28
        stakeholders = [
            ("CISO", "Approve approach, sponsor Group Service elevation"),
            ("UK Signing Team", "Primary users, validate workflow replacement"),
            ("CH Team", "New capability beneficiaries, validate requirements"),
            ("Group InfoSec", "Co-own the service, define certificate & signing policies"),
            ("Group IAM", "Integrate with centralised identity (SSO, API auth)"),
            ("Platform / Infra", "Kubernetes hosting, monitoring, SLA"),
        ]
        for name, role in stakeholders:
            self._draw_text(s, 70, y, name, "F2", 12, 0.2, 0.2, 0.2)
            self._draw_text(s, 230, y, role, "F1", 12, 0.4, 0.4, 0.4)
            y -= 22

    # SLIDE 12 -Roadmap: PoC to Group Service
    def slide_roadmap(self, s):
        self._slide_header_bar(s, "Roadmap -PoC to Group Service")

        # Three phase boxes
        phases = [
            ("PHASE 1 -NOW", "PoC / Demo", [
                "Demo to CISO & teams",
                "Validate architecture & security",
                "Gather feedback from UK + CH",
                "Confirm fit for both entities",
            ], (0.18, 0.35, 0.72)),
            ("PHASE 2", "Production Pilot", [
                "Deploy to Kubernetes (prod)",
                "Integrate with Group IAM / SSO",
                "Enterprise CA certificates",
                "Onboard UK + CH teams",
                "Connect to SNOW production",
            ], (0.15, 0.5, 0.25)),
            ("PHASE 3", "Group Service", [
                "Official Group Service status",
                "Co-owned: Group InfoSec + IAM",
                "HSM / PKCS#11 for hardware keys",
                "SLA-backed availability",
                "Onboard future entities",
            ], (0.55, 0.25, 0.6)),
        ]

        bx = 50
        for title, subtitle, items, color in phases:
            # Phase box
            self._draw_rect(s, bx, 160, 220, 310, 0.97, 0.97, 0.97)
            self._draw_rect(s, bx, 430, 220, 40, *color)
            self._draw_text(s, bx + 12, 448, title, "F2", 13, 1, 1, 1)
            self._draw_text(s, bx + 12, 415, subtitle, "F2", 16, 0.15, 0.15, 0.15)

            iy = 390
            for item in items:
                self._draw_bullet(s, bx + 15, iy, item, 11, (0.3, 0.3, 0.3), 12)
                iy -= 22

            # Arrow between phases
            if bx < 500:
                self._draw_text(s, bx + 228, 340, "->", "F2", 20, 0.5, 0.5, 0.5)

            bx += 250

        # Convert PoC callout
        y = 115
        self._draw_rect(s, 50, y, 690, 40, 0.95, 0.93, 0.97)
        self._draw_rect(s, 50, y, 5, 40, 0.55, 0.25, 0.6)
        self._draw_text(s, 70, y + 14,
            "When elevated to Group Service: convert PoC to production service with Group InfoSec & Group IAM ownership",
            "F2", 12, 0.4, 0.2, 0.5)

    # SLIDE 13 -Summary / Closing
    def slide_summary(self, s):
        self._draw_rect(s, 0, 0, self.page_width, self.page_height, 0.12, 0.15, 0.28)

        self._draw_text(s, 50, 480, "Summary", "F2", 36, 1, 1, 1)
        self._draw_rect(s, 50, 465, 120, 4, 0.3, 0.56, 0.94)

        headers = ["", "Manual (Today)", "Macro Sign Service"]
        rows = [
            ["Speed", "Hours to days", "Sub-second"],
            ["Cost", "Dedicated team effort", "Zero marginal cost"],
            ["Coverage", "UK only", "UK + CH + future"],
            ["Audit", "Partial", "Complete, automated"],
            ["CI/CD", "Not integrated", "Native integration"],
            ["Availability", "Business hours", "24/7"],
            ["Risk", "Human error + no CH", "Deterministic, enforced"],
        ]

        # Draw table on dark bg with light colors
        y = 410
        # Header
        tw = 600
        cx = 96
        self._draw_rect(s, cx, y - 2, tw, 24, 0.3, 0.56, 0.94)
        col_ws = [150, 225, 225]
        hx = cx
        for i, h in enumerate(headers):
            self._draw_text(s, hx + 8, y + 4, h, "F2", 12, 1, 1, 1)
            hx += col_ws[i]

        for ri, row in enumerate(rows):
            ry = y - (ri + 1) * 24
            bg = (0.16, 0.19, 0.32) if ri % 2 == 0 else (0.14, 0.17, 0.3)
            self._draw_rect(s, cx, ry - 2, tw, 24, *bg)
            rx = cx
            for ci, cell in enumerate(row):
                f = "F2" if ci == 0 else "F1"
                color = (0.85, 0.88, 0.95) if ci < 2 else (0.4, 0.9, 0.5)
                self._draw_text(s, rx + 8, ry + 4, cell, f, 12, *color)
                rx += col_ws[ci]

        # Tagline
        y = 160
        self._draw_rect(s, 50, y, 692, 50, 0.08, 0.1, 0.2)
        self._draw_text(s, 130, y + 17, "One service.   Two entities.   Zero manual effort.", "F2", 24, 0.3, 0.56, 0.94)

        # Thank you
        self._draw_text(s, 50, 100, "Thank you", "F2", 28, 0.7, 0.75, 0.85)
        self._draw_text(s, 50, 70, "Questions?", "F4", 18, 0.5, 0.55, 0.65)

    # ── build PDF ──────────────────────────────────────────────────
    def build(self):
        slides = [
            self.slide_title,
            self.slide_agenda,
            self.slide_problem_workflow,
            self.slide_problem_bottlenecks,
            self.slide_solution,
            self.slide_value_stream,
            self.slide_architecture,
            self.slide_snow_flow,
            self.slide_tech_security,
            self.slide_demo,
            self.slide_next_steps_entities,
            self.slide_roadmap,
            self.slide_summary,
        ]
        total = len(slides)
        for i, builder in enumerate(slides):
            stream_content = self._make_slide(builder, i + 1, total)
            stream_bytes = stream_content.encode("latin-1", errors="replace")
            compressed = zlib.compress(stream_bytes)
            stream_obj = (
                f"<< /Length {len(compressed)} /Filter /FlateDecode >>\n"
                f"stream\n"
            )
            stream_id = self._add_obj(("__stream__", compressed, stream_obj))

            font_dict = " ".join(f"/{k} {v} 0 R" for k, v in self.fonts.items())
            resources = f"<< /Font << {font_dict} >> >>"
            page_id = self._add_obj(
                f"<< /Type /Page /Parent __pages__ 0 R "
                f"/MediaBox [0 0 {self.page_width} {self.page_height}] "
                f"/Contents {stream_id} 0 R "
                f"/Resources {resources} >>"
            )
            self.pages.append(page_id)

        # Pages object
        kids = " ".join(f"{p} 0 R" for p in self.pages)
        pages_id = self._add_obj(
            f"<< /Type /Pages /Kids [{kids}] /Count {len(self.pages)} >>"
        )
        # Fix parent references
        for i, obj in enumerate(self.objects):
            if isinstance(obj, str) and "__pages__" in obj:
                self.objects[i] = obj.replace("__pages__", str(pages_id))

        # Catalog
        catalog_id = self._add_obj(
            f"<< /Type /Catalog /Pages {pages_id} 0 R >>"
        )

        # Info
        now = datetime.datetime.now().strftime("D:%Y%m%d%H%M%S")
        info_id = self._add_obj(
            f"<< /Title (Macro Sign Service - Demo Deck) "
            f"/Author (Macro Sign Service Team) "
            f"/Subject (Demo Presentation for CISO and UK/CH Teams) "
            f"/CreationDate ({now}) >>"
        )

        # Serialize
        out = []
        out.append(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, obj in enumerate(self.objects):
            offsets.append(sum(len(x) for x in out))
            obj_num = i + 1
            if isinstance(obj, tuple) and obj[0] == "__stream__":
                _, compressed, header = obj
                out.append(f"{obj_num} 0 obj\n{header}".encode("latin-1"))
                out.append(compressed)
                out.append(b"\nendstream\nendobj\n")
            else:
                out.append(f"{obj_num} 0 obj\n{obj}\nendobj\n".encode("latin-1"))

        xref_offset = sum(len(x) for x in out)
        out.append(f"xref\n0 {len(self.objects) + 1}\n".encode())
        out.append(b"0000000000 65535 f \n")
        for off in offsets:
            out.append(f"{off:010d} 00000 n \n".encode())
        out.append(
            f"trailer\n<< /Size {len(self.objects) + 1} "
            f"/Root {catalog_id} 0 R /Info {info_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n".encode()
        )
        return b"".join(out)


if __name__ == "__main__":
    pdf = PDFWriter()
    data = pdf.build()
    output_path = "/home/user/macro-sign-service/docs/DEMO_DECK.pdf"
    with open(output_path, "wb") as f:
        f.write(data)
    print(f"PDF generated: {output_path} ({len(data):,} bytes, {len(pdf.pages)} slides)")
