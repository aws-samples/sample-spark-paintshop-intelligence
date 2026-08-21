"""Generate the SPARK end-to-end flow diagram as a clean line flowchart PNG."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1500, 600
img = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(img)

# ── Fonts ────────────────────────────────────────────────────────────────────
def font(size, bold=False):
    for path in [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else '-Regular'}.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

F_TITLE = font(15, bold=True)
F_LABEL = font(11, bold=True)
F_BODY  = font(10)
F_SMALL = font(9)

BLACK  = "#000000"
GRAY   = "#555555"
LGRAY  = "#aaaaaa"
WHITE  = "#ffffff"
BORDER = "#222222"

# ── Helpers ──────────────────────────────────────────────────────────────────
def rect(x, y, w, h, fill=WHITE, outline=BORDER, lw=2):
    draw.rectangle([x, y, x+w, y+h], fill=fill, outline=outline, width=lw)

def ctext(text, cx, y, f=F_BODY, color=BLACK):
    bb = draw.textbbox((0,0), text, font=f)
    draw.text((cx - (bb[2]-bb[0])//2, y), text, font=f, fill=color)

def ltext(lines, cx, y, f=F_BODY, color=GRAY, lh=14):
    for l in lines:
        ctext(l, cx, y, f, color)
        y += lh

def arrow_right(x1, y, x2):
    draw.line([(x1, y), (x2-8, y)], fill=BLACK, width=2)
    draw.polygon([(x2, y), (x2-10, y-5), (x2-10, y+5)], fill=BLACK)

def arrow_down(x, y1, y2):
    draw.line([(x, y1), (x, y2-8)], fill=BLACK, width=2)
    draw.polygon([(x, y2), (x-5, y2-10), (x+5, y2-10)], fill=BLACK)

def arrow_down_gray(x, y1, y2):
    draw.line([(x, y1), (x, y2-8)], fill=LGRAY, width=1)
    draw.polygon([(x, y2), (x-4, y2-8), (x+4, y2-8)], fill=LGRAY)

# ── Title ────────────────────────────────────────────────────────────────────
ctext("SPARK — End-to-End Flow", W//2, 18, F_TITLE, BLACK)

# ── Layout ───────────────────────────────────────────────────────────────────
# Main row: 7 boxes left-to-right
# Box dimensions
BW = 155   # box width
BH = 90    # box height
BY = 80    # top y of main row
GAP = 30   # gap between boxes

# X centres for 7 boxes across ~1480px
#  1: Simulator   2: Kinesis    3: SageMaker   4: EventBridge
#  5: Step Fn     6a: MPS Agent 6b: RCA Agent  7: Output
xs = [90, 280, 470, 660, 850, 1100, 1350]

# Box definitions: (cx, label line1, label line2, detail lines)
boxes = [
    (xs[0], "IoT Simulator",      "Lambda",             ["EventBridge rule", "10s interval", "Sensor readings"]),
    (xs[1], "Kinesis + Lambda",   "Ingestion",          ["Data Streams", "Stream Processor", "DynamoDB write"]),
    (xs[2], "SageMaker",          "ML Detection",       ["Isolation Forest", "LSTM Autoencoder", "XGBoost Classifier"]),
    (xs[3], "EventBridge",        "Anomaly Rule",       ["Score threshold", "Fires on anomaly", "→ Step Functions"]),
    (xs[4], "Step Functions",     "Orchestration",      ["Parallel branches", "MPS + RCA", "~55s total"]),
]

# Output box
out_cx = xs[6]

# Agent boxes (parallel, stacked to right of Step Functions)
agent_top_cx = xs[5]
agent_top_by = BY
agent_bot_by = BY + BH + 40

# ── Draw main boxes 1-5 ──────────────────────────────────────────────────────
for (cx, l1, l2, details) in boxes:
    x = cx - BW//2
    rect(x, BY, BW, BH)
    ctext(l1, cx, BY + 8,  F_LABEL, BLACK)
    ctext(l2, cx, BY + 24, F_BODY,  GRAY)
    draw.line([(x+8, BY+40), (x+BW-8, BY+40)], fill=LGRAY, width=1)
    ltext(details, cx, BY+46, F_SMALL, GRAY, lh=13)

# ── Draw agent boxes ─────────────────────────────────────────────────────────
for (by, l1, l2, details) in [
    (agent_top_by, "MPS Agent",   "Bedrock AgentCore", ["Reschedule jobs", "Reroute / hold", "Apply schedule"]),
    (agent_bot_by, "RCA Agent",   "Bedrock AgentCore", ["Sensor history", "Neptune KB lookup", "RCA report"]),
]:
    x = agent_top_cx - BW//2
    rect(x, by, BW, BH)
    ctext(l1, agent_top_cx, by + 8,  F_LABEL, BLACK)
    ctext(l2, agent_top_cx, by + 24, F_BODY,  GRAY)
    draw.line([(x+8, by+40), (x+BW-8, by+40)], fill=LGRAY, width=1)
    ltext(details, agent_top_cx, by+46, F_SMALL, GRAY, lh=13)

# ── Draw output box ───────────────────────────────────────────────────────────
out_mid_y = BY + BH//2 + 20   # vertically centred between two agent boxes
out_by    = out_mid_y - BH//2
rect(out_cx - BW//2, out_by, BW, BH)
ctext("Dashboard",       out_cx, out_by + 8,  F_LABEL, BLACK)
ctext("React + WebSocket", out_cx, out_by + 24, F_BODY, GRAY)
draw.line([(out_cx-BW//2+8, out_by+40), (out_cx+BW//2-8, out_by+40)], fill=LGRAY, width=1)
ltext(["Incident card", "RCA report", "Production schedule"], out_cx, out_by+46, F_SMALL, GRAY, lh=13)

# ── Arrows: boxes 1→2→3→4→5 ─────────────────────────────────────────────────
for i in range(len(boxes)-1):
    cx_left  = boxes[i][0]
    cx_right = boxes[i+1][0]
    arrow_right(cx_left + BW//2, BY + BH//2, cx_right - BW//2)

# ── Arrow: Step Functions → MPS Agent (horizontal) ───────────────────────────
sfn_cx = xs[4]
arrow_right(sfn_cx + BW//2, BY + BH//2, agent_top_cx - BW//2)

# ── Arrow: Step Functions → RCA Agent (down then right) ──────────────────────
# Go down from bottom of Step Functions box, then right to RCA Agent
sfn_bot_x = sfn_cx
sfn_bot_y = BY + BH
rca_mid_y = agent_bot_by + BH//2
rca_left_x = agent_top_cx - BW//2

# vertical leg
draw.line([(sfn_bot_x, sfn_bot_y), (sfn_bot_x, rca_mid_y)], fill=BLACK, width=2)
# horizontal leg with arrowhead
arrow_right(sfn_bot_x, rca_mid_y, rca_left_x)

# ── Arrows: MPS → Output, RCA → Output ───────────────────────────────────────
mps_mid_y = agent_top_by + BH//2
rca_mid_y2 = agent_bot_by + BH//2

# MPS → Output
draw.line([(agent_top_cx + BW//2, mps_mid_y), (out_cx - BW//2, out_mid_y - 12)], fill=BLACK, width=2)
draw.polygon([
    (out_cx - BW//2, out_mid_y - 12),
    (out_cx - BW//2 - 10, out_mid_y - 18),
    (out_cx - BW//2 - 10, out_mid_y - 6),
], fill=BLACK)

# RCA → Output
draw.line([(agent_top_cx + BW//2, rca_mid_y2), (out_cx - BW//2, out_mid_y + 12)], fill=BLACK, width=2)
draw.polygon([
    (out_cx - BW//2, out_mid_y + 12),
    (out_cx - BW//2 - 10, out_mid_y + 6),
    (out_cx - BW//2 - 10, out_mid_y + 18),
], fill=BLACK)

# ── Step labels below arrows (1→2, 2→3, etc.) ────────────────────────────────
labels_between = [
    ((xs[0]+xs[1])//2, "sensor data"),
    ((xs[1]+xs[2])//2, "readings"),
    ((xs[2]+xs[3])//2, "anomaly score"),
    ((xs[3]+xs[4])//2, "event trigger"),
    ((xs[4]+xs[5])//2, "parallel invoke"),
]
for (cx, lbl) in labels_between:
    ctext(lbl, cx, BY + BH//2 + 6, F_SMALL, LGRAY)

# ── Phase numbers ─────────────────────────────────────────────────────────────
phases = [
    (xs[0], "①"),
    (xs[1], "②"),
    (xs[2], "③"),
    (xs[3], "④"),
    (xs[4], "⑤"),
    (xs[5], "⑥a"),
    (agent_top_cx, "⑥b"),
    (out_cx, "⑦"),
]
# Draw phase numbers above each box
for i, (cx, num) in enumerate([(xs[0],"1"),(xs[1],"2"),(xs[2],"3"),(xs[3],"4"),(xs[4],"5")]):
    ctext(num, cx, BY - 18, F_SMALL, LGRAY)
for (cx, num, by2) in [(agent_top_cx,"6a",agent_top_by),(agent_top_cx,"6b",agent_bot_by),(out_cx,"7",out_by)]:
    ctext(num, cx, by2 - 18, F_SMALL, LGRAY)

# ── Supporting infra row ──────────────────────────────────────────────────────
INF_Y  = agent_bot_by + BH + 55
INF_BW = 170
INF_BH = 52
infra = [
    ("Neptune Graph DB",   "Fault history · tank graph"),
    ("Bedrock KB",         "29 SOP docs · OpenSearch AOSS"),
    ("DynamoDB",           "Jobs · incidents · RCA reports"),
    ("SSM Param Store",    "Agent ARNs · config"),
    ("CloudWatch",         "Metrics · logs · monitoring"),
]
total_w = len(infra) * INF_BW + (len(infra)-1) * 20
start_x = (W - total_w) // 2
draw.line([(60, INF_Y - 22), (W-60, INF_Y - 22)], fill=LGRAY, width=1)
ctext("Supporting Infrastructure", W//2, INF_Y - 18, F_SMALL, LGRAY)
for i, (name, detail) in enumerate(infra):
    ix = start_x + i * (INF_BW + 20)
    rect(ix, INF_Y, INF_BW, INF_BH, outline=LGRAY, lw=1)
    ctext(name,   ix + INF_BW//2, INF_Y + 8,  F_SMALL, BLACK)
    ctext(detail, ix + INF_BW//2, INF_Y + 26, F_SMALL, GRAY)

    # dashed connector from nearest main box to infra box
    near_cx = min([(abs(b[0] - (ix + INF_BW//2)), b[0]) for b in boxes + [(agent_top_cx,),(out_cx,)]], key=lambda t: t[0])[1]
    infra_top_x = ix + INF_BW//2

# ── Legend ────────────────────────────────────────────────────────────────────
leg_y = H - 30
draw.text((40, leg_y), "Boxes = AWS services   Arrows = data / event flow   Parallel branch: MPS (rescheduling) and RCA (root cause) run simultaneously", font=F_SMALL, fill=LGRAY)

out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "e2e_flow.png"))
img.save(out_path, "PNG")
print(f"Saved: {out_path}  ({W}x{H})")
