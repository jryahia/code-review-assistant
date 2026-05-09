"""Markdown and PDF report builder."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.scoring import get_score_band, severity_color


def generate_markdown_report(review_data: Dict[str, Any]) -> str:
    """Generate a complete Markdown code review report."""
    lines: List[str] = []
    score = review_data.get("score", 0) or 0
    label, _ = get_score_band(score)
    pr_url = review_data.get("pr_url", "")
    pr_title = review_data.get("pr_title", "Untitled PR")
    created_at = review_data.get("created_at", datetime.utcnow())
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)

    lines.append(f"# Code Review Report")
    lines.append(f"")
    lines.append(f"**PR:** [{pr_title}]({pr_url})")
    lines.append(f"**Date:** {created_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Score:** {score:.1f}/100 — {label}")
    lines.append(f"")

    # Summary stats
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Files Changed | {review_data.get('files_changed', 0)} |")
    lines.append(f"| Lines Added | +{review_data.get('lines_added', 0)} |")
    lines.append(f"| Lines Removed | -{review_data.get('lines_removed', 0)} |")
    lines.append(f"| Critical Issues | {review_data.get('critical_count', 0)} |")
    lines.append(f"| Warnings | {review_data.get('warning_count', 0)} |")
    lines.append(f"| Suggestions | {review_data.get('suggestion_count', 0)} |")
    lines.append(f"| Total Findings | {review_data.get('total_findings', 0)} |")
    lines.append("")

    # AI Summary
    if review_data.get("ai_summary"):
        lines.append("## AI Analysis")
        lines.append("")
        lines.append(review_data["ai_summary"])
        lines.append("")

    # Score gauge
    lines.append("## Score")
    lines.append("")
    bar_filled = int(score / 5)
    bar_empty = 20 - bar_filled
    bar = "█" * bar_filled + "░" * bar_empty
    lines.append(f"```")
    lines.append(f"[{bar}] {score:.1f}/100 ({label})")
    lines.append(f"```")
    lines.append("")

    # File breakdown
    file_reviews = review_data.get("file_reviews", [])
    if file_reviews:
        lines.append("## File Analysis")
        lines.append("")
        for fr in file_reviews:
            filename = fr.get("filename", "unknown")
            lang = fr.get("language", "unknown")
            file_score = fr.get("score", 100) or 100
            findings = fr.get("findings", [])
            findings_count = fr.get("findings_count", len(findings))
            file_label, _ = get_score_band(file_score)

            lines.append(f"### `{filename}`")
            lines.append(f"")
            lines.append(f"**Language:** {lang.capitalize()} | **Score:** {file_score:.1f}/100 ({file_label}) | **Findings:** {findings_count}")
            lines.append(f"")

            if findings:
                lines.append("| Severity | Line | Category | Issue |")
                lines.append("|----------|------|----------|-------|")
                for finding in findings:
                    sev = finding.get("severity", "suggestion").upper()
                    line_no = finding.get("line_number", "-") or "-"
                    category = finding.get("category", "").capitalize()
                    message = finding.get("message", "")[:80]
                    lines.append(f"| {sev} | {line_no} | {category} | {message} |")
                lines.append("")

                # Show code snippets for critical findings
                critical = [f for f in findings if f.get("severity") == "critical"]
                for finding in critical[:3]:
                    if finding.get("code_snippet"):
                        lines.append(f"**Critical at line {finding.get('line_number', '?')}:**")
                        lines.append(f"```")
                        lines.append(finding["code_snippet"])
                        lines.append(f"```")
                        if finding.get("suggestion"):
                            lines.append(f"> 💡 {finding['suggestion']}")
                        lines.append("")
            else:
                lines.append("✅ No issues found in this file.")
                lines.append("")

    # Findings by category
    all_findings: List[Dict] = []
    for fr in file_reviews:
        for finding in fr.get("findings", []):
            finding_with_file = dict(finding)
            finding_with_file["filename"] = fr.get("filename", "")
            all_findings.append(finding_with_file)

    if all_findings:
        by_category: Dict[str, List[Dict]] = {}
        for f in all_findings:
            cat = f.get("category", "other")
            by_category.setdefault(cat, []).append(f)

        lines.append("## Findings by Category")
        lines.append("")
        for category in ("bugs", "security", "performance", "architecture", "style"):
            cat_findings = by_category.get(category, [])
            if not cat_findings:
                continue
            emoji = {"bugs": "🐛", "security": "🔒", "performance": "⚡", "architecture": "🏗️", "style": "✨"}.get(category, "•")
            lines.append(f"### {emoji} {category.capitalize()} ({len(cat_findings)})")
            lines.append("")
            for f in sorted(cat_findings, key=lambda x: {"critical": 0, "warning": 1, "suggestion": 2}.get(x.get("severity", ""), 3)):
                sev = f.get("severity", "suggestion")
                badge = {"critical": "🔴", "warning": "🟡", "suggestion": "🔵"}.get(sev, "⚪")
                lines.append(f"- {badge} **{f['filename']}:{f.get('line_number', '?')}** — {f.get('message', '')}")
                if f.get("suggestion"):
                    lines.append(f"  - Fix: {f['suggestion']}")
            lines.append("")

    lines.append("---")
    lines.append("*Generated by [Code Review Assistant](https://github.com/your-org/code-review-assistant)*")

    return "\n".join(lines)


def generate_github_comment(review_data: Dict[str, Any]) -> str:
    """Generate a concise GitHub PR comment."""
    score = review_data.get("score", 0) or 0
    label, _ = get_score_band(score)
    score_emoji = "🟢" if score >= 90 else "🔵" if score >= 70 else "🟡" if score >= 40 else "🔴"

    lines: List[str] = [
        f"## {score_emoji} Code Review — {score:.1f}/100 ({label})",
        "",
        f"| Files | +Added | -Removed | 🔴 Critical | 🟡 Warning | 🔵 Suggestion |",
        f"|-------|--------|----------|-------------|------------|---------------|",
        f"| {review_data.get('files_changed', 0)} | "
        f"+{review_data.get('lines_added', 0)} | "
        f"-{review_data.get('lines_removed', 0)} | "
        f"{review_data.get('critical_count', 0)} | "
        f"{review_data.get('warning_count', 0)} | "
        f"{review_data.get('suggestion_count', 0)} |",
        "",
    ]

    if review_data.get("ai_summary"):
        lines.extend(["> " + review_data["ai_summary"], ""])

    # Top critical findings
    file_reviews = review_data.get("file_reviews", [])
    critical_findings: List[Dict] = []
    for fr in file_reviews:
        for finding in fr.get("findings", []):
            if finding.get("severity") == "critical":
                finding_copy = dict(finding)
                finding_copy["filename"] = fr.get("filename", "")
                critical_findings.append(finding_copy)

    if critical_findings:
        lines.append("<details>")
        lines.append(f"<summary>🔴 Critical Issues ({len(critical_findings)})</summary>")
        lines.append("")
        for f in critical_findings[:10]:
            lines.append(f"**`{f['filename']}`:{f.get('line_number', '?')}** — {f.get('message', '')}")
            if f.get("suggestion"):
                lines.append(f"> 💡 {f['suggestion']}")
            if f.get("code_snippet"):
                lines.append(f"```\n{f['code_snippet']}\n```")
            lines.append("")
        lines.append("</details>")
        lines.append("")

    # Per-file scores
    if file_reviews:
        lines.append("<details>")
        lines.append("<summary>📁 File Scores</summary>")
        lines.append("")
        lines.append("| File | Language | Score | Critical | Warnings |")
        lines.append("|------|----------|-------|----------|----------|")
        for fr in file_reviews:
            fr_score = fr.get("score", 100) or 100
            fr_label, _ = get_score_band(fr_score)
            findings = fr.get("findings", [])
            crit = sum(1 for f in findings if f.get("severity") == "critical")
            warn = sum(1 for f in findings if f.get("severity") == "warning")
            lines.append(
                f"| `{fr.get('filename', '')}` | {fr.get('language', '')} | "
                f"{fr_score:.1f} ({fr_label}) | {crit} | {warn} |"
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("---")
    lines.append("*🤖 Generated by Code Review Assistant*")

    return "\n".join(lines)


def generate_pdf_report(review_data: Dict[str, Any]) -> bytes:
    """Generate a PDF report using reportlab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=1 * inch,
            bottomMargin=1 * inch,
        )

        styles = getSampleStyleSheet()
        story: List[Any] = []

        # Title
        title_style = ParagraphStyle(
            "Title",
            parent=styles["Title"],
            fontSize=20,
            spaceAfter=12,
            textColor=colors.HexColor("#0f1117"),
        )
        h1_style = ParagraphStyle(
            "H1",
            parent=styles["Heading1"],
            fontSize=14,
            spaceAfter=8,
            textColor=colors.HexColor("#1a1d27"),
        )
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=10,
            spaceAfter=4,
        )
        code_style = ParagraphStyle(
            "Code",
            parent=styles["Code"],
            fontSize=8,
            fontName="Courier",
            backColor=colors.HexColor("#f8f9fa"),
            borderPadding=4,
        )

        score = review_data.get("score", 0) or 0
        label, color_hex = get_score_band(score)
        pr_title = review_data.get("pr_title", "Code Review Report")
        created_at = review_data.get("created_at", datetime.utcnow())

        story.append(Paragraph("Code Review Report", title_style))
        story.append(Paragraph(f"<b>{pr_title}</b>", h1_style))

        if isinstance(created_at, datetime):
            date_str = created_at.strftime("%Y-%m-%d %H:%M UTC")
        else:
            date_str = str(created_at)
        story.append(Paragraph(f"Generated: {date_str}", body_style))
        story.append(Spacer(1, 12))

        # Score
        score_color = colors.HexColor(color_hex)
        score_table_data = [
            ["Overall Score", f"{score:.1f}/100", label],
            ["Files Changed", str(review_data.get("files_changed", 0)), ""],
            ["Lines Added", f"+{review_data.get('lines_added', 0)}", ""],
            ["Lines Removed", f"-{review_data.get('lines_removed', 0)}", ""],
            ["Critical Issues", str(review_data.get("critical_count", 0)), ""],
            ["Warnings", str(review_data.get("warning_count", 0)), ""],
            ["Suggestions", str(review_data.get("suggestion_count", 0)), ""],
        ]
        score_table = Table(score_table_data, colWidths=[2.5 * inch, 1.5 * inch, 2 * inch])
        score_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), score_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
                ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(score_table)
        story.append(Spacer(1, 16))

        # AI Summary
        if review_data.get("ai_summary"):
            story.append(Paragraph("AI Analysis", h1_style))
            story.append(Paragraph(review_data["ai_summary"], body_style))
            story.append(Spacer(1, 12))

        # File breakdown
        file_reviews = review_data.get("file_reviews", [])
        if file_reviews:
            story.append(Paragraph("File Analysis", h1_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
            story.append(Spacer(1, 8))

            for fr in file_reviews:
                filename = fr.get("filename", "unknown")
                fr_score = fr.get("score", 100) or 100
                fr_label, fr_color = get_score_band(fr_score)
                findings = fr.get("findings", [])
                findings_count = len(findings)

                story.append(Paragraph(f"<b>{filename}</b>", h1_style))
                meta_data = [
                    ["Language", fr.get("language", "").capitalize(), "Score", f"{fr_score:.1f} ({fr_label})", "Findings", str(findings_count)],
                ]
                meta_table = Table(meta_data, colWidths=[1*inch, 1*inch, 0.75*inch, 1.5*inch, 0.75*inch, 0.75*inch])
                meta_table.setStyle(TableStyle([
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(meta_table)
                story.append(Spacer(1, 6))

                if findings:
                    findings_data = [["Sev", "Line", "Category", "Message"]]
                    for f in findings[:20]:
                        sev = f.get("severity", "suggestion").upper()
                        findings_data.append([
                            sev,
                            str(f.get("line_number", "-")),
                            f.get("category", "").capitalize(),
                            f.get("message", "")[:60],
                        ])
                    findings_table = Table(
                        findings_data,
                        colWidths=[0.8*inch, 0.5*inch, 1.1*inch, 4.3*inch],
                    )
                    sev_colors = {"CRITICAL": "#ef4444", "WARNING": "#fbbf24", "SUGGESTION": "#4f8cff"}
                    table_style = [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222733")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
                        ("PADDING", (0, 0), (-1, -1), 4),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
                    ]
                    # Color severity cells
                    for row_idx, row in enumerate(findings_data[1:], 1):
                        sev_val = row[0]
                        hex_c = sev_colors.get(sev_val, "#94a3b8")
                        table_style.append(("TEXTCOLOR", (0, row_idx), (0, row_idx), colors.HexColor(hex_c)))
                        table_style.append(("FONTNAME", (0, row_idx), (0, row_idx), "Helvetica-Bold"))
                    findings_table.setStyle(TableStyle(table_style))
                    story.append(findings_table)
                else:
                    story.append(Paragraph("✅ No issues found.", body_style))

                story.append(Spacer(1, 12))

        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
        story.append(Paragraph("Generated by Code Review Assistant", body_style))

        doc.build(story)
        return buffer.getvalue()

    except ImportError:
        # Fallback: generate a simple text-based PDF-like bytes
        md = generate_markdown_report(review_data)
        return md.encode("utf-8")
