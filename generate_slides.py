"""
Script tạo bộ Slide thuyết trình PowerPoint 16:9 (20 slide) đồng bộ Design System
Đỏ nhận diện (#C62828) – Xanh dương nhạt (#DCEBFA) – Xanh dương đậm (#245A85).
Xuất trực tiếp:
  - BAO_CAO_DO_AN.pptx (OpenXML 16:9 chuẩn Microsoft PowerPoint)
  - SLIDE_THUYET_TRINH.pdf (thông qua PowerPoint COM nếu có cài Office)
"""

import os
import sqlite3
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "slide_assets"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
ASSETS_DIR.mkdir(exist_ok=True)
SCREENSHOTS_DIR.mkdir(exist_ok=True)

PPTX_PATH = BASE_DIR / "BAO_CAO_DO_AN.pptx"
PDF_PATH = BASE_DIR / "SLIDE_THUYET_TRINH.pdf"

# Bộ màu chuẩn Design System
RED = "C62828"
RED_LIGHT = "FCE8E8"
BLUE_LIGHT = "DCEBFA"
BLUE_SOFT = "EFF6FD"
BLUE_DARK = "245A85"
TEXT_MAIN = "263445"
TEXT_MUTED = "718096"
BORDER = "D5E2EE"
WHITE = "FFFFFF"
SUCCESS = "27865B"
WARNING = "D69E2E"

# Kích thước Slide 16:9 tính theo EMU (1 inch = 914400 EMU; 13.333 x 7.5 in)
SLIDE_W = 12192000
SLIDE_H = 6858000
EMU_PER_INCH = 914400


def inch(v: float) -> int:
    return int(round(v * EMU_PER_INCH))


