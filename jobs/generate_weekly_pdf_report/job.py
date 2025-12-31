import os, json
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table
from reportlab.lib.styles import getSampleStyleSheet

def run(ctx):
    report_path = "reports/weekly_report.pdf"
    styles = getSampleStyleSheet()
    elements = [Paragraph("Weekly Job Platform Report", styles["Title"])]

    data = [["Job", "Runs", "Success", "Errors"]]

    for job in os.listdir("jobs"):
        stats_path = f"jobs/{job}/stats.json"
        if os.path.exists(stats_path):
            with open(stats_path) as f:
                s = json.load(f)
                data.append([job, s.get("runs"), s.get("success"), s.get("errors")])

    elements.append(Table(data))
    SimpleDocTemplate(report_path).build(elements)
    ctx.log(f"Weekly PDF report generated: {report_path}")