# ==============================================================================
# 1. VẼ SƠ ĐỒ & BIỂU ĐỒ CHẤT LƯỢNG CAO (300 DPI)
# ==============================================================================
def generate_diagrams() -> dict:
    plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    paths = {}

    # --- 1. Use Case Diagram (Slide 5) ---
    fig, ax = plt.subplots(figsize=(10.5, 5.2), dpi=220)
    ax.set_xlim(0, 10.5)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    fig.patch.set_facecolor("#FFFFFF")

    # System boundary
    ax.add_patch(FancyBboxPatch((2.6, 0.25), 5.3, 4.7, boxstyle="round,pad=0.08",
                                facecolor="#F5F9FE", edgecolor="#245A85", linewidth=1.8))
    ax.text(5.25, 4.72, "HỆ THỐNG QUẢN LÝ SINH VIÊN & ĐÀO TẠO", ha="center", va="center",
            fontsize=11, fontweight="bold", color="#245A85")

    actors = [
        (0.25, 3.65, "Phòng Đào tạo\n(ADMIN)", "#FCE8E8", "#C62828"),
        (0.25, 2.05, "Giảng viên\n(LECTURER)", "#DCEBFA", "#245A85"),
        (0.25, 0.50, "Sinh viên\n(STUDENT)", "#E7F6EE", "#27865B"),
    ]
    for x, y, lbl, fc, ec in actors:
        ax.add_patch(FancyBboxPatch((x, y), 1.85, 0.95, boxstyle="round,pad=0.06",
                                    facecolor=fc, edgecolor=ec, linewidth=1.8))
        ax.text(x + 0.925, y + 0.475, lbl, ha="center", va="center", fontsize=9.5,
                fontweight="bold", color=ec)

    usecases = [
        (3.0, 4.05, "Đăng nhập & Phân quyền 3 đối tượng"),
        (3.0, 3.35, "Quản lý Sinh viên, Lớp học, Học phần"),
        (3.0, 2.65, "Quản lý Chương trình đào tạo & Mở LHP"),
        (3.0, 1.95, "Nhập / Cập nhật Điểm & Tính hệ 4"),
        (3.0, 1.25, "Đăng ký Học phần & Kiểm tra tiên quyết"),
        (3.0, 0.55, "Tra cứu GPA (10/4) & Cảnh báo học vụ"),
    ]
    for x, y, lbl in usecases:
        ax.add_patch(FancyBboxPatch((x, y), 4.5, 0.52, boxstyle="round,pad=0.04",
                                    facecolor="#FFFFFF", edgecolor="#245A85", linewidth=1.2))
        ax.text(x + 2.25, y + 0.26, lbl, ha="center", va="center", fontsize=9, color="#263445", fontweight="bold")

    # Connections
    links = [
        ((2.1, 4.15), (3.0, 4.30), "#C62828"),
        ((2.1, 4.15), (3.0, 3.60), "#C62828"),
        ((2.1, 4.15), (3.0, 2.90), "#C62828"),
        ((2.1, 4.15), (3.0, 2.20), "#C62828"),
        ((2.1, 2.52), (3.0, 4.30), "#245A85"),
        ((2.1, 2.52), (3.0, 2.20), "#245A85"),
        ((2.1, 2.52), (3.0, 0.80), "#245A85"),
        ((2.1, 0.97), (3.0, 4.30), "#27865B"),
        ((2.1, 0.97), (3.0, 1.50), "#27865B"),
        ((2.1, 0.97), (3.0, 0.80), "#27865B"),
    ]
    for (x1, y1), (x2, y2), col in links:
        ax.plot([x1, x2], [y1, y2], color=col, linewidth=1.2, alpha=0.8)

    # Legend box on right
    ax.add_patch(FancyBboxPatch((8.2, 1.0), 2.1, 3.3, boxstyle="round,pad=0.08",
                                facecolor="#FFFFFF", edgecolor="#E3E9F0", linewidth=1.3))
    ax.text(9.25, 4.02, "BẢO MẬT RBAC", ha="center", fontsize=9.5, fontweight="bold", color="#C62828")
    ax.text(8.35, 3.55, "• Xác thực Bearer Token\n• Ẩn menu theo vai trò\n• Backend kiểm tra 403\n• SV chỉ xem dữ liệu\n  của chính mình\n• GV nhập điểm lớp\n  được phân công",
            va="top", fontsize=8.3, color="#263445", linespacing=1.45)

    p_uc = ASSETS_DIR / "usecase_diagram.png"
    plt.tight_layout(pad=0.2)
    plt.savefig(p_uc, dpi=220, facecolor="#FFFFFF")
    plt.close(fig)
    paths["usecase"] = p_uc

    # --- 2. ERD Diagram (Slide 7) ---
    fig, ax = plt.subplots(figsize=(11.2, 5.1), dpi=220)
    ax.set_xlim(0, 11.2)
    ax.set_ylim(0, 5.1)
    ax.axis("off")
    fig.patch.set_facecolor("#FFFFFF")

    def draw_entity(x, y, w, h, title, header_col, fields):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04",
                                    facecolor="#FFFFFF", edgecolor=header_col, linewidth=1.6))
        ax.add_patch(FancyBboxPatch((x, y + h - 0.42), w, 0.42, boxstyle="round,pad=0.02",
                                    facecolor=header_col, edgecolor=header_col, linewidth=1.0))
        ax.text(x + w / 2, y + h - 0.21, title, ha="center", va="center",
                fontsize=9.2, fontweight="bold", color="#FFFFFF")
        fy = y + h - 0.62
        for f in fields:
            ax.text(x + 0.12, fy, f, ha="left", va="center", fontsize=7.8, color="#263445", family="Arial")
            fy -= 0.26

    draw_entity(0.2, 2.75, 2.55, 2.1, "dbo.classes (Lớp học)", "#245A85",
                ["PK  id (INT IDENTITY)", "UK  class_code", "    class_name", "    academic_year", "    homeroom_teacher"])
    draw_entity(3.4, 2.50, 2.75, 2.35, "dbo.students (Sinh viên)", "#C62828",
                ["PK  id (INT IDENTITY)", "UK  student_code", "    full_name, gender", "    date_of_birth", "UK  email, hometown", "FK  class_id -> classes"])
    draw_entity(6.9, 2.60, 2.75, 2.25, "dbo.scores (Điểm thi)", "#C62828",
                ["PK  id (INT IDENTITY)", "FK  student_id -> students", "FK  subject_id -> subjects", "UQ  semester (Bộ 3 duy nhất)", "    process_score (40%)", "    exam_score (60%) / final"])
    draw_entity(6.9, 0.25, 2.75, 1.85, "dbo.subjects (Học phần)", "#245A85",
                ["PK  id (INT IDENTITY)", "UK  subject_code", "    subject_name", "    credits (CHECK 1..15)", "    department"])
    draw_entity(0.2, 0.25, 2.55, 1.85, "app_accounts (3 Đối tượng)", "#27865B",
                ["PK  id, UK username", "    password_hash (PBKDF2)", "    role (ADMIN/LECT/STU)", "FK  student_id (nullable)", "    assigned_classes, active"])
    draw_entity(3.4, 0.25, 2.75, 1.85, "sections & enrollments", "#D69E2E",
                ["PK  section_id / enroll_id", "FK  subject_id, student_id", "    semester, schedule, room", "    max_capacity, prereq", "UQ  (student_id, section_id)"])

    # Relationship lines + cardinality
    ax.annotate("", xy=(3.4, 3.8), xytext=(2.75, 3.8), arrowprops=dict(arrowstyle="->", color="#245A85", lw=1.8))
    ax.text(3.07, 3.98, "1 : N", ha="center", fontsize=8.5, fontweight="bold", color="#245A85")

    ax.annotate("", xy=(6.9, 3.8), xytext=(6.15, 3.8), arrowprops=dict(arrowstyle="->", color="#C62828", lw=1.8))
    ax.text(6.52, 3.98, "1 : N", ha="center", fontsize=8.5, fontweight="bold", color="#C62828")

    ax.annotate("", xy=(8.25, 2.6), xytext=(8.25, 2.1), arrowprops=dict(arrowstyle="->", color="#245A85", lw=1.8))
    ax.text(8.62, 2.35, "1 : N", ha="center", fontsize=8.5, fontweight="bold", color="#245A85")

    ax.annotate("", xy=(4.75, 2.1), xytext=(4.75, 2.5), arrowprops=dict(arrowstyle="<-", color="#D69E2E", lw=1.5))
    ax.annotate("", xy=(6.9, 1.15), xytext=(6.15, 1.15), arrowprops=dict(arrowstyle="<-", color="#D69E2E", lw=1.5))
    ax.annotate("", xy=(3.4, 3.05), xytext=(2.75, 1.45), arrowprops=dict(arrowstyle="->", color="#27865B", lw=1.3, ls="--"))

    # Legend
    ax.text(10.0, 4.5, "Phân nhóm bảng:", fontsize=8.5, fontweight="bold", color="#263445")
    for idx, (col, lbl) in enumerate([("#C62828", "Học vụ & Điểm"), ("#245A85", "Danh mục Đào tạo"),
                                      ("#D69E2E", "ĐKHP & CTĐT"), ("#27865B", "Xác thực 3 vai trò")]):
        yy = 4.1 - idx * 0.42
        ax.add_patch(FancyBboxPatch((9.95, yy), 0.22, 0.22, boxstyle="round,pad=0.02", facecolor=col, edgecolor=col))
        ax.text(10.25, yy + 0.11, lbl, va="center", fontsize=7.8, color="#263445")

    p_erd = ASSETS_DIR / "erd_diagram.png"
    plt.tight_layout(pad=0.15)
    plt.savefig(p_erd, dpi=220, facecolor="#FFFFFF")
    plt.close(fig)
    paths["erd"] = p_erd

    # --- 3. Architecture Diagram (Slide 12) ---
    fig, ax = plt.subplots(figsize=(11.0, 4.6), dpi=220)
    ax.set_xlim(0, 11.0)
    ax.set_ylim(0, 4.6)
    ax.axis("off")
    fig.patch.set_facecolor("#FFFFFF")

    boxes = [
        (0.3, 1.0, 3.0, 2.9, "TẦNG GIAO DIỆN (FRONTEND)", "#DCEBFA", "#245A85",
         "• SPA HTML5 / CSS3 / JS Fetch\n• Cổng Đăng nhập 3 Đối tượng\n• Sidebar cố định bên trái\n• Responsive Desktop/Mobile\n• Bộ màu #C62828 & #DCEBFA\n• Biểu đồ GPA & Cảnh báo"),
        (4.0, 1.0, 3.1, 2.9, "TẦNG API BACKEND (FASTAPI)", "#FCE8E8", "#C62828",
         "• Python FastAPI + Uvicorn\n• Pydantic v2 Validation (422)\n• Auth PBKDF2 + Bearer Token\n• RBAC Guard 3 Vai trò (403)\n• Tính GPA hệ 10/4 & Cảnh báo\n• OpenAPI Swagger UI (/docs)"),
        (7.8, 1.0, 2.9, 2.9, "TẦNG CƠ SỞ DỮ LIỆU", "#E7F6EE", "#27865B",
         "• Microsoft SQL Server (SSMS 22)\n• 4 bảng chuẩn 3NF + bảng mở rộng\n• 5 Stored Procedures\n• 4 User-Defined Functions\n• 4 Multi-row DML Triggers\n• 3 Transactions (COMMIT/ROLLBACK)"),
    ]
    for x, y, w, h, title, fc, ec, body in boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.06", facecolor=fc, edgecolor=ec, linewidth=2))
        ax.add_patch(FancyBboxPatch((x, y + h - 0.52), w, 0.52, boxstyle="round,pad=0.02", facecolor=ec, edgecolor=ec))
        ax.text(x + w / 2, y + h - 0.26, title, ha="center", va="center", fontsize=8.8, fontweight="bold", color="#FFFFFF")
        ax.text(x + 0.16, y + h - 0.72, body, va="top", fontsize=8.4, color="#263445", linespacing=1.55)

    ax.annotate("", xy=(4.0, 2.55), xytext=(3.3, 2.55), arrowprops=dict(arrowstyle="<->", color="#245A85", lw=2.2))
    ax.text(3.65, 2.85, "REST JSON\nBearer JWT", ha="center", fontsize=7.6, fontweight="bold", color="#245A85")

    ax.annotate("", xy=(7.8, 2.55), xytext=(7.1, 2.55), arrowprops=dict(arrowstyle="<->", color="#C62828", lw=2.2))
    ax.text(7.45, 2.85, "ODBC / SQL\nSync Engine", ha="center", fontsize=7.6, fontweight="bold", color="#C62828")

    ax.add_patch(FancyBboxPatch((0.3, 0.15), 10.4, 0.58, boxstyle="round,pad=0.04",
                                facecolor="#F5F7FA", edgecolor="#E3E9F0", linewidth=1.2))
    ax.text(5.5, 0.44, "Luồng bảo mật: Người dùng đăng nhập -> Nhận Token -> Mọi API kiểm tra quyền theo vai trò -> Thực thi ràng buộc PK / FK / UNIQUE / CHECK / Trigger",
            ha="center", va="center", fontsize=8.3, fontweight="bold", color="#263445")

    p_arch = ASSETS_DIR / "architecture_diagram.png"
    plt.tight_layout(pad=0.15)
    plt.savefig(p_arch, dpi=220, facecolor="#FFFFFF")
    plt.close(fig)
    paths["arch"] = p_arch

    # --- 4. Real Data Chart from SQLite DB (Slide 15/16) ---
    db_path = BASE_DIR / "student_grade_local.db"
    dist_counts = [0, 0, 0, 0]
    class_labels, class_counts = [], []
    if db_path.exists():
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        dist_counts = [
            cur.execute("SELECT COUNT(*) FROM scores WHERE final_score >= 8.5").fetchone()[0],
            cur.execute("SELECT COUNT(*) FROM scores WHERE final_score >= 7.0 AND final_score < 8.5").fetchone()[0],
            cur.execute("SELECT COUNT(*) FROM scores WHERE final_score >= 5.5 AND final_score < 7.0").fetchone()[0],
            cur.execute("SELECT COUNT(*) FROM scores WHERE final_score < 5.5").fetchone()[0],
        ]
        for row in cur.execute("""
            SELECT c.class_code, COUNT(s.id)
            FROM classes c LEFT JOIN students s ON s.class_id = c.id
            GROUP BY c.id, c.class_code ORDER BY c.id
        """).fetchall():
            class_labels.append(row[0])
            class_counts.append(row[1])
        con.close()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 3.8), dpi=220)
    fig.patch.set_facecolor("#FFFFFF")

    labels1 = ["Giỏi (A)", "Khá (B/B+)", "TB (C/C+)", "Yếu/Kém (D/F)"]
    colors1 = ["#27865B", "#245A85", "#D69E2E", "#C62828"]
    bars1 = ax1.bar(labels1, dist_counts, color=colors1, width=0.55)
    ax1.set_title("Phân bố Kết quả Học tập (Dữ liệu thật)", fontsize=10, fontweight="bold", color="#263445", pad=10)
    ax1.set_ylabel("Số bản ghi điểm", fontsize=8.5, color="#718096")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.grid(axis="y", linestyle="--", alpha=0.35)
    for b in bars1:
        h = b.get_height()
        ax1.text(b.get_x() + b.get_width() / 2, h + 0.15, f"{int(h)}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    bars2 = ax2.bar(class_labels or ["CNTT01", "CNTT02"], class_counts or [3, 2], color="#245A85", width=0.52)
    ax2.set_title("Sinh viên theo Lớp / Chuyên ngành", fontsize=10, fontweight="bold", color="#263445", pad=10)
    ax2.set_ylabel("Số sinh viên", fontsize=8.5, color="#718096")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.grid(axis="y", linestyle="--", alpha=0.35)
    for b in bars2:
        h = b.get_height()
        ax2.text(b.get_x() + b.get_width() / 2, h + 0.08, f"{int(h)}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    p_chart = ASSETS_DIR / "stats_chart.png"
    plt.tight_layout(pad=0.8)
    plt.savefig(p_chart, dpi=220, facecolor="#FFFFFF")
    plt.close(fig)
    paths["chart"] = p_chart

    return paths


# ==============================================================================
# 2. ENGINE XUẤT PPTX THUẦN PYTHON (OPENXML 16:9 CHUẨN MICROSOFT POWERPOINT)
# ==============================================================================
class SlideBuilder:
    def __init__(self, slide_idx: int, total_slides: int, title: str, subtitle: str = "", is_cover: bool = False):
        self.slide_idx = slide_idx
        self.total_slides = total_slides
        self.title = title
        self.subtitle = subtitle
        self.is_cover = is_cover
        self.shapes: list[str] = []
        self.images: list[tuple[str, Path]] = []  # (rId, path)
        self._shape_id = 2

    def _next_id(self) -> int:
        sid = self._shape_id
        self._shape_id += 1
        return sid

    def add_rect(self, x: float, y: float, w: float, h: float, fill_hex: str, border_hex: str = None, radius: bool = False):
        sid = self._next_id()
        prst = "roundRect" if radius else "rect"
        ln = f'<a:ln w="12700"><a:solidFill><a:srgbClr val="{border_hex}"/></a:solidFill></a:ln>' if border_hex else '<a:ln><a:noFill/></a:ln>'
        self.shapes.append(f"""
        <p:sp>
          <p:nvSpPr><p:cNvPr id="{sid}" name="Rect {sid}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
          <p:spPr>
            <a:xfrm><a:off x="{inch(x)}" y="{inch(y)}"/><a:ext cx="{inch(w)}" cy="{inch(h)}"/></a:xfrm>
            <a:prstGeom prst="{prst}"><a:avLst/></a:prstGeom>
            <a:solidFill><a:srgbClr val="{fill_hex}"/></a:solidFill>
            {ln}
          </p:spPr>
        </p:sp>""")

    def add_text(self, x: float, y: float, w: float, h: float, lines: list,
                 font_size: int = 14, color: str = TEXT_MAIN, bold: bool = False,
                 align: str = "l", line_spacing: int = 120):
        sid = self._next_id()
        paras = []
        for item in lines:
            if isinstance(item, dict):
                txt = xml_escape(str(item.get("text", "")))
                sz = int(item.get("size", font_size) * 100)
                col = item.get("color", color)
                b_attr = ' b="1"' if item.get("bold", bold) else ""
                al = item.get("align", align)
                spc_after = int(item.get("space_after", 4) * 100)
            else:
                txt = xml_escape(str(item))
                sz = int(font_size * 100)
                col = color
                b_attr = ' b="1"' if bold else ""
                al = align
                spc_after = 400
            paras.append(f"""
            <a:p>
              <a:pPr algn="{al}"><a:lnSpc><a:spcPct val="{line_spacing * 1000}"/></a:lnSpc><a:spcAft><a:spcPts val="{spc_after}"/></a:spcAft></a:pPr>
              <a:r>
                <a:rPr lang="vi-VN" sz="{sz}"{b_attr} dirty="0">
                  <a:solidFill><a:srgbClr val="{col}"/></a:solidFill>
                  <a:latin typeface="Arial"/><a:ea typeface="Arial"/><a:cs typeface="Arial"/>
                </a:rPr>
                <a:t>{txt}</a:t>
              </a:r>
            </a:p>""")
        self.shapes.append(f"""
        <p:sp>
          <p:nvSpPr><p:cNvPr id="{sid}" name="Text {sid}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
          <p:spPr>
            <a:xfrm><a:off x="{inch(x)}" y="{inch(y)}"/><a:ext cx="{inch(w)}" cy="{inch(h)}"/></a:xfrm>
            <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
            <a:noFill/>
          </p:spPr>
          <p:txBody>
            <a:bodyPr wrap="square" lIns="72000" tIns="45000" rIns="72000" bIns="45000"/>
            <a:lstStyle/>
            {''.join(paras)}
          </p:txBody>
        </p:sp>""")

    def add_card(self, x: float, y: float, w: float, h: float, title: str, bullets: list[str],
                 accent: str = BLUE_DARK, fill: str = WHITE):
        self.add_rect(x, y, w, h, fill, BORDER, radius=True)
        self.add_rect(x, y, w, 0.08, accent)
        lines = [{"text": title, "size": 14, "bold": True, "color": accent, "space_after": 6}]
        for b in bullets:
            lines.append({"text": f"• {b}", "size": 12, "color": TEXT_MAIN, "space_after": 4})
        self.add_text(x + 0.14, y + 0.14, w - 0.28, h - 0.22, lines, line_spacing=118)

    def add_image_fit(self, x: float, y: float, max_w: float, max_h: float, img_path: Path, caption: str = ""):
        if not img_path.exists():
            # Placeholder minh bạch nếu chưa có ảnh chụp thực tế
            self.add_rect(x, y, max_w, max_h, BLUE_SOFT, BLUE_DARK, radius=True)
            self.add_text(x + 0.2, y + max_h / 2 - 0.4, max_w - 0.4, 0.9, [
                {"text": f"[Vị trí chèn ảnh thực tế: {img_path.name}]", "size": 13, "bold": True, "color": BLUE_DARK, "align": "ctr"},
                {"text": caption or "Chụp từ giao diện hệ thống đang chạy tại http://127.0.0.1:8000/", "size": 11, "color": TEXT_MUTED, "align": "ctr"},
            ])
            return

        with Image.open(img_path) as im:
            iw, ih = im.size
        ratio = min(max_w / iw, max_h / ih)
        w = iw * ratio
        h = ih * ratio
        cx = x + (max_w - w) / 2
        cy = y + (max_h - h) / 2

        rid = f"rIdImg{len(self.images) + 1}"
        self.images.append((rid, img_path))
        sid = self._next_id()
        # Subtle border frame behind image
        self.add_rect(cx - 0.03, cy - 0.03, w + 0.06, h + 0.06, WHITE, BORDER)
        self.shapes.append(f"""
        <p:pic>
          <p:nvPicPr>
            <p:cNvPr id="{sid}" name="{xml_escape(img_path.name)}"/>
            <p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>
            <p:nvPr/>
          </p:nvPicPr>
          <p:blipFill>
            <a:blip r:embed="{rid}"/>
            <a:stretch><a:fillRect/></a:stretch>
          </p:blipFill>
          <p:spPr>
            <a:xfrm><a:off x="{inch(cx)}" y="{inch(cy)}"/><a:ext cx="{inch(w)}" cy="{inch(h)}"/></a:xfrm>
            <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          </p:spPr>
        </p:pic>""")
        if caption:
            self.add_text(x, y + max_h + 0.04, max_w, 0.3, [
                {"text": caption, "size": 10.5, "color": TEXT_MUTED, "align": "ctr"}
            ])

    def add_chrome(self):
        if self.is_cover:
            return
        # Top subtle light-blue header strip + red accent bar
        self.add_rect(0, 0, 13.333, 0.96, BLUE_SOFT)
        self.add_rect(0, 0, 0.14, 0.96, RED)
        self.add_rect(0, 0.96, 13.333, 0.025, BORDER)
        self.add_text(0.35, 0.14, 10.8, 0.45, [
            {"text": self.title, "size": 21, "bold": True, "color": TEXT_MAIN, "space_after": 0}
        ])
        if self.subtitle:
            self.add_text(0.35, 0.56, 10.8, 0.32, [
                {"text": self.subtitle, "size": 11.5, "color": BLUE_DARK, "bold": True, "space_after": 0}
            ])
        # Badge corner
        self.add_rect(11.35, 0.24, 1.65, 0.44, RED, radius=True)
        self.add_text(11.35, 0.28, 1.65, 0.36, [
            {"text": f"SLIDE {self.slide_idx:02d}/{self.total_slides}", "size": 10.5, "bold": True, "color": WHITE, "align": "ctr"}
        ])
        # Footer line
        self.add_rect(0.35, 7.05, 12.63, 0.015, BORDER)
        self.add_text(0.35, 7.10, 9.8, 0.32, [
            {"text": "Đồ án Hệ quản trị CSDL — Hệ thống Quản lý Sinh viên và Đào tạo Đại học", "size": 9.5, "color": TEXT_MUTED}
        ])
        self.add_text(10.5, 7.10, 2.48, 0.32, [
            {"text": f"Trang {self.slide_idx} / {self.total_slides}", "size": 9.5, "bold": True, "color": BLUE_DARK, "align": "r"}
        ])

    def to_xml(self) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:bg><p:bgPr><a:solidFill><a:srgbClr val="{WHITE}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
      {''.join(self.shapes)}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""


def build_all_20_slides(diagrams: dict) -> list[SlideBuilder]:
    TOTAL = 20
    slides: list[SlideBuilder] = []

    def new_slide(idx, title, subtitle="", is_cover=False):
        s = SlideBuilder(idx, TOTAL, title, subtitle, is_cover=is_cover)
        s.add_chrome()
        slides.append(s)
        return s

    # --- SLIDE 1: TRANG BÌA ---
    s1 = new_slide(1, "Trang bìa", is_cover=True)
    s1.add_rect(0, 0, 4.3, 7.5, BLUE_LIGHT)
    s1.add_rect(0, 0, 0.22, 7.5, RED)
    s1.add_rect(4.3, 0, 0.03, 7.5, BORDER)
    # Left brand block
    s1.add_rect(0.55, 0.7, 1.35, 0.65, RED, radius=True)
    s1.add_text(0.55, 0.80, 1.35, 0.5, [{"text": "EDU", "size": 22, "bold": True, "color": WHITE, "align": "ctr"}])
    s1.add_text(0.55, 1.6, 3.45, 2.2, [
        {"text": "BÁO CÁO ĐỒ ÁN MÔN HỌC", "size": 12.5, "bold": True, "color": RED, "space_after": 8},
        {"text": "HỌC PHẦN:\nHệ quản trị Cơ sở dữ liệu\n& Phát triển Ứng dụng Web", "size": 14, "bold": True, "color": BLUE_DARK, "space_after": 12},
        {"text": "Trường Đại học / Khoa CNTT\n(Cập nhật tên trường của nhóm)", "size": 11.5, "color": TEXT_MUTED},
    ])
    s1.add_rect(0.55, 5.45, 3.35, 1.45, WHITE, BORDER, radius=True)
    s1.add_text(0.72, 5.58, 3.0, 1.25, [
        {"text": "CÔNG NGHỆ TRIỂN KHAI", "size": 10.5, "bold": True, "color": RED, "space_after": 6},
        {"text": "• Web SPA (Sidebar trái + RBAC)\n• FastAPI + Pydantic Validation\n• Microsoft SQL Server (SSMS 22)", "size": 10.5, "color": TEXT_MAIN},
    ])
    # Right title block
    s1.add_text(4.75, 0.95, 8.1, 2.4, [
        {"text": "ĐỀ TÀI BẢO VỆ ĐỒ ÁN", "size": 12, "bold": True, "color": BLUE_DARK, "space_after": 8},
        {"text": "HỆ THỐNG QUẢN LÝ SINH VIÊN\nVÀ ĐÀO TẠO ĐẠI HỌC", "size": 30, "bold": True, "color": TEXT_MAIN, "space_after": 10},
        {"text": "Thiết kế CSDL chuẩn 3NF, T-SQL nâng cao, Phân quyền 3 đối tượng & Giao diện chuẩn đại học", "size": 13.5, "color": TEXT_MUTED},
    ])
    s1.add_rect(4.75, 3.65, 8.0, 0.05, RED)
    s1.add_text(4.75, 3.9, 8.0, 2.9, [
        {"text": "Giảng viên hướng dẫn:  [Họ tên Giảng viên hướng dẫn]", "size": 13.5, "bold": True, "color": BLUE_DARK, "space_after": 10},
        {"text": "Nhóm thực hiện (5 thành viên):", "size": 13, "bold": True, "color": TEXT_MAIN, "space_after": 6},
        {"text": "1. Thành viên 1 — Nhóm trưởng / Thiết kế CSDL & T-SQL", "size": 12, "color": TEXT_MAIN},
        {"text": "2. Thành viên 2 — Backend FastAPI & Phân quyền RBAC", "size": 12, "color": TEXT_MAIN},
        {"text": "3. Thành viên 3 — Giao diện Frontend & Design System", "size": 12, "color": TEXT_MAIN},
        {"text": "4. Thành viên 4 — Nghiệp vụ GPA, ĐKHP & Cảnh báo học vụ", "size": 12, "color": TEXT_MAIN},
        {"text": "5. Thành viên 5 — Kiểm thử tự động, Tài liệu & Báo cáo", "size": 12, "color": TEXT_MAIN},
    ])

    # --- SLIDE 2: TỔNG QUAN ĐỀ TÀI ---
    s2 = new_slide(2, "Tổng quan Đề tài", "Lý do chọn đề tài, bối cảnh chuyển đổi số giáo dục và bài toán đặt ra")
    s2.add_card(0.45, 1.25, 4.0, 5.4, "1. Bối cảnh Thực tiễn", [
        "Đào tạo tín chỉ tại đại học phát sinh khối lượng dữ liệu lớn: hồ sơ sinh viên, lớp, học phần, đăng ký và điểm thi.",
        "Quy trình thủ công bằng bảng tính rời rạc dễ sai sót công thức GPA và trùng lặp mã.",
        "Nhu cầu minh bạch dữ liệu theo thời gian thực cho 3 nhóm đối tượng: Phòng Đào tạo, Giảng viên và Sinh viên.",
    ], BLUE_DARK)
    s2.add_card(4.67, 1.25, 4.0, 5.4, "2. Vấn đề Cần giải quyết", [
        "Đảm bảo toàn vẹn tham chiếu PK / FK, chống trùng lặp dữ liệu học kỳ.",
        "Tự động hóa quy đổi điểm hệ 10 sang điểm chữ, điểm hệ 4 và phát hiện sớm cảnh báo học vụ.",
        "Kiểm soát phân quyền chặt chẽ giữa Admin, Giảng viên và Sinh viên trên cả UI và API.",
    ], RED)
    s2.add_card(8.89, 1.25, 4.0, 5.4, "3. Lý do Chọn Đề tài", [
        "Áp dụng trọn vẹn kiến thức Hệ quản trị CSDL: chuẩn hóa 3NF, Stored Procedure, UDF, Trigger và Transaction.",
        "Xây dựng sản phẩm Web hoàn chỉnh có API thật, dữ liệu thật và bộ kiểm thử tự động.",
        "Thiết kế giao diện đồng bộ nhận diện đại học, dễ mở rộng cho thực tế triển khai.",
    ], SUCCESS)

    # --- SLIDE 3: MỤC TIÊU HỆ THỐNG ---
    s3 = new_slide(3, "Mục tiêu của Hệ thống", "5 trụ cột nghiệp vụ cốt lõi trong quản lý sinh viên và đào tạo")
    goals = [
        ("01", "Quản lý Hồ sơ Sinh viên", "Lưu trữ đầy đủ thông tin cá nhân, lớp học, trạng thái học vụ, tìm kiếm đa tiêu chí và phân trang.", BLUE_DARK),
        ("02", "Chương trình Đào tạo", "Tổ chức học phần theo ngành/khóa, phân nhóm Bắt buộc – Tự chọn, tổng tín chỉ và môn tiên quyết.", BLUE_DARK),
        ("03", "Đăng ký Học phần", "Mở lớp học phần theo học kỳ, theo dõi sĩ số còn lại, tự động chặn nếu thiếu tiên quyết hoặc hết chỗ.", RED),
        ("04", "Tính Điểm & GPA (10/4)", "Tự động tính tổng kết (40% QT + 60% Thi), quy đổi điểm chữ, GPA học kỳ & tích lũy hệ 10 và hệ 4.", SUCCESS),
        ("05", "Cảnh báo Học vụ", "Tự động rà soát sinh viên GPA thấp / nợ tín chỉ theo Mức 1 – Mức 2 và theo dõi tiến độ tư vấn.", RED),
    ]
    positions = [(0.45, 1.3, 4.0, 2.55), (4.67, 1.3, 4.0, 2.55), (8.89, 1.3, 4.0, 2.55),
                 (1.6, 4.15, 4.8, 2.55), (6.9, 4.15, 4.8, 2.55)]
    for (num, ttl, desc, col), (x, y, w, h) in zip(goals, positions):
        s3.add_rect(x, y, w, h, WHITE, BORDER, radius=True)
        s3.add_rect(x + 0.18, y + 0.18, 0.58, 0.42, col, radius=True)
        s3.add_text(x + 0.18, y + 0.21, 0.58, 0.36, [{"text": num, "size": 13, "bold": True, "color": WHITE, "align": "ctr"}])
        s3.add_text(x + 0.88, y + 0.2, w - 1.05, 0.45, [{"text": ttl, "size": 14, "bold": True, "color": col}])
        s3.add_text(x + 0.18, y + 0.78, w - 0.36, h - 0.9, [{"text": desc, "size": 12, "color": TEXT_MAIN}], line_spacing=125)

    # --- SLIDE 4: PHẠM VI HỆ THỐNG ---
    s4 = new_slide(4, "Phạm vi Hệ thống & Phân quyền 3 Đối tượng", "Xác định rõ tác nhân sử dụng và 4 phân hệ nghiệp vụ chính")
    s4.add_card(0.45, 1.25, 4.0, 5.45, "Tác nhân 1: Phòng Đào tạo (ADMIN)", [
        "Quản trị toàn hệ thống: Lớp học, Khoa/Ngành, Học phần, Sinh viên.",
        "Xây dựng Chương trình đào tạo và mở Lớp học phần theo học kỳ.",
        "Quản lý toàn bộ bảng điểm, xét & xử lý Cảnh báo học vụ.",
        "Cấp phát, khóa/mở khóa tài khoản 3 đối tượng và cấu hình quy chế.",
    ], RED, WHITE)
    s4.add_card(4.67, 1.25, 4.0, 5.45, "Tác nhân 2: Giảng viên (LECTURER)", [
        "Xem danh sách sinh viên thuộc các lớp cố vấn / được phân công.",
        "Tra cứu Chương trình đào tạo và lịch giảng dạy lớp học phần.",
        "Nhập và cập nhật điểm quá trình (40%) – điểm thi (60%) theo quyền.",
        "Cập nhật trạng thái tư vấn cho sinh viên bị cảnh báo học vụ.",
        "Bị ẩn menu quản trị & chặn API 403 ngoài phạm vi.",
    ], BLUE_DARK, WHITE)
    s4.add_card(8.89, 1.25, 4.0, 5.45, "Tác nhân 3: Sinh viên (STUDENT)", [
        "Xem Dashboard học tập cá nhân: GPA hệ 10, hệ 4, tín chỉ tích lũy.",
        "Tra cứu khung Chương trình đào tạo ngành học.",
        "Đăng ký và hủy đăng ký học phần trực tuyến theo đợt.",
        "Xem bảng điểm chi tiết, biểu đồ tiến trình GPA và cảnh báo cá nhân.",
        "Không truy cập dữ liệu sinh viên khác (cô lập ở Backend).",
    ], SUCCESS, WHITE)

    # --- SLIDE 5: USE CASE TỔNG QUÁT ---
    s5 = new_slide(5, "Sơ đồ Use Case Tổng quát", "Mối quan hệ giữa 3 nhóm tác nhân và các nhóm chức năng nghiệp vụ")
    s5.add_image_fit(0.45, 1.18, 12.43, 5.55, diagrams["usecase"], "Hình 5.1 — Sơ đồ Use Case phân quyền 3 đối tượng (Admin / Giảng viên / Sinh viên)")

    # --- SLIDE 6: QUY TRÌNH NGHIỆP VỤ ---
    s6 = new_slide(6, "Quy trình Nghiệp vụ Đào tạo Khép kín", "5 giai đoạn liên thông dữ liệu từ nhập học đến xét cảnh báo học vụ")
    steps_biz = [
        ("Bước 1", "Hồ sơ Sinh viên", "Tiếp nhận SV mới, gán lớp hành chính, cấp tài khoản đăng nhập.", BLUE_DARK),
        ("Bước 2", "Chương trình ĐT", "Thiết lập khung học phần bắt buộc/tự chọn, tín chỉ và tiên quyết.", BLUE_DARK),
        ("Bước 3", "Đăng ký Học phần", "Mở LHP, SV đăng ký; hệ thống kiểm tra chỗ trống & môn tiên quyết.", RED),
        ("Bước 4", "Điểm & Kết quả", "GV nhập điểm 40/60; tự tính điểm chữ, GPA học kỳ & tích lũy (10/4).", SUCCESS),
        ("Bước 5", "Cảnh báo Học vụ", "Rà soát GPA < 2.0 hoặc nợ tín chỉ; phân mức 1–2 và theo dõi tư vấn.", RED),
    ]
    for i, (st, ttl, desc, col) in enumerate(steps_biz):
        x = 0.42 + i * 2.53
        s6.add_rect(x, 1.65, 2.32, 4.4, WHITE, BORDER, radius=True)
        s6.add_rect(x, 1.65, 2.32, 0.55, col, radius=True)
        s6.add_text(x, 1.74, 2.32, 0.4, [{"text": st, "size": 13, "bold": True, "color": WHITE, "align": "ctr"}])
        s6.add_text(x + 0.14, 2.4, 2.04, 0.65, [{"text": ttl, "size": 13.5, "bold": True, "color": TEXT_MAIN, "align": "ctr"}])
        s6.add_text(x + 0.14, 3.15, 2.04, 2.6, [{"text": desc, "size": 11.5, "color": TEXT_MUTED, "align": "ctr"}], line_spacing=128)
        if i < 4:
            s6.add_text(x + 2.30, 3.55, 0.25, 0.45, [{"text": "→", "size": 18, "bold": True, "color": RED, "align": "ctr"}])

    # --- SLIDE 7: SƠ ĐỒ ERD ---
    s7 = new_slide(7, "Sơ đồ Thực thể Kết hợp (ERD)", "Thiết kế cơ sở dữ liệu quan hệ phân nhóm rõ ràng theo màu sắc")
    s7.add_image_fit(0.45, 1.15, 12.43, 5.55, diagrams["erd"], "Hình 7.1 — Sơ đồ ERD tổng thể: 4 bảng lõi 3NF (classes, students, subjects, scores) và các bảng học vụ mở rộng")

    # --- SLIDE 8: MÔ HÌNH QUAN HỆ ---
    s8 = new_slide(8, "Mô hình Quan hệ & Toàn vẹn Khóa", "Lược đồ bảng chính, Khóa chính (PK), Khóa ngoại (FK) và Ràng buộc duy nhất (UQ)")
    s8.add_card(0.45, 1.22, 6.1, 2.6, "dbo.classes & dbo.students", [
        "CLASSES(PK id, UQ class_code, class_name, academic_year, homeroom_teacher)",
        "STUDENTS(PK id, UQ student_code, full_name, date_of_birth, gender, UQ email, hometown, FK class_id -> CLASSES.id)",
        "Quan hệ 1 : N — Chặn xóa lớp khi còn sinh viên thuộc lớp.",
    ], BLUE_DARK)
    s8.add_card(6.78, 1.22, 6.1, 2.6, "dbo.subjects & dbo.scores", [
        "SUBJECTS(PK id, UQ subject_code, subject_name, credits [1..15], department)",
        "SCORES(PK id, FK student_id, FK subject_id, semester, process_score, exam_score, final_score)",
        "Composite UNIQUE (student_id, subject_id, semester) chống nhập trùng điểm cùng kỳ.",
    ], RED)
    s8.add_card(0.45, 4.05, 6.1, 2.65, "Các bảng Học vụ Mở rộng", [
        "app_accounts: lưu tài khoản 3 đối tượng, mật khẩu băm PBKDF2-SHA256.",
        "curriculum_items: khung chương trình theo ngành/khóa, nhóm bắt buộc/tự chọn.",
        "course_sections & enrollments: lớp mở, sĩ số, tiên quyết, UQ(student_id, section_id).",
    ], SUCCESS)
    s8.add_card(6.78, 4.05, 6.1, 2.65, "Kiểm soát Toàn vẹn Dữ liệu", [
        "CHECK constraints: điểm [0.0..10.0], tín chỉ [1..15], giới tính, định dạng email.",
        "FOREIGN KEY chặn xóa Lớp/SV/Học phần khi còn dữ liệu phụ thuộc.",
        "Đồng bộ ràng buộc ở cả tầng SQL Server và tầng Pydantic API.",
    ], BLUE_DARK)

    # --- SLIDE 9: CHUẨN HÓA DỮ LIỆU ---
    s9 = new_slide(9, "Chuẩn hóa Cơ sở dữ liệu (1NF → 2NF → 3NF)", "Loại bỏ dư thừa dữ liệu và dị thường cập nhật trong lược đồ quan hệ")
    s9.add_card(0.45, 1.25, 4.0, 3.6, "Chuẩn 1NF (Nguyên tố)", [
        "Mọi cột trong 4 bảng lõi đều chứa giá trị đơn (atomic), không đa trị hay nhóm lặp.",
        "Mỗi bảng có khóa chính định danh duy nhất (IDENTITY(1,1)).",
        "Ví dụ: tách từng điểm theo học kỳ thành 1 dòng riêng trong bảng scores.",
    ], BLUE_DARK)
    s9.add_card(4.67, 1.25, 4.0, 3.6, "Chuẩn 2NF (Đầy đủ vào khóa)", [
        "Loại bỏ phụ thuộc hàm bộ phận trên khóa tổ hợp (student_id, subject_id, semester).",
        "Thông tin SV (full_name, class_id) tách riêng ở bảng students.",
        "Thông tin học phần (subject_name, credits) tách riêng ở bảng subjects.",
    ], BLUE_DARK)
    s9.add_card(8.89, 1.25, 4.0, 3.6, "Chuẩn 3NF (Không bắc cầu)", [
        "Loại bỏ phụ thuộc bắc cầu: student_id → class_id → class_name, homeroom_teacher.",
        "Bảng students chỉ lưu class_id tham chiếu sang bảng classes.",
        "Giảm dư thừa: sửa tên lớp / GVCN chỉ cần cập nhật 1 dòng duy nhất.",
    ], RED)
    s9.add_rect(0.45, 5.1, 12.44, 1.65, BLUE_SOFT, BLUE_DARK, radius=True)
    s9.add_text(0.65, 5.24, 12.0, 1.4, [
        {"text": "Ví dụ Minh họa Chuẩn hóa:", "size": 13, "bold": True, "color": RED, "space_after": 4},
        {"text": "Trước chuẩn hóa: BANG_DIEM(MaSV, TenSV, MaLop, TenLop, MaMon, TenMon, SoTC, HocKy, DiemQT, DiemThi)  → Dư thừa TenSV, TenLop, TenMon.", "size": 11.5, "color": TEXT_MAIN},
        {"text": "Sau đạt 3NF: Tách thành 4 bảng classes, students, subjects, scores liên kết khóa ngoại chặt chẽ, tối ưu toàn vẹn và truy vấn.", "size": 11.5, "bold": True, "color": BLUE_DARK},
    ])

    # --- SLIDE 10: SQL SERVER ---
    s10 = new_slide(10, "Triển khai Cơ sở dữ liệu trên SQL Server (SSMS 22)", "Cấu trúc 8 file script T-SQL chuẩn hóa, ràng buộc và truy vấn thống kê")
    s10.add_card(0.45, 1.25, 6.0, 5.4, "Bộ 8 Script T-SQL Tổ chức Khoa học", [
        "01_create_database.sql — Tạo DB StudentGradeManagementDB, READ_COMMITTED_SNAPSHOT ON.",
        "02_create_tables.sql — Tạo 4 bảng 3NF + PK, FK, UNIQUE, CHECK, DEFAULT.",
        "03_insert_sample_data.sql — Dữ liệu mẫu có tính liên kết đầy đủ.",
        "04_stored_procedures.sql — 5 Stored Procedures nghiệp vụ & báo cáo.",
        "05_functions.sql — 4 User-Defined Functions (Scalar & Table-Valued).",
        "06_triggers.sql — 4 DML Triggers xử lý đa dòng (inserted/deleted).",
        "07_transactions.sql — 3 Giao dịch nguyên tử COMMIT / ROLLBACK.",
        "08_test_database.sql — Bộ kiểm thử tự động 20 kịch bản (20/20 PASS).",
    ], BLUE_DARK)
    s10.add_card(6.75, 1.25, 6.1, 5.4, "Ràng buộc & Tối ưu Truy vấn", [
        "Khóa ngoại FK_students_classes, FK_scores_students, FK_scores_subjects bảo vệ tính nhất quán.",
        "CHECK constraints kiểm soát điểm [0.0–10.0], tín chỉ [1–15], ngày sinh và email ngay tại tầng DB.",
        "Chỉ mục NONCLUSTERED UNIQUE trên class_code, student_code, email, subject_code tăng tốc tìm kiếm.",
        "Hỗ trợ kiểm tra trực quan Database Diagram (ERD) trực tiếp trên SSMS 22.",
    ], RED)

    # --- SLIDE 11: SQL NÂNG CAO ---
    s11 = new_slide(11, "Lập trình T-SQL Nâng cao trên SQL Server", "Stored Procedure, User-Defined Function, Multi-row Trigger và Transaction")
    s11.add_card(0.45, 1.25, 6.05, 2.55, "5 Stored Procedures (04_stored_procedures.sql)", [
        "usp_UpsertStudentScore: Thêm/cập nhật điểm và tự tính tổng kết.",
        "usp_GetStudentTranscriptAndGPA: Xuất bảng điểm + GPA hệ 10 & hệ 4.",
        "usp_StatsByClass, usp_StatsBySubject, usp_SearchStudentsAdvanced.",
    ], BLUE_DARK)
    s11.add_card(6.8, 1.25, 6.08, 2.55, "4 User-Defined Functions (05_functions.sql)", [
        "ufn_CalculateFinalScore(QT, Thi): Tính 40% QT + 60% Thi.",
        "ufn_GetGradeClassification(score): Xếp loại học lực chuẩn.",
        "ufn_CalculateStudentGPA(id) & Inline TVF ufn_GetClassHonorRoll.",
    ], SUCCESS)
    s11.add_card(0.45, 4.05, 6.05, 2.65, "4 Multi-row DML Triggers (06_triggers.sql)", [
        "trg_Scores_ValidateAndSyncFinal: Xử lý đồng thời nhiều dòng inserted, tự đồng bộ final_score.",
        "3 INSTEAD OF DELETE Triggers chặn xóa lớp, sinh viên, môn học khi còn dữ liệu liên kết.",
    ], RED)
    s11.add_card(6.8, 4.05, 6.08, 2.65, "3 Transactions ACID (07_transactions.sql)", [
        "usp_Tran_RegisterStudentWithScores: Thêm SV + điểm đầu kỳ nguyên tử; tự ROLLBACK nếu điểm lỗi.",
        "usp_Tran_TransferStudentAndRecordScore & usp_Tran_DeleteStudentAndAllScores (TRY...CATCH + THROW).",
    ], WARNING)

    # --- SLIDE 12: KIẾN TRÚC HỆ THỐNG ---
    s12 = new_slide(12, "Kiến trúc Tổng thể Hệ thống", "Mô hình 3 tầng tách biệt: Giao diện Web Sidebar – FastAPI Backend – SQL Server")
    s12.add_image_fit(0.45, 1.22, 12.43, 5.45, diagrams["arch"], "Hình 12.1 — Kiến trúc kết nối RESTful API + Bảo mật phân quyền 3 đối tượng")

    # --- SLIDE 13: GIAO DIỆN DASHBOARD & ĐĂNG NHẬP 3 ĐỐI TƯỢNG ---
    s13 = new_slide(13, "Giao diện Đăng nhập 3 Đối tượng & Dashboard", "Ảnh chụp thực tế từ hệ thống đang chạy (bố cục Sidebar trái, màu #C62828 – #DCEBFA)")
    s13.add_image_fit(0.42, 1.22, 6.1, 5.15, SCREENSHOTS_DIR / "01_login_3_roles.png", "Hình 13.1 — Cổng đăng nhập bắt buộc quản lý 3 đối tượng")
    s13.add_image_fit(6.80, 1.22, 6.1, 5.15, SCREENSHOTS_DIR / "02_dashboard_admin.png", "Hình 13.2 — Dashboard tổng quan với Sidebar cố định bên trái")

    # --- SLIDE 14: CÁC PHÂN HỆ CHÍNH ---
    s14 = new_slide(14, "Các Phân hệ Quản lý Đào tạo Chính", "Quản lý Sinh viên, Chương trình Đào tạo và Đăng ký Học phần trực tuyến")
    s14.add_image_fit(0.42, 1.22, 6.1, 5.15, SCREENSHOTS_DIR / "03_students.png", "Hình 14.1 — Trang Quản lý Sinh viên (tìm kiếm, lọc, phân trang)")
    s14.add_image_fit(6.80, 1.22, 6.1, 5.15, SCREENSHOTS_DIR / "04_registration_student.png", "Hình 14.2 — Trang Đăng ký Học phần (góc nhìn Sinh viên, kiểm tra tiên quyết)")

    # --- SLIDE 15: KẾT QUẢ HỌC TẬP & GPA ---
    s15 = new_slide(15, "Kết quả Học tập & Thống kê GPA (Hệ 10 – Hệ 4)", "Theo dõi tiến trình học tập theo học kỳ và phân bố điểm thực tế")
    s15.add_image_fit(0.42, 1.22, 6.3, 5.15, SCREENSHOTS_DIR / "05_results_gpa.png", "Hình 15.1 — Bảng điểm chi tiết, GPA hệ 10 & hệ 4 thực tế")
    s15.add_image_fit(6.95, 1.22, 5.95, 5.15, diagrams["chart"], "Hình 15.2 — Biểu đồ thống kê phân bố điểm và sĩ số lớp từ CSDL")

    # --- SLIDE 16: CẢNH BÁO HỌC VỤ ---
    s16 = new_slide(16, "Phân hệ Cảnh báo Học vụ", "Quy trình xét tự động từ GPA & tín chỉ nợ, phân mức cảnh báo và theo dõi xử lý")
    s16.add_card(0.42, 1.22, 4.35, 5.4, "Quy tắc Xét Cảnh báo Học vụ", [
        "Tính toán trực tiếp từ bảng điểm thật trên Backend API.",
        "Cảnh báo Mức 1: GPA tích lũy hệ 4 < 2.00 hoặc nợ ≥ 3 tín chỉ không đạt (điểm F).",
        "Cảnh báo Mức 2: GPA tích lũy hệ 4 < 1.20 hoặc nợ ≥ 7 tín chỉ không đạt.",
        "Quy trình xử lý: Chờ xử lý → Đã gửi thông báo → Đã tư vấn học vụ.",
        "Phòng Đào tạo & Giảng viên cố vấn cập nhật trạng thái trực tiếp; Sinh viên xem cảnh báo cá nhân.",
    ], RED)
    s16.add_image_fit(5.0, 1.22, 7.9, 5.15, SCREENSHOTS_DIR / "06_warnings.png", "Hình 16.1 — Giao diện Cảnh báo học vụ thực tế với dữ liệu từ hệ thống")

    # --- SLIDE 17: KIỂM THỬ HỆ THỐNG ---
    s17 = new_slide(17, "Kiểm thử Hệ thống (Database, API & Giao diện)", "Kết quả kiểm thử tự động T-SQL, FastAPI RBAC 3 đối tượng và giao diện thực tế")
    s17.add_card(0.42, 1.22, 5.8, 5.4, "Tổng hợp Kết quả Kiểm thử", [
        "Kiểm thử SQL Server (08_test_database.sql): 20/20 PASS (Constraints, UDF, SP, Multi-row Triggers, Transactions).",
        "Kiểm thử API & CRUD (test_api.py): 31/31 PASS (HTTP 200/201/400/404/409/422).",
        "Kiểm thử Phân quyền 3 đối tượng: PASS — Sinh viên/Giảng viên bị chặn 403 ở Backend khi gọi API ngoài quyền.",
        "Kiểm thử Giao diện & Responsive: PASS — Sidebar cố định Desktop, thu gọn tooltip, Drawer Mobile.",
    ], SUCCESS)
    s17.add_image_fit(6.48, 1.22, 6.42, 5.15, SCREENSHOTS_DIR / "07_accounts_rbac.png", "Hình 17.1 — Trang Quản lý Tài khoản & Ma trận Phân quyền 3 Đối tượng")

    # --- SLIDE 18: GITHUB & PHÂN CÔNG 5 THÀNH VIÊN ---
    s18 = new_slide(18, "Quản lý Mã nguồn GitHub & Phân công Nhóm", "Cấu trúc thư mục mã nguồn rõ ràng và phân nhiệm 5 thành viên")
    s18.add_card(0.45, 1.25, 5.5, 5.4, "Repository & Cấu trúc Dự án", [
        "GitHub: github.com/dlhchu98-sketch/student-grade-management",
        "01..08_*.sql — Toàn bộ kịch bản SQL Server SSMS 22.",
        "main.py — FastAPI Backend, RBAC 3 đối tượng & SQL Sync.",
        "static/index.html — Giao diện Web chuẩn Design System Sidebar.",
        "test_api.py — Bộ kiểm thử tích hợp API tự động.",
        "BAO_CAO_DO_AN.pptx & BAO_CAO_DO_AN.md — Tài liệu bảo vệ.",
    ], BLUE_DARK)
    s18.add_card(6.22, 1.25, 6.66, 5.4, "Phân công Công việc 5 Thành viên", [
        "TV 1 (Nhóm trưởng): Thiết kế ERD, chuẩn hóa 3NF, viết 01–03 & 07 Transactions SQL.",
        "TV 2: Viết Stored Procedures, UDFs, Triggers (04–06) và bộ test 08_test_database.sql.",
        "TV 3: Phát triển Backend FastAPI (main.py), Pydantic validation và xác thực RBAC 3 vai trò.",
        "TV 4: Thiết kế Design System (#C62828/#DCEBFA), Sidebar trái, Dashboard & 12 trang chức năng.",
        "TV 5: Kiểm thử tích hợp (test_api.py), chụp minh chứng UI, tổng hợp báo cáo và Slide bảo vệ.",
    ], RED)

    # --- SLIDE 19: KẾT LUẬN & HƯỚNG PHÁT TRIỂN ---
    s19 = new_slide(19, "Kết luận, Hạn chế & Hướng Phát triển", "Đánh giá kết quả đạt được và lộ trình mở rộng cho thực tế triển khai")
    s19.add_card(0.45, 1.25, 4.0, 5.4, "Kết quả Đạt được", [
        "Hoàn thiện CSDL chuẩn 3NF với đầy đủ SP, UDF, Multi-row Trigger và Transaction trên SQL Server.",
        "Nâng cấp toàn diện giao diện Sidebar bên trái, bộ màu nhận diện đại học đồng bộ.",
        "Triển khai đầy đủ Đăng nhập & Phân quyền 3 đối tượng (Admin, Giảng viên, Sinh viên).",
        "Dữ liệu thống kê Dashboard, GPA (10/4) và Cảnh báo học vụ vận hành từ API thật.",
    ], SUCCESS)
    s19.add_card(4.67, 1.25, 4.0, 5.4, "Hạn chế Hiện tại", [
        "Chưa tích hợp gửi email/SMS tự động khi sinh viên rơi vào diện cảnh báo học vụ.",
        "Chưa có phân hệ xuất bảng điểm chính thức định dạng PDF có chữ ký số.",
        "Chưa tích hợp cổng thanh toán học phí trực tuyến theo tín chỉ đăng ký.",
    ], WARNING)
    s19.add_card(8.89, 1.25, 4.0, 5.4, "Hướng Phát triển", [
        "Tích hợp OAuth2 / SSO đại học và xác thực 2 lớp (2FA) cho tài khoản quản trị.",
        "Bổ sung module thời khóa biểu xung đột tự động và lịch thi cuối kỳ.",
        "Ứng dụng AI dự báo sớm nguy cơ cảnh báo học vụ ngay từ điểm quá trình giữa kỳ.",
    ], BLUE_DARK)

    # --- SLIDE 20: CẢM ƠN & Q&A ---
    s20 = new_slide(20, "Cảm ơn", is_cover=True)
    s20.add_rect(0, 0, 13.333, 2.35, BLUE_LIGHT)
    s20.add_rect(0, 2.35, 13.333, 0.08, RED)
    s20.add_text(0.8, 0.55, 11.7, 1.4, [
        {"text": "TRÂN TRỌNG CẢM ƠN QUÝ THẦY CÔ ĐÃ LẮNG NGHE!", "size": 28, "bold": True, "color": TEXT_MAIN, "align": "ctr", "space_after": 8},
        {"text": "HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐÀO TẠO ĐẠI HỌC", "size": 15, "bold": True, "color": BLUE_DARK, "align": "ctr"},
    ])
    s20.add_rect(3.4, 3.05, 6.53, 1.5, RED_LIGHT, RED, radius=True)
    s20.add_text(3.6, 3.28, 6.13, 1.1, [
        {"text": "PHẦN HỎI ĐÁP & DEMO TRỰC TIẾP (Q&A)", "size": 20, "bold": True, "color": RED, "align": "ctr", "space_after": 6},
        {"text": "Sẵn sàng trình diễn trực tiếp 3 tài khoản (Admin / Giảng viên / Sinh viên) & SSMS 22", "size": 12, "color": TEXT_MAIN, "align": "ctr"},
    ])
    s20.add_text(1.0, 5.15, 11.33, 1.6, [
        {"text": "Tài khoản Demo trực tiếp tại http://127.0.0.1:8000/", "size": 13, "bold": True, "color": BLUE_DARK, "align": "ctr", "space_after": 6},
        {"text": "Phòng Đào tạo: admin / admin123   |   Giảng viên: gv.minh / gv123   |   Sinh viên: SV2024001 / sv123", "size": 12.5, "bold": True, "color": TEXT_MAIN, "align": "ctr", "space_after": 8},
        {"text": "Repository: https://github.com/dlhchu98-sketch/student-grade-management", "size": 11.5, "color": TEXT_MUTED, "align": "ctr"},
    ])

    return slides


def write_pptx(slides: list[SlideBuilder], out_path: Path) -> None:
    content_types_slides = []
    pres_sld_ids = []
    pres_rels = []

    media_files: dict[str, Path] = {}
    media_counter = 1

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, sl in enumerate(slides, start=1):
            slide_rel_items = [
                '<Relationship Id="rIdLayout" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            ]
            for rid, img_path in sl.images:
                ext = img_path.suffix.lower().lstrip(".") or "png"
                media_name = f"image{media_counter}.{ext}"
                media_counter += 1
                media_files[media_name] = img_path
                slide_rel_items.append(
                    f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{media_name}"/>'
                )

            zf.writestr(f"ppt/slides/slide{idx}.xml", sl.to_xml())
            zf.writestr(
                f"ppt/slides/_rels/slide{idx}.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(slide_rel_items)
                + "</Relationships>",
            )
            content_types_slides.append(
                f'<Override PartName="/ppt/slides/slide{idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            )
            pres_sld_ids.append(f'<p:sldId id="{255 + idx}" r:id="rIdSld{idx}"/>')
            pres_rels.append(
                f'<Relationship Id="rIdSld{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{idx}.xml"/>'
            )

        for media_name, img_path in media_files.items():
            zf.write(img_path, f"ppt/media/{media_name}")

        zf.writestr(
            "[Content_Types].xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="jpg" ContentType="image/jpeg"/>
  <Default Extension="jpeg" ContentType="image/jpeg"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  {''.join(content_types_slides)}
</Types>""",
        )

        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>""",
        )

        zf.writestr(
            "ppt/presentation.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rIdMaster1"/></p:sldMasterIdLst>
  <p:sldIdLst>{''.join(pres_sld_ids)}</p:sldIdLst>
  <p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}" type="screen16x9"/>
  <p:notesSz cx="{SLIDE_H}" cy="{SLIDE_W}"/>
</p:presentation>""",
        )

        zf.writestr(
            "ppt/_rels/presentation.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdMaster1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
            + "".join(pres_rels)
            + "</Relationships>",
        )

        zf.writestr(
            "ppt/slideMasters/slideMaster1.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rIdLayout1"/></p:sldLayoutIdLst>
</p:sldMaster>""",
        )

        zf.writestr(
            "ppt/slideMasters/_rels/slideMaster1.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdLayout1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rIdTheme1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>""",
        )

        zf.writestr(
            "ppt/slideLayouts/slideLayout1.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
</p:sldLayout>""",
        )

        zf.writestr(
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdMaster1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>""",
        )

        zf.writestr(
            "ppt/theme/theme1.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="UniversityTheme">
  <a:themeElements>
    <a:clrScheme name="UniversityColors">
      <a:dk1><a:srgbClr val="{TEXT_MAIN}"/></a:dk1>
      <a:lt1><a:srgbClr val="{WHITE}"/></a:lt1>
      <a:dk2><a:srgbClr val="{BLUE_DARK}"/></a:dk2>
      <a:lt2><a:srgbClr val="{BLUE_LIGHT}"/></a:lt2>
      <a:accent1><a:srgbClr val="{RED}"/></a:accent1>
      <a:accent2><a:srgbClr val="{BLUE_DARK}"/></a:accent2>
      <a:accent3><a:srgbClr val="{SUCCESS}"/></a:accent3>
      <a:accent4><a:srgbClr val="{WARNING}"/></a:accent4>
      <a:accent5><a:srgbClr val="{BLUE_LIGHT}"/></a:accent5>
      <a:accent6><a:srgbClr val="{RED_LIGHT}"/></a:accent6>
      <a:hlink><a:srgbClr val="{BLUE_DARK}"/></a:hlink>
      <a:folHlink><a:srgbClr val="{RED}"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="UniversityFonts">
      <a:majorFont><a:latin typeface="Arial"/><a:ea typeface="Arial"/><a:cs typeface="Arial"/></a:majorFont>
      <a:minorFont><a:latin typeface="Arial"/><a:ea typeface="Arial"/><a:cs typeface="Arial"/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Simple">
      <a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>
      <a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="25400"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>
      <a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
      <a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>""",
        )


def main():
    diagrams = generate_diagrams()
    slides = build_all_20_slides(diagrams)
    write_pptx(slides, PPTX_PATH)
    print(f"OK: Generated {PPTX_PATH} ({len(slides)} slides, {PPTX_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
