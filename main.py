import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator

# Load biến môi trường từ file .env (nếu có)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

# ==============================================================================
# 1. CẤU HÌNH KẾT NỐI CƠ SỞ DỮ LIỆU (SQL SERVER PRIMARY + SQLITE FALLBACK)
# ==============================================================================
DB_SERVER = os.getenv("DB_SERVER", r".\SQLEXPRESS")
DB_NAME = os.getenv("DB_NAME", "StudentGradeManagementDB")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_TRUSTED = os.getenv("DB_TRUSTED_CONNECTION", "yes").lower() in ("yes", "true", "1")
DB_MODE_PREF = os.getenv("DB_ENGINE", "auto").lower()  # auto | mssql | sqlite
SQLITE_DB_PATH = BASE_DIR / "student_grade_local.db"

DB_BACKEND = "sqlite"
ODBC_DRIVER = "SQLite3 Local Sync (SQL Server Compatible)"
_pyodbc_module = None
_odbc_conn_str = ""


def _detect_and_init_backend() -> None:
    global DB_BACKEND, ODBC_DRIVER, _pyodbc_module, _odbc_conn_str
    if DB_MODE_PREF == "sqlite":
        DB_BACKEND = "sqlite"
        return

    import threading

    probe_result: Dict[str, Any] = {"ok": False}

    def _probe_mssql():
        try:
            import pyodbc  # type: ignore

            env_driver = os.getenv("DB_DRIVER")
            if env_driver:
                driver = env_driver
            else:
                available = pyodbc.drivers()
                driver = "ODBC Driver 17 for SQL Server"
                for preferred in [
                    "ODBC Driver 18 for SQL Server",
                    "ODBC Driver 17 for SQL Server",
                    "SQL Server Native Client 11.0",
                    "SQL Server",
                ]:
                    if preferred in available:
                        driver = preferred
                        break

            def build_conn(database: str) -> str:
                parts = [
                    f"DRIVER={{{driver}}}",
                    f"SERVER={DB_SERVER}",
                    f"DATABASE={database}",
                    "TrustServerCertificate=yes",
                    "Connection Timeout=2",
                ]
                if DB_TRUSTED and not DB_USER:
                    parts.append("Trusted_Connection=yes")
                else:
                    parts.append(f"UID={DB_USER}")
                    parts.append(f"PWD={DB_PASSWORD}")
                return ";".join(parts) + ";"

            with pyodbc.connect(build_conn("master"), autocommit=True, timeout=2) as conn:
                cur = conn.cursor()
                cur.execute(
                    f"IF DB_ID(N'{DB_NAME}') IS NULL BEGIN CREATE DATABASE [{DB_NAME}]; END"
                )

            probe_result["ok"] = True
            probe_result["pyodbc"] = pyodbc
            probe_result["driver"] = driver
            probe_result["conn_str"] = build_conn(DB_NAME)
        except Exception:
            probe_result["ok"] = False

    t = threading.Thread(target=_probe_mssql, daemon=True)
    t.start()
    t.join(timeout=2.5)

    if probe_result.get("ok"):
        _pyodbc_module = probe_result["pyodbc"]
        ODBC_DRIVER = probe_result["driver"]
        _odbc_conn_str = probe_result["conn_str"]
        DB_BACKEND = "mssql"
    else:
        DB_BACKEND = "sqlite"
        ODBC_DRIVER = "SQLite3 Local Engine (SQL Server Schema Sync)"


_detect_and_init_backend()


class DBConnectionWrapper:
    """Wrapper DB-API đồng nhất giữa Microsoft SQL Server (pyodbc) và SQLite."""

    def __init__(self) -> None:
        self.backend = DB_BACKEND
        if self.backend == "mssql" and _pyodbc_module is not None:
            self.conn = _pyodbc_module.connect(_odbc_conn_str)
        else:
            self.backend = "sqlite"
            self.conn = sqlite3.connect(str(SQLITE_DB_PATH), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON;")

    def execute(self, sql: str, params: Any = None):
        cur = self.conn.cursor()
        if params is None:
            cur.execute(sql)
            return cur
        if isinstance(params, dict):
            # Hỗ trợ named params kiểu :id cho tương thích test_api.py
            sql_converted = sql
            values: List[Any] = []
            import re

            def repl(match):
                key = match.group(1)
                values.append(params[key])
                return "?"

            sql_converted = re.sub(r":([a-zA-Z_][a-zA-Z0-9_]*)", repl, sql_converted)
            cur.execute(sql_converted, values)
            return cur
        cur.execute(sql, params)
        return cur

    def fetchone_dict(self, sql: str, params: Any = None) -> Optional[Dict[str, Any]]:
        cur = self.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        if isinstance(row, sqlite3.Row):
            return dict(row)
        cols = [col[0] for col in cur.description]
        return dict(zip(cols, row))

    def fetchall_dict(self, sql: str, params: Any = None) -> List[Dict[str, Any]]:
        cur = self.execute(sql, params)
        rows = cur.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], sqlite3.Row):
            return [dict(r) for r in rows]
        cols = [col[0] for col in cur.description]
        return [dict(zip(cols, r)) for r in rows]

    def insert_and_get_id(self, sql: str, params: tuple) -> int:
        cur = self.conn.cursor()
        if self.backend == "mssql":
            cur.execute(sql + "; SELECT CAST(SCOPE_IDENTITY() AS INT);", params)
            cur.nextset()
            row = cur.fetchone()
            return int(row[0])
        cur.execute(sql, params)
        return int(cur.lastrowid)

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()


def SessionLocal() -> DBConnectionWrapper:
    return DBConnectionWrapper()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==============================================================================
# 2. TIỆN ÍCH NGHIỆP VỤ ĐIỂM SỐ, GPA HỆ 10 / HỆ 4, CẢNH BÁO HỌC VỤ & BẢO MẬT
# ==============================================================================
def calculate_final_score(process_score: float, exam_score: float) -> float:
    """Tính điểm tổng kết theo trọng số: 40% điểm quá trình + 60% điểm thi."""
    return round(process_score * 0.4 + exam_score * 0.6, 2)


def classify_grade(final_score: float) -> str:
    """Xếp loại học lực theo thang điểm 10 (giữ nguyên tương thích nghiệp vụ)."""
    if final_score >= 8.5:
        return "Giỏi (A)"
    if final_score >= 7.0:
        return "Khá (B)"
    if final_score >= 5.5:
        return "Trung bình (C)"
    if final_score >= 4.0:
        return "Trung bình yếu (D)"
    return "Kém / Trượt (F)"


def convert_to_letter_and_gpa4(final_score: float) -> tuple[str, float]:
    """Quy đổi điểm hệ 10 sang điểm chữ và điểm hệ 4 chuẩn tín chỉ đại học."""
    if final_score >= 8.5:
        return ("A", 4.0)
    if final_score >= 8.0:
        return ("B+", 3.5)
    if final_score >= 7.0:
        return ("B", 3.0)
    if final_score >= 6.5:
        return ("C+", 2.5)
    if final_score >= 5.5:
        return ("C", 2.0)
    if final_score >= 5.0:
        return ("D+", 1.5)
    if final_score >= 4.0:
        return ("D", 1.0)
    return ("F", 0.0)


def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt_val = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_val.encode("utf-8"), 100_000
    ).hex()
    return f"{salt_val}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    if "$" not in stored_hash:
        return False
    salt_val, expected = stored_hash.split("$", 1)
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_val.encode("utf-8"), 100_000
    ).hex()
    return hmac.compare_digest(actual, expected)


ROLE_METADATA: Dict[str, Dict[str, Any]] = {
    "ADMIN": {
        "label": "Quản trị viên / Phòng Đào tạo",
        "short_label": "Phòng Đào tạo",
        "permissions": [
            "dashboard",
            "students:read",
            "students:write",
            "classes:read",
            "classes:write",
            "subjects:read",
            "subjects:write",
            "curriculum:read",
            "curriculum:write",
            "sections:read",
            "sections:write",
            "enrollments:read",
            "enrollments:write",
            "scores:read",
            "scores:write",
            "scores:delete",
            "results:read",
            "warnings:read",
            "warnings:write",
            "accounts:read",
            "accounts:write",
            "settings:read",
        ],
    },
    "LECTURER": {
        "label": "Giảng viên",
        "short_label": "Giảng viên",
        "permissions": [
            "dashboard",
            "students:read",
            "classes:read",
            "subjects:read",
            "curriculum:read",
            "sections:read",
            "scores:read",
            "scores:write",
            "results:read",
            "warnings:read",
        ],
    },
    "STUDENT": {
        "label": "Sinh viên",
        "short_label": "Sinh viên",
        "permissions": [
            "dashboard",
            "curriculum:read",
            "sections:read",
            "enrollments:read",
            "enrollments:write",
            "results:read",
            "warnings:read",
        ],
    },
}

# Bộ nhớ phiên đăng nhập (Bearer Token -> User payload)
ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _parse_optional_user(
    authorization: Optional[str] = Header(default=None),
) -> Optional[Dict[str, Any]]:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header Authorization không hợp lệ (yêu cầu dạng Bearer token)",
        )
    token = parts[1].strip()
    session_user = ACTIVE_SESSIONS.get(token)
    if not session_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại.",
        )
    return session_user


def require_authenticated_user(
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
) -> Dict[str, Any]:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yêu cầu đăng nhập để thực hiện thao tác này.",
        )
    return user


def enforce_roles(user: Optional[Dict[str, Any]], allowed_roles: List[str], action_name: str) -> None:
    """Kiểm tra phân quyền ở backend khi request có xác thực Bearer token."""
    if user is None:
        return
    if user["role"] not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Vai trò '{user['role_label']}' không có quyền {action_name}.",
        )


def _format_date(val: Any) -> str:
    if isinstance(val, (date, datetime)):
        return val.strftime("%Y-%m-%d")
    return str(val)


# ==============================================================================
# 3. KHỞI TẠO LƯỢC ĐỒ BẢNG & DỮ LIỆU MẪU CHUẨN ĐẠI HỌC
# ==============================================================================
def init_db_and_seed() -> None:
    db = SessionLocal()
    try:
        if db.backend == "mssql":
            # Giữ nguyên cấu trúc 4 bảng cốt lõi đồng bộ 02_create_tables.sql
            db.execute(
                """
                IF OBJECT_ID(N'dbo.classes', N'U') IS NULL
                CREATE TABLE dbo.classes (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    class_code VARCHAR(50) NOT NULL UNIQUE,
                    class_name NVARCHAR(100) NOT NULL,
                    academic_year VARCHAR(30) NULL DEFAULT ('2024-2028'),
                    homeroom_teacher NVARCHAR(100) NULL
                );
                """
            )
            db.execute(
                """
                IF OBJECT_ID(N'dbo.students', N'U') IS NULL
                CREATE TABLE dbo.students (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    student_code VARCHAR(50) NOT NULL UNIQUE,
                    full_name NVARCHAR(100) NOT NULL,
                    date_of_birth DATE NOT NULL,
                    gender NVARCHAR(20) NOT NULL,
                    email VARCHAR(120) NOT NULL UNIQUE,
                    hometown NVARCHAR(150) NULL,
                    class_id INT NOT NULL FOREIGN KEY REFERENCES dbo.classes(id)
                );
                """
            )
            db.execute(
                """
                IF OBJECT_ID(N'dbo.subjects', N'U') IS NULL
                CREATE TABLE dbo.subjects (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    subject_code VARCHAR(50) NOT NULL UNIQUE,
                    subject_name NVARCHAR(120) NOT NULL,
                    credits INT NOT NULL,
                    department NVARCHAR(100) NULL
                );
                """
            )
            db.execute(
                """
                IF OBJECT_ID(N'dbo.scores', N'U') IS NULL
                CREATE TABLE dbo.scores (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    student_id INT NOT NULL FOREIGN KEY REFERENCES dbo.students(id),
                    subject_id INT NOT NULL FOREIGN KEY REFERENCES dbo.subjects(id),
                    semester VARCHAR(30) NOT NULL DEFAULT ('HK1-2026'),
                    process_score FLOAT NOT NULL,
                    exam_score FLOAT NOT NULL,
                    final_score FLOAT NOT NULL,
                    CONSTRAINT uq_student_subject_semester UNIQUE (student_id, subject_id, semester)
                );
                """
            )
            db.execute(
                """
                IF OBJECT_ID(N'dbo.app_accounts', N'U') IS NULL
                CREATE TABLE dbo.app_accounts (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    username VARCHAR(60) NOT NULL UNIQUE,
                    password_hash VARCHAR(200) NOT NULL,
                    full_name NVARCHAR(120) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    email VARCHAR(120) NULL,
                    department NVARCHAR(120) NULL,
                    student_id INT NULL,
                    assigned_classes NVARCHAR(250) NULL,
                    is_active INT NOT NULL DEFAULT 1
                );
                """
            )
            db.execute(
                """
                IF OBJECT_ID(N'dbo.curriculum_items', N'U') IS NULL
                CREATE TABLE dbo.curriculum_items (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    major_name NVARCHAR(120) NOT NULL,
                    cohort VARCHAR(30) NOT NULL,
                    subject_id INT NOT NULL FOREIGN KEY REFERENCES dbo.subjects(id),
                    semester_plan INT NOT NULL DEFAULT 1,
                    course_group NVARCHAR(40) NOT NULL DEFAULT N'Bắt buộc',
                    prerequisite_code VARCHAR(50) NULL
                );
                """
            )
            db.execute(
                """
                IF OBJECT_ID(N'dbo.course_sections', N'U') IS NULL
                CREATE TABLE dbo.course_sections (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    section_code VARCHAR(50) NOT NULL UNIQUE,
                    subject_id INT NOT NULL FOREIGN KEY REFERENCES dbo.subjects(id),
                    semester VARCHAR(30) NOT NULL,
                    lecturer_name NVARCHAR(100) NOT NULL,
                    schedule_text NVARCHAR(120) NOT NULL,
                    room VARCHAR(40) NOT NULL,
                    max_capacity INT NOT NULL DEFAULT 45,
                    prerequisite_code VARCHAR(50) NULL,
                    registration_open INT NOT NULL DEFAULT 1
                );
                """
            )
            db.execute(
                """
                IF OBJECT_ID(N'dbo.enrollments', N'U') IS NULL
                CREATE TABLE dbo.enrollments (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    student_id INT NOT NULL FOREIGN KEY REFERENCES dbo.students(id),
                    section_id INT NOT NULL FOREIGN KEY REFERENCES dbo.course_sections(id),
                    registered_at VARCHAR(30) NOT NULL,
                    status NVARCHAR(40) NOT NULL DEFAULT N'Đã đăng ký',
                    CONSTRAINT uq_student_section UNIQUE (student_id, section_id)
                );
                """
            )
            db.execute(
                """
                IF OBJECT_ID(N'dbo.warning_records', N'U') IS NULL
                CREATE TABLE dbo.warning_records (
                    student_id INT PRIMARY KEY,
                    handling_status NVARCHAR(60) NOT NULL DEFAULT N'Chờ xử lý',
                    advisor_note NVARCHAR(250) NULL,
                    updated_at VARCHAR(30) NULL
                );
                """
            )
            db.commit()
        else:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS classes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    class_code TEXT NOT NULL UNIQUE,
                    class_name TEXT NOT NULL,
                    academic_year TEXT DEFAULT '2024-2028',
                    homeroom_teacher TEXT
                );
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_code TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    date_of_birth TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    hometown TEXT,
                    class_id INTEGER NOT NULL REFERENCES classes(id)
                );
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS subjects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_code TEXT NOT NULL UNIQUE,
                    subject_name TEXT NOT NULL,
                    credits INTEGER NOT NULL,
                    department TEXT
                );
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL REFERENCES students(id),
                    subject_id INTEGER NOT NULL REFERENCES subjects(id),
                    semester TEXT NOT NULL DEFAULT 'HK1-2026',
                    process_score REAL NOT NULL,
                    exam_score REAL NOT NULL,
                    final_score REAL NOT NULL,
                    UNIQUE (student_id, subject_id, semester)
                );
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS app_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    email TEXT,
                    department TEXT,
                    student_id INTEGER,
                    assigned_classes TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                );
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS curriculum_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    major_name TEXT NOT NULL,
                    cohort TEXT NOT NULL,
                    subject_id INTEGER NOT NULL REFERENCES subjects(id),
                    semester_plan INTEGER NOT NULL DEFAULT 1,
                    course_group TEXT NOT NULL DEFAULT 'Bắt buộc',
                    prerequisite_code TEXT
                );
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS course_sections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    section_code TEXT NOT NULL UNIQUE,
                    subject_id INTEGER NOT NULL REFERENCES subjects(id),
                    semester TEXT NOT NULL,
                    lecturer_name TEXT NOT NULL,
                    schedule_text TEXT NOT NULL,
                    room TEXT NOT NULL,
                    max_capacity INTEGER NOT NULL DEFAULT 45,
                    prerequisite_code TEXT,
                    registration_open INTEGER NOT NULL DEFAULT 1
                );
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS enrollments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL REFERENCES students(id),
                    section_id INTEGER NOT NULL REFERENCES course_sections(id),
                    registered_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Đã đăng ký',
                    UNIQUE (student_id, section_id)
                );
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS warning_records (
                    student_id INTEGER PRIMARY KEY,
                    handling_status TEXT NOT NULL DEFAULT 'Chờ xử lý',
                    advisor_note TEXT,
                    updated_at TEXT
                );
                """
            )
            db.commit()

        # Seed dữ liệu 4 bảng cốt lõi nếu chưa có
        cnt_cls = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM classes")["cnt"]
        if cnt_cls == 0:
            classes_seed = [
                ("CNTT01-K18", "Công nghệ phần mềm 01 - K18", "2024-2028", "TS. Nguyễn Văn Minh"),
                ("CNTT02-K18", "Hệ thống thông tin 02 - K18", "2024-2028", "ThS. Trần Thị Thu Hà"),
                ("KHDL01-K18", "Khoa học dữ liệu & AI - K18", "2024-2028", "PGS.TS. Lê Hoàng Nam"),
                ("ATTT01-K18", "An toàn thông tin 01 - K18", "2024-2028", "TS. Phạm Quốc Bảo"),
            ]
            class_ids: List[int] = []
            for row in classes_seed:
                cid = db.insert_and_get_id(
                    "INSERT INTO classes (class_code, class_name, academic_year, homeroom_teacher) VALUES (?, ?, ?, ?)",
                    row,
                )
                class_ids.append(cid)

            subjects_seed = [
                ("IT3010", "Hệ quản trị Cơ sở dữ liệu SQL Server", 3, "Hệ thống thông tin"),
                ("IT3020", "Phát triển Ứng dụng Web với FastAPI", 3, "Công nghệ phần mềm"),
                ("IT3030", "Cấu trúc dữ liệu và Giải thuật", 4, "Khoa học máy tính"),
                ("IT3040", "Trí tuệ nhân tạo & Học máy", 3, "Khoa học dữ liệu"),
                ("IT3050", "Mạng máy tính và Bảo mật", 3, "An toàn thông tin"),
                ("IT3060", "Phân tích & Thiết kế Hệ thống", 3, "Hệ thống thông tin"),
                ("IT3070", "Kiểm thử & Đảm bảo chất lượng PM", 3, "Công nghệ phần mềm"),
            ]
            sub_ids: List[int] = []
            for row in subjects_seed:
                sid = db.insert_and_get_id(
                    "INSERT INTO subjects (subject_code, subject_name, credits, department) VALUES (?, ?, ?, ?)",
                    row,
                )
                sub_ids.append(sid)

            students_seed = [
                ("SV2024001", "Nguyễn Minh Quân", "2005-03-15", "Nam", "quan.nm24001@student.edu.vn", "Hà Nội", class_ids[0]),
                ("SV2024002", "Trần Ngọc Ánh", "2005-07-22", "Nữ", "anh.tn24002@student.edu.vn", "Hải Phòng", class_ids[0]),
                ("SV2024003", "Lê Hoàng Phúc", "2005-11-08", "Nam", "phuc.lh24003@student.edu.vn", "Đà Nẵng", class_ids[1]),
                ("SV2024004", "Phạm Khánh Linh", "2005-01-30", "Nữ", "linh.pk24004@student.edu.vn", "Nam Định", class_ids[1]),
                ("SV2024005", "Hoàng Đức Tuấn", "2005-05-19", "Nam", "tuan.hd24005@student.edu.vn", "Nghệ An", class_ids[2]),
                ("SV2024006", "Vũ Phương Thảo", "2005-09-12", "Nữ", "thao.vp24006@student.edu.vn", "Quảng Ninh", class_ids[3]),
                ("SV2024007", "Đỗ Gia Huy", "2005-04-04", "Nam", "huy.dg24007@student.edu.vn", "Thái Bình", class_ids[0]),
                ("SV2024008", "Bùi Mai Hương", "2005-12-25", "Nữ", "huong.bm24008@student.edu.vn", "Hưng Yên", class_ids[2]),
            ]
            st_ids: List[int] = []
            for row in students_seed:
                stid = db.insert_and_get_id(
                    "INSERT INTO students (student_code, full_name, date_of_birth, gender, email, hometown, class_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
                st_ids.append(stid)

            scores_seed = [
                # Học kỳ trước HK2-2025 (để biểu đồ tiến trình học tập có dữ liệu thực)
                (st_ids[0], sub_ids[2], "HK2-2025", 8.5, 8.0),
                (st_ids[0], sub_ids[5], "HK2-2025", 8.0, 8.5),
                (st_ids[1], sub_ids[5], "HK2-2025", 7.5, 7.5),
                (st_ids[2], sub_ids[2], "HK2-2025", 6.0, 5.5),
                (st_ids[5], sub_ids[2], "HK2-2025", 3.5, 3.0),
                (st_ids[6], sub_ids[2], "HK2-2025", 4.0, 3.5),
                # Học kỳ hiện tại HK1-2026
                (st_ids[0], sub_ids[0], "HK1-2026", 9.0, 8.5),
                (st_ids[0], sub_ids[1], "HK1-2026", 8.5, 9.0),
                (st_ids[1], sub_ids[0], "HK1-2026", 8.0, 7.5),
                (st_ids[1], sub_ids[2], "HK1-2026", 7.5, 8.0),
                (st_ids[2], sub_ids[0], "HK1-2026", 6.5, 7.0),
                (st_ids[3], sub_ids[1], "HK1-2026", 9.5, 9.0),
                (st_ids[3], sub_ids[0], "HK1-2026", 9.0, 8.5),
                (st_ids[4], sub_ids[3], "HK1-2026", 8.0, 8.5),
                (st_ids[4], sub_ids[0], "HK1-2026", 7.5, 8.0),
                (st_ids[5], sub_ids[4], "HK1-2026", 4.5, 3.5),
                (st_ids[5], sub_ids[0], "HK1-2026", 4.0, 4.0),
                (st_ids[6], sub_ids[0], "HK1-2026", 3.0, 2.5),
                (st_ids[6], sub_ids[1], "HK1-2026", 5.0, 4.5),
                (st_ids[7], sub_ids[3], "HK1-2026", 8.5, 8.0),
            ]
            for st_id, sub_id, sem, proc, exam in scores_seed:
                final_val = calculate_final_score(proc, exam)
                db.execute(
                    "INSERT INTO scores (student_id, subject_id, semester, process_score, exam_score, final_score) VALUES (?, ?, ?, ?, ?, ?)",
                    (st_id, sub_id, sem, proc, exam, final_val),
                )
            db.commit()

        # Seed tài khoản 3 đối tượng (Admin/PĐT, Giảng viên, Sinh viên)
        cnt_acc = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM app_accounts")["cnt"]
        if cnt_acc == 0:
            st1 = db.fetchone_dict("SELECT id FROM students WHERE student_code = ?", ("SV2024001",))
            st6 = db.fetchone_dict("SELECT id FROM students WHERE student_code = ?", ("SV2024006",))
            accounts_seed = [
                (
                    "admin",
                    hash_password("admin123"),
                    "Nguyễn Thu Trang",
                    "ADMIN",
                    "daotao@university.edu.vn",
                    "Phòng Đào tạo Đại học",
                    None,
                    "ALL",
                    1,
                ),
                (
                    "gv.minh",
                    hash_password("gv123"),
                    "TS. Nguyễn Văn Minh",
                    "LECTURER",
                    "minh.nv@university.edu.vn",
                    "Khoa Công nghệ thông tin",
                    None,
                    "CNTT01-K18,ATTT01-K18",
                    1,
                ),
                (
                    "gv.ha",
                    hash_password("gv123"),
                    "ThS. Trần Thị Thu Hà",
                    "LECTURER",
                    "ha.ttt@university.edu.vn",
                    "Khoa Hệ thống thông tin",
                    None,
                    "CNTT02-K18,KHDL01-K18",
                    1,
                ),
                (
                    "SV2024001",
                    hash_password("sv123"),
                    "Nguyễn Minh Quân",
                    "STUDENT",
                    "quan.nm24001@student.edu.vn",
                    "Công nghệ phần mềm 01 - K18",
                    st1["id"] if st1 else 1,
                    "CNTT01-K18",
                    1,
                ),
                (
                    "SV2024006",
                    hash_password("sv123"),
                    "Vũ Phương Thảo",
                    "STUDENT",
                    "thao.vp24006@student.edu.vn",
                    "An toàn thông tin 01 - K18",
                    st6["id"] if st6 else 6,
                    "ATTT01-K18",
                    1,
                ),
            ]
            for acc in accounts_seed:
                db.execute(
                    """
                    INSERT INTO app_accounts
                    (username, password_hash, full_name, role, email, department, student_id, assigned_classes, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    acc,
                )
            db.commit()

        # Seed Chương trình đào tạo (Curriculum)
        cnt_cur = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM curriculum_items")["cnt"]
        if cnt_cur == 0:
            subs = {
                s["subject_code"]: s["id"]
                for s in db.fetchall_dict("SELECT id, subject_code FROM subjects")
            }
            cur_seed = [
                ("Công nghệ phần mềm", "K18 (2024-2028)", subs.get("IT3030"), 2, "Bắt buộc", None),
                ("Công nghệ phần mềm", "K18 (2024-2028)", subs.get("IT3010"), 3, "Bắt buộc", "IT3030"),
                ("Công nghệ phần mềm", "K18 (2024-2028)", subs.get("IT3020"), 3, "Bắt buộc", "IT3010"),
                ("Công nghệ phần mềm", "K18 (2024-2028)", subs.get("IT3060"), 4, "Bắt buộc", "IT3010"),
                ("Công nghệ phần mềm", "K18 (2024-2028)", subs.get("IT3070"), 4, "Tự chọn", "IT3020"),
                ("Hệ thống thông tin", "K18 (2024-2028)", subs.get("IT3030"), 2, "Bắt buộc", None),
                ("Hệ thống thông tin", "K18 (2024-2028)", subs.get("IT3010"), 3, "Bắt buộc", "IT3030"),
                ("Hệ thống thông tin", "K18 (2024-2028)", subs.get("IT3060"), 3, "Bắt buộc", "IT3010"),
                ("Hệ thống thông tin", "K18 (2024-2028)", subs.get("IT3040"), 4, "Tự chọn", "IT3030"),
                ("Khoa học dữ liệu & AI", "K18 (2024-2028)", subs.get("IT3030"), 2, "Bắt buộc", None),
                ("Khoa học dữ liệu & AI", "K18 (2024-2028)", subs.get("IT3040"), 3, "Bắt buộc", "IT3030"),
                ("An toàn thông tin", "K18 (2024-2028)", subs.get("IT3050"), 3, "Bắt buộc", "IT3030"),
                ("An toàn thông tin", "K18 (2024-2028)", subs.get("IT3010"), 3, "Tự chọn", None),
            ]
            for item in cur_seed:
                if item[2]:
                    db.execute(
                        """
                        INSERT INTO curriculum_items
                        (major_name, cohort, subject_id, semester_plan, course_group, prerequisite_code)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        item,
                    )
            db.commit()

        # Seed Lớp học phần mở đăng ký (Course Sections) & Đăng ký mẫu
        cnt_sec = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM course_sections")["cnt"]
        if cnt_sec == 0:
            subs = {
                s["subject_code"]: s["id"]
                for s in db.fetchall_dict("SELECT id, subject_code FROM subjects")
            }
            sec_seed = [
                ("LHP-IT3010-01", subs.get("IT3010"), "HK2-2026", "TS. Nguyễn Văn Minh", "Thứ 2 (Tiết 1-3)", "B1-302", 45, "IT3030", 1),
                ("LHP-IT3020-01", subs.get("IT3020"), "HK2-2026", "TS. Nguyễn Văn Minh", "Thứ 3 (Tiết 4-6)", "C2-204", 40, "IT3010", 1),
                ("LHP-IT3040-01", subs.get("IT3040"), "HK2-2026", "PGS.TS. Lê Hoàng Nam", "Thứ 4 (Tiết 1-3)", "A1-405", 35, "IT3030", 1),
                ("LHP-IT3050-01", subs.get("IT3050"), "HK2-2026", "TS. Phạm Quốc Bảo", "Thứ 5 (Tiết 7-9)", "B2-105", 40, None, 1),
                ("LHP-IT3060-01", subs.get("IT3060"), "HK2-2026", "ThS. Trần Thị Thu Hà", "Thứ 6 (Tiết 1-3)", "C1-301", 30, "IT3010", 1),
                ("LHP-IT3070-01", subs.get("IT3070"), "HK2-2026", "TS. Nguyễn Văn Minh", "Thứ 7 (Tiết 1-3)", "A2-202", 2, "IT3020", 1),
            ]
            sec_ids: List[int] = []
            for srow in sec_seed:
                if srow[1]:
                    sec_id = db.insert_and_get_id(
                        """
                        INSERT INTO course_sections
                        (section_code, subject_id, semester, lecturer_name, schedule_text, room, max_capacity, prerequisite_code, registration_open)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        srow,
                    )
                    sec_ids.append(sec_id)

            students_all = db.fetchall_dict("SELECT id, student_code FROM students ORDER BY id ASC")
            if students_all and len(sec_ids) >= 5:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                sample_enroll = [
                    (students_all[0]["id"], sec_ids[2], now_str, "Đã đăng ký"),
                    (students_all[1]["id"], sec_ids[1], now_str, "Đã đăng ký"),
                    (students_all[2]["id"], sec_ids[4], now_str, "Đã đăng ký"),
                    (students_all[3]["id"], sec_ids[2], now_str, "Đã đăng ký"),
                    (students_all[4]["id"], sec_ids[3], now_str, "Đã đăng ký"),
                ]
                for en in sample_enroll:
                    try:
                        db.execute(
                            "INSERT INTO enrollments (student_id, section_id, registered_at, status) VALUES (?, ?, ?, ?)",
                            en,
                        )
                    except Exception:
                        pass
            db.commit()
    finally:
        db.close()


init_db_and_seed()


# ==============================================================================
# 4. PYDANTIC SCHEMAS (KIỂM TRA DỮ LIỆU ĐẦU VÀO & ĐẦU RA)
# ==============================================================================
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=60)
    password: str = Field(..., min_length=3, max_length=100)
    expected_role: Optional[str] = Field(None, description="ADMIN | LECTURER | STUDENT")


class AccountCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=60)
    password: str = Field(..., min_length=4, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=120)
    role: str = Field(..., description="ADMIN | LECTURER | STUDENT")
    email: Optional[str] = Field(None, max_length=120)
    department: Optional[str] = Field(None, max_length=120)
    student_id: Optional[int] = None
    assigned_classes: Optional[str] = Field(None, max_length=250)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        val = v.strip().upper()
        if val not in ("ADMIN", "LECTURER", "STUDENT"):
            raise ValueError("Vai trò phải là ADMIN, LECTURER hoặc STUDENT")
        return val


class AccountUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=120)
    role: Optional[str] = None
    department: Optional[str] = None
    assigned_classes: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=4, max_length=100)


class ClassCreate(BaseModel):
    class_code: str = Field(..., min_length=2, max_length=50)
    class_name: str = Field(..., min_length=2, max_length=100)
    academic_year: Optional[str] = Field("2024-2028", max_length=30)
    homeroom_teacher: Optional[str] = Field(None, max_length=100)

    @field_validator("class_code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Mã lớp học không được để trống")
        return cleaned

    @field_validator("class_name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Tên lớp học không được để trống")
        return cleaned


class ClassUpdate(BaseModel):
    class_code: Optional[str] = Field(None, min_length=2, max_length=50)
    class_name: Optional[str] = Field(None, min_length=2, max_length=100)
    academic_year: Optional[str] = Field(None, max_length=30)
    homeroom_teacher: Optional[str] = Field(None, max_length=100)

    @field_validator("class_code")
    @classmethod
    def normalize_code(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip().upper()
            if not cleaned:
                raise ValueError("Mã lớp học không được để trống")
            return cleaned
        return v

    @field_validator("class_name")
    @classmethod
    def normalize_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Tên lớp học không được để trống")
            return cleaned
        return v


class ClassResponse(BaseModel):
    id: int
    class_code: str
    class_name: str
    academic_year: Optional[str] = None
    homeroom_teacher: Optional[str] = None
    student_count: int = 0


class StudentCreate(BaseModel):
    student_code: str = Field(..., min_length=2, max_length=50)
    full_name: str = Field(..., min_length=2, max_length=100)
    date_of_birth: date
    gender: str = Field(..., min_length=1, max_length=20)
    email: EmailStr
    hometown: Optional[str] = Field(None, max_length=150)
    class_id: int = Field(..., gt=0)

    @field_validator("student_code")
    @classmethod
    def normalize_student_code(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Mã sinh viên không được để trống")
        return cleaned

    @field_validator("full_name", "gender")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Trường dữ liệu không được để trống")
        return cleaned


class StudentUpdate(BaseModel):
    student_code: Optional[str] = Field(None, min_length=2, max_length=50)
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, min_length=1, max_length=20)
    email: Optional[EmailStr] = None
    hometown: Optional[str] = Field(None, max_length=150)
    class_id: Optional[int] = Field(None, gt=0)

    @field_validator("student_code")
    @classmethod
    def normalize_student_code(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip().upper()
            if not cleaned:
                raise ValueError("Mã sinh viên không được để trống")
            return cleaned
        return v


class StudentResponse(BaseModel):
    id: int
    student_code: str
    full_name: str
    date_of_birth: date
    gender: str
    email: str
    hometown: Optional[str] = None
    class_id: int
    class_code: Optional[str] = None
    class_name: Optional[str] = None
    gpa10: Optional[float] = None
    gpa4: Optional[float] = None
    academic_status: Optional[str] = None


class SubjectCreate(BaseModel):
    subject_code: str = Field(..., min_length=2, max_length=50)
    subject_name: str = Field(..., min_length=2, max_length=120)
    credits: int = Field(..., ge=1, le=15)
    department: Optional[str] = Field(None, max_length=100)

    @field_validator("subject_code")
    @classmethod
    def normalize_subject_code(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Mã môn học không được để trống")
        return cleaned

    @field_validator("subject_name")
    @classmethod
    def normalize_subject_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Tên môn học không được để trống")
        return cleaned


class SubjectUpdate(BaseModel):
    subject_code: Optional[str] = Field(None, min_length=2, max_length=50)
    subject_name: Optional[str] = Field(None, min_length=2, max_length=120)
    credits: Optional[int] = Field(None, ge=1, le=15)
    department: Optional[str] = Field(None, max_length=100)

    @field_validator("subject_code")
    @classmethod
    def normalize_subject_code(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip().upper()
            if not cleaned:
                raise ValueError("Mã môn học không được để trống")
            return cleaned
        return v


class SubjectResponse(BaseModel):
    id: int
    subject_code: str
    subject_name: str
    credits: int
    department: Optional[str] = None
    score_count: int = 0


class ScoreCreate(BaseModel):
    student_id: int = Field(..., gt=0)
    subject_id: int = Field(..., gt=0)
    semester: str = Field("HK1-2026", min_length=2, max_length=30)
    process_score: float = Field(..., ge=0.0, le=10.0)
    exam_score: float = Field(..., ge=0.0, le=10.0)

    @field_validator("semester")
    @classmethod
    def normalize_semester(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Học kỳ không được để trống")
        return cleaned


class ScoreUpdate(BaseModel):
    student_id: Optional[int] = Field(None, gt=0)
    subject_id: Optional[int] = Field(None, gt=0)
    semester: Optional[str] = Field(None, min_length=2, max_length=30)
    process_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    exam_score: Optional[float] = Field(None, ge=0.0, le=10.0)

    @field_validator("semester")
    @classmethod
    def normalize_semester(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip().upper()
            if not cleaned:
                raise ValueError("Học kỳ không được để trống")
            return cleaned
        return v


class ScoreResponse(BaseModel):
    id: int
    student_id: int
    student_code: str
    student_name: str
    class_code: Optional[str] = None
    subject_id: int
    subject_code: str
    subject_name: str
    credits: int
    semester: str
    process_score: float
    exam_score: float
    final_score: float
    letter_grade: str
    gpa4_score: float
    grade_rank: str
    passed: bool


class CurriculumCreate(BaseModel):
    major_name: str = Field(..., min_length=2, max_length=120)
    cohort: str = Field("K18 (2024-2028)", min_length=2, max_length=30)
    subject_id: int = Field(..., gt=0)
    semester_plan: int = Field(1, ge=1, le=10)
    course_group: str = Field("Bắt buộc", max_length=40)
    prerequisite_code: Optional[str] = Field(None, max_length=50)


class SectionCreate(BaseModel):
    section_code: str = Field(..., min_length=2, max_length=50)
    subject_id: int = Field(..., gt=0)
    semester: str = Field("HK2-2026", min_length=2, max_length=30)
    lecturer_name: str = Field(..., min_length=2, max_length=100)
    schedule_text: str = Field(..., min_length=2, max_length=120)
    room: str = Field(..., min_length=2, max_length=40)
    max_capacity: int = Field(45, ge=1, le=200)
    prerequisite_code: Optional[str] = Field(None, max_length=50)


class EnrollmentCreate(BaseModel):
    section_id: int = Field(..., gt=0)
    student_id: Optional[int] = Field(None, gt=0)


class WarningUpdate(BaseModel):
    handling_status: str = Field(..., min_length=2, max_length=60)
    advisor_note: Optional[str] = Field(None, max_length=250)


# ==============================================================================
# 5. HÀM TÍNH TOÁN KẾT QUẢ HỌC TẬP & CẢNH BÁO HỌC VỤ TỪ DỮ LIỆU THẬT
# ==============================================================================
def compute_student_academic_summary(db: DBConnectionWrapper, student_id: int) -> Dict[str, Any]:
    rows = db.fetchall_dict(
        """
        SELECT sc.id, sc.semester, sc.process_score, sc.exam_score, sc.final_score,
               sub.subject_code, sub.subject_name, sub.credits
        FROM scores sc
        JOIN subjects sub ON sc.subject_id = sub.id
        WHERE sc.student_id = ?
        ORDER BY sc.semester ASC, sc.id ASC
        """,
        (student_id,),
    )
    semesters_map: Dict[str, Dict[str, Any]] = {}
    total_weighted_10 = 0.0
    total_weighted_4 = 0.0
    total_credits = 0
    passed_credits = 0
    failed_credits = 0
    detailed_rows: List[Dict[str, Any]] = []

    for r in rows:
        final_s = float(r["final_score"])
        credits = int(r["credits"])
        letter, gpa4 = convert_to_letter_and_gpa4(final_s)
        passed = final_s >= 4.0

        total_weighted_10 += final_s * credits
        total_weighted_4 += gpa4 * credits
        total_credits += credits
        if passed:
            passed_credits += credits
        else:
            failed_credits += credits

        sem = r["semester"]
        if sem not in semesters_map:
            semesters_map[sem] = {
                "semester": sem,
                "weighted_10": 0.0,
                "weighted_4": 0.0,
                "credits": 0,
                "passed_credits": 0,
                "failed_credits": 0,
                "subjects": [],
            }
        sm = semesters_map[sem]
        sm["weighted_10"] += final_s * credits
        sm["weighted_4"] += gpa4 * credits
        sm["credits"] += credits
        if passed:
            sm["passed_credits"] += credits
        else:
            sm["failed_credits"] += credits

        item = {
            "id": r["id"],
            "semester": sem,
            "subject_code": r["subject_code"],
            "subject_name": r["subject_name"],
            "credits": credits,
            "process_score": float(r["process_score"]),
            "exam_score": float(r["exam_score"]),
            "final_score": final_s,
            "letter_grade": letter,
            "gpa4_score": gpa4,
            "grade_rank": classify_grade(final_s),
            "passed": passed,
        }
        sm["subjects"].append(item)
        detailed_rows.append(item)

    semester_list = []
    for sem, sm in semesters_map.items():
        c = sm["credits"] or 1
        semester_list.append(
            {
                "semester": sem,
                "gpa10": round(sm["weighted_10"] / c, 2),
                "gpa4": round(sm["weighted_4"] / c, 2),
                "credits": sm["credits"],
                "passed_credits": sm["passed_credits"],
                "failed_credits": sm["failed_credits"],
                "subjects": sm["subjects"],
            }
        )

    cum_gpa10 = round(total_weighted_10 / total_credits, 2) if total_credits > 0 else 0.0
    cum_gpa4 = round(total_weighted_4 / total_credits, 2) if total_credits > 0 else 0.0

    # Đánh giá mức cảnh báo học vụ
    warning_level = 0
    warning_label = "Bình thường"
    warning_reason = ""
    if total_credits > 0:
        if cum_gpa4 < 1.2 or failed_credits >= 7:
            warning_level = 2
            warning_label = "Cảnh báo mức 2"
            reasons = []
            if cum_gpa4 < 1.2:
                reasons.append(f"GPA tích lũy hệ 4 thấp ({cum_gpa4:.2f} < 1.20)")
            if failed_credits >= 7:
                reasons.append(f"Nợ {failed_credits} tín chỉ không đạt")
            warning_reason = "; ".join(reasons)
        elif cum_gpa4 < 2.0 or failed_credits >= 3:
            warning_level = 1
            warning_label = "Cảnh báo mức 1"
            reasons = []
            if cum_gpa4 < 2.0:
                reasons.append(f"GPA tích lũy hệ 4 dưới ngưỡng ({cum_gpa4:.2f} < 2.00)")
            if failed_credits >= 3:
                reasons.append(f"Có {failed_credits} tín chỉ chưa đạt trong kỳ")
            warning_reason = "; ".join(reasons)

    latest_semester = semester_list[-1]["semester"] if semester_list else "HK1-2026"
    return {
        "cumulative_gpa10": cum_gpa10,
        "cumulative_gpa4": cum_gpa4,
        "total_credits": total_credits,
        "passed_credits": passed_credits,
        "failed_credits": failed_credits,
        "warning_level": warning_level,
        "warning_label": warning_label,
        "warning_reason": warning_reason,
        "latest_semester": latest_semester,
        "semesters": semester_list,
        "scores": detailed_rows,
    }


def compute_all_warnings(db: DBConnectionWrapper) -> List[Dict[str, Any]]:
    students = db.fetchall_dict(
        """
        SELECT st.id, st.student_code, st.full_name, st.email, c.class_code, c.class_name, c.homeroom_teacher
        FROM students st
        JOIN classes c ON st.class_id = c.id
        ORDER BY st.id ASC
        """
    )
    records_map = {
        r["student_id"]: r
        for r in db.fetchall_dict("SELECT * FROM warning_records")
    }
    warnings: List[Dict[str, Any]] = []
    for st in students:
        summary = compute_student_academic_summary(db, st["id"])
        if summary["warning_level"] > 0:
            rec = records_map.get(st["id"], {})
            warnings.append(
                {
                    "student_id": st["id"],
                    "student_code": st["student_code"],
                    "full_name": st["full_name"],
                    "class_code": st["class_code"],
                    "class_name": st["class_name"],
                    "homeroom_teacher": st["homeroom_teacher"],
                    "gpa10": summary["cumulative_gpa10"],
                    "gpa4": summary["cumulative_gpa4"],
                    "failed_credits": summary["failed_credits"],
                    "passed_credits": summary["passed_credits"],
                    "warning_level": summary["warning_level"],
                    "warning_label": summary["warning_label"],
                    "reason": summary["warning_reason"],
                    "semester": summary["latest_semester"],
                    "handling_status": rec.get("handling_status", "Chờ xử lý"),
                    "advisor_note": rec.get("advisor_note", ""),
                    "updated_at": rec.get("updated_at", ""),
                }
            )
    return warnings


# ==============================================================================
# 6. KHỞI TẠO FASTAPI APP & CÁC API XÁC THỰC / PHÂN QUYỀN 3 ĐỐI TƯỢNG
# ==============================================================================
app = FastAPI(
    title="Hệ thống Quản lý Sinh viên và Đào tạo Đại học",
    description="RESTful API Backend FastAPI + SQL Server/SQLite + RBAC 3 đối tượng (Phòng Đào tạo / Giảng viên / Sinh viên).",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _serialize_account(row: Dict[str, Any]) -> Dict[str, Any]:
    role = row["role"]
    meta = ROLE_METADATA.get(role, ROLE_METADATA["STUDENT"])
    assigned = [c.strip() for c in (row.get("assigned_classes") or "").split(",") if c.strip()]
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": role,
        "role_label": meta["label"],
        "role_short": meta["short_label"],
        "email": row.get("email"),
        "department": row.get("department"),
        "student_id": row.get("student_id"),
        "assigned_classes": assigned,
        "is_active": bool(row.get("is_active", 1)),
        "permissions": meta["permissions"],
    }


@app.post("/api/auth/login", tags=["Authentication"], summary="Đăng nhập theo 3 đối tượng")
def login(payload: LoginRequest, db: DBConnectionWrapper = Depends(get_db)):
    row = db.fetchone_dict(
        "SELECT * FROM app_accounts WHERE LOWER(username) = LOWER(?)",
        (payload.username.strip(),),
    )
    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác.",
        )
    if not row.get("is_active", 1):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản này đang bị khóa. Vui lòng liên hệ Phòng Đào tạo.",
        )
    if payload.expected_role and payload.expected_role.upper() != row["role"]:
        role_vn = ROLE_METADATA.get(row["role"], {}).get("short_label", row["role"])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tài khoản '{row['username']}' thuộc đối tượng {role_vn}, không khớp cổng đăng nhập đã chọn.",
        )

    user_info = _serialize_account(row)
    token = secrets.token_urlsafe(32)
    ACTIVE_SESSIONS[token] = user_info
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_info,
    }


@app.get("/api/auth/me", tags=["Authentication"], summary="Thông tin tài khoản đang đăng nhập")
def get_me(user: Dict[str, Any] = Depends(require_authenticated_user)):
    return user


@app.post("/api/auth/logout", tags=["Authentication"], summary="Đăng xuất phiên hiện tại")
def logout(authorization: Optional[str] = Header(default=None)):
    if authorization and " " in authorization:
        token = authorization.split(" ", 1)[1].strip()
        ACTIVE_SESSIONS.pop(token, None)
    return {"message": "Đã đăng xuất thành công"}


@app.get("/api/auth/accounts", tags=["Authentication"], summary="Danh sách tài khoản 3 đối tượng (Admin)")
def list_accounts(
    role: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(require_authenticated_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "xem danh sách tài khoản hệ thống")
    if role:
        rows = db.fetchall_dict(
            "SELECT * FROM app_accounts WHERE role = ? ORDER BY id ASC", (role.upper(),)
        )
    else:
        rows = db.fetchall_dict("SELECT * FROM app_accounts ORDER BY id ASC")
    return [_serialize_account(r) for r in rows]


@app.post(
    "/api/auth/accounts",
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"],
    summary="Tạo tài khoản mới cho 3 đối tượng (Admin)",
)
def create_account(
    payload: AccountCreate,
    user: Dict[str, Any] = Depends(require_authenticated_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "tạo tài khoản hệ thống")
    dup = db.fetchone_dict(
        "SELECT id FROM app_accounts WHERE LOWER(username) = LOWER(?)",
        (payload.username.strip(),),
    )
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tên đăng nhập '{payload.username}' đã tồn tại.",
        )
    new_id = db.insert_and_get_id(
        """
        INSERT INTO app_accounts
        (username, password_hash, full_name, role, email, department, student_id, assigned_classes, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            payload.username.strip(),
            hash_password(payload.password),
            payload.full_name.strip(),
            payload.role,
            payload.email,
            payload.department,
            payload.student_id,
            payload.assigned_classes or ("ALL" if payload.role == "ADMIN" else ""),
        ),
    )
    db.commit()
    row = db.fetchone_dict("SELECT * FROM app_accounts WHERE id = ?", (new_id,))
    return _serialize_account(row)


@app.patch(
    "/api/auth/accounts/{account_id}",
    tags=["Authentication"],
    summary="Cập nhật / khóa / mở khóa tài khoản (Admin)",
)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    user: Dict[str, Any] = Depends(require_authenticated_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "cập nhật phân quyền tài khoản")
    row = db.fetchone_dict("SELECT * FROM app_accounts WHERE id = ?", (account_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    data = payload.model_dump(exclude_unset=True)
    if row["username"] == "admin" and data.get("is_active") is False:
        raise HTTPException(status_code=400, detail="Không thể khóa tài khoản quản trị mặc định 'admin'")

    fields = []
    vals: List[Any] = []
    if "full_name" in data and data["full_name"] is not None:
        fields.append("full_name = ?")
        vals.append(data["full_name"].strip())
    if "role" in data and data["role"] is not None:
        fields.append("role = ?")
        vals.append(data["role"].strip().upper())
    if "department" in data:
        fields.append("department = ?")
        vals.append(data["department"])
    if "assigned_classes" in data:
        fields.append("assigned_classes = ?")
        vals.append(data["assigned_classes"])
    if "is_active" in data and data["is_active"] is not None:
        fields.append("is_active = ?")
        vals.append(1 if data["is_active"] else 0)
    if "password" in data and data["password"]:
        fields.append("password_hash = ?")
        vals.append(hash_password(data["password"]))

    if fields:
        vals.append(account_id)
        db.execute(f"UPDATE app_accounts SET {', '.join(fields)} WHERE id = ?", tuple(vals))
        db.commit()

    updated = db.fetchone_dict("SELECT * FROM app_accounts WHERE id = ?", (account_id,))
    return _serialize_account(updated)


# ==============================================================================
# 7. API THỐNG KÊ DASHBOARD TỔNG QUAN (/api/stats)
# ==============================================================================
@app.get("/api/stats", tags=["Dashboard"], summary="Lấy thống kê tổng quan cho Dashboard")
def get_dashboard_stats(
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    total_classes = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM classes")["cnt"]
    total_students = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM students")["cnt"]
    total_subjects = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM subjects")["cnt"]
    total_scores = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM scores")["cnt"]
    total_sections = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM course_sections")["cnt"]
    total_enrollments = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM enrollments")["cnt"]

    avg_row = db.fetchone_dict("SELECT AVG(final_score) AS avg_s FROM scores")
    avg_score = round(float(avg_row["avg_s"]), 2) if avg_row and avg_row["avg_s"] is not None else 0.0

    passed_count = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM scores WHERE final_score >= 4.0")["cnt"]
    pass_rate = round((passed_count / total_scores) * 100, 1) if total_scores > 0 else 0.0

    excellent = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM scores WHERE final_score >= 8.5")["cnt"]
    good = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM scores WHERE final_score >= 7.0 AND final_score < 8.5")["cnt"]
    average = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM scores WHERE final_score >= 5.5 AND final_score < 7.0")["cnt"]
    weak = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM scores WHERE final_score < 5.5")["cnt"]

    students_by_class = db.fetchall_dict(
        """
        SELECT c.class_code, c.class_name, COUNT(st.id) AS student_count
        FROM classes c
        LEFT JOIN students st ON st.class_id = c.id
        GROUP BY c.id, c.class_code, c.class_name
        ORDER BY c.id ASC
        """
    )

    registration_stats = db.fetchall_dict(
        """
        SELECT cs.section_code, sub.subject_name, cs.max_capacity, COUNT(e.id) AS enrolled
        FROM course_sections cs
        JOIN subjects sub ON cs.subject_id = sub.id
        LEFT JOIN enrollments e ON e.section_id = cs.id
        GROUP BY cs.id, cs.section_code, sub.subject_name, cs.max_capacity
        ORDER BY cs.id ASC
        """
    )

    recent_students = db.fetchall_dict(
        """
        SELECT st.id, st.student_code, st.full_name, st.email, c.class_code
        FROM students st
        JOIN classes c ON st.class_id = c.id
        ORDER BY st.id DESC
        """
    )[:5]

    warnings = compute_all_warnings(db)
    if user and user["role"] == "STUDENT":
        warnings = [w for w in warnings if w["student_id"] == user.get("student_id")]
    elif user and user["role"] == "LECTURER":
        assigned = user.get("assigned_classes") or []
        if assigned and "ALL" not in assigned:
            warnings = [w for w in warnings if w["class_code"] in assigned]

    personal_summary = None
    if user and user["role"] == "STUDENT" and user.get("student_id"):
        personal_summary = compute_student_academic_summary(db, int(user["student_id"]))

    return {
        "total_classes": total_classes,
        "total_students": total_students,
        "total_subjects": total_subjects,
        "total_scores": total_scores,
        "total_sections": total_sections,
        "total_enrollments": total_enrollments,
        "warning_count": len(warnings),
        "average_score": avg_score,
        "pass_rate": pass_rate,
        "distribution": {
            "excellent": excellent,
            "good": good,
            "average": average,
            "weak": weak,
        },
        "students_by_class": students_by_class,
        "registration_stats": registration_stats,
        "recent_students": recent_students,
        "warnings_preview": warnings[:5],
        "personal_summary": personal_summary,
        "database_info": {
            "server": DB_SERVER if DB_BACKEND == "mssql" else "Local FastAPI Engine",
            "database": DB_NAME if DB_BACKEND == "mssql" else SQLITE_DB_PATH.name,
            "driver": ODBC_DRIVER,
            "engine": DB_BACKEND,
        },
    }


# ==============================================================================
# 8. API QUẢN LÝ LỚP HỌC (/api/classes)
# ==============================================================================
@app.get("/api/classes", response_model=List[ClassResponse], tags=["Classes"])
def list_classes(
    search: Optional[str] = Query(None),
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    rows = db.fetchall_dict(
        """
        SELECT c.id, c.class_code, c.class_name, c.academic_year, c.homeroom_teacher,
               COUNT(st.id) AS student_count
        FROM classes c
        LEFT JOIN students st ON st.class_id = c.id
        GROUP BY c.id, c.class_code, c.class_name, c.academic_year, c.homeroom_teacher
        ORDER BY c.id ASC
        """
    )
    if search and search.strip():
        kw = search.strip().lower()
        rows = [
            r
            for r in rows
            if kw in (r["class_code"] or "").lower()
            or kw in (r["class_name"] or "").lower()
            or kw in (r["homeroom_teacher"] or "").lower()
        ]
    return rows


@app.get("/api/classes/{class_id}", response_model=ClassResponse, tags=["Classes"])
def get_class(class_id: int, db: DBConnectionWrapper = Depends(get_db)):
    row = db.fetchone_dict(
        """
        SELECT c.id, c.class_code, c.class_name, c.academic_year, c.homeroom_teacher,
               COUNT(st.id) AS student_count
        FROM classes c
        LEFT JOIN students st ON st.class_id = c.id
        WHERE c.id = ?
        GROUP BY c.id, c.class_code, c.class_name, c.academic_year, c.homeroom_teacher
        """,
        (class_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy lớp học với ID = {class_id}")
    return row


@app.post("/api/classes", response_model=ClassResponse, status_code=201, tags=["Classes"])
def create_class(
    payload: ClassCreate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "thêm lớp học mới")
    if db.fetchone_dict("SELECT id FROM classes WHERE class_code = ?", (payload.class_code,)):
        raise HTTPException(status_code=409, detail=f"Mã lớp học '{payload.class_code}' đã tồn tại trong hệ thống")
    new_id = db.insert_and_get_id(
        "INSERT INTO classes (class_code, class_name, academic_year, homeroom_teacher) VALUES (?, ?, ?, ?)",
        (payload.class_code, payload.class_name, payload.academic_year, payload.homeroom_teacher),
    )
    db.commit()
    return {
        "id": new_id,
        "class_code": payload.class_code,
        "class_name": payload.class_name,
        "academic_year": payload.academic_year,
        "homeroom_teacher": payload.homeroom_teacher,
        "student_count": 0,
    }


@app.patch("/api/classes/{class_id}", response_model=ClassResponse, tags=["Classes"])
def update_class(
    class_id: int,
    payload: ClassUpdate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "cập nhật lớp học")
    existing = db.fetchone_dict("SELECT * FROM classes WHERE id = ?", (class_id,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy lớp học với ID = {class_id}")
    data = payload.model_dump(exclude_unset=True)
    if "class_code" in data and data["class_code"] != existing["class_code"]:
        if db.fetchone_dict("SELECT id FROM classes WHERE class_code = ? AND id != ?", (data["class_code"], class_id)):
            raise HTTPException(status_code=409, detail=f"Mã lớp học '{data['class_code']}' đã tồn tại")
    if data:
        cols = ", ".join(f"{k} = ?" for k in data.keys())
        db.execute(f"UPDATE classes SET {cols} WHERE id = ?", tuple(list(data.values()) + [class_id]))
        db.commit()
    return get_class(class_id, db)


@app.delete("/api/classes/{class_id}", tags=["Classes"])
def delete_class(
    class_id: int,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "xóa lớp học")
    existing = db.fetchone_dict("SELECT * FROM classes WHERE id = ?", (class_id,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy lớp học với ID = {class_id}")
    st_cnt = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM students WHERE class_id = ?", (class_id,))["cnt"]
    if st_cnt > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Không thể xóa lớp '{existing['class_code']}' vì đang có {st_cnt} sinh viên thuộc lớp này (Ràng buộc khóa ngoại).",
        )
    db.execute("DELETE FROM classes WHERE id = ?", (class_id,))
    db.commit()
    return {"message": f"Đã xóa lớp học '{existing['class_code']}' (ID={class_id}) thành công"}


# ==============================================================================
# 9. API QUẢN LÝ SINH VIÊN (/api/students)
# ==============================================================================
def _enrich_student_row(db: DBConnectionWrapper, row: Dict[str, Any]) -> Dict[str, Any]:
    summary = compute_student_academic_summary(db, row["id"])
    return {
        "id": row["id"],
        "student_code": row["student_code"],
        "full_name": row["full_name"],
        "date_of_birth": _format_date(row["date_of_birth"]),
        "gender": row["gender"],
        "email": row["email"],
        "hometown": row.get("hometown"),
        "class_id": row["class_id"],
        "class_code": row.get("class_code"),
        "class_name": row.get("class_name"),
        "gpa10": summary["cumulative_gpa10"],
        "gpa4": summary["cumulative_gpa4"],
        "academic_status": summary["warning_label"],
    }


@app.get("/api/students", response_model=List[StudentResponse], tags=["Students"])
def list_students(
    search: Optional[str] = Query(None),
    class_id: Optional[int] = Query(None),
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    if user and user["role"] == "STUDENT":
        rows = db.fetchall_dict(
            """
            SELECT st.*, c.class_code, c.class_name
            FROM students st
            JOIN classes c ON st.class_id = c.id
            WHERE st.id = ?
            """,
            (user.get("student_id") or -1,),
        )
        return [_enrich_student_row(db, r) for r in rows]

    sql = """
        SELECT st.*, c.class_code, c.class_name
        FROM students st
        JOIN classes c ON st.class_id = c.id
        ORDER BY st.id ASC
    """
    rows = db.fetchall_dict(sql)

    if user and user["role"] == "LECTURER":
        assigned = user.get("assigned_classes") or []
        if assigned and "ALL" not in assigned:
            rows = [r for r in rows if r["class_code"] in assigned]

    if class_id is not None:
        rows = [r for r in rows if r["class_id"] == class_id]
    if search and search.strip():
        kw = search.strip().lower()
        rows = [
            r
            for r in rows
            if kw in (r["student_code"] or "").lower()
            or kw in (r["full_name"] or "").lower()
            or kw in (r["email"] or "").lower()
            or kw in (r["hometown"] or "").lower()
        ]
    return [_enrich_student_row(db, r) for r in rows]


@app.get("/api/students/{student_id}", response_model=StudentResponse, tags=["Students"])
def get_student(
    student_id: int,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    if user and user["role"] == "STUDENT" and user.get("student_id") != student_id:
        raise HTTPException(status_code=403, detail="Sinh viên chỉ có quyền xem hồ sơ của chính mình.")
    row = db.fetchone_dict(
        """
        SELECT st.*, c.class_code, c.class_name
        FROM students st
        JOIN classes c ON st.class_id = c.id
        WHERE st.id = ?
        """,
        (student_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy sinh viên với ID = {student_id}")
    return _enrich_student_row(db, row)


@app.post("/api/students", response_model=StudentResponse, status_code=201, tags=["Students"])
def create_student(
    payload: StudentCreate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "thêm sinh viên mới")
    if not db.fetchone_dict("SELECT id FROM classes WHERE id = ?", (payload.class_id,)):
        raise HTTPException(
            status_code=400,
            detail=f"Khóa ngoại không hợp lệ: Lớp học với class_id = {payload.class_id} không tồn tại",
        )
    if db.fetchone_dict("SELECT id FROM students WHERE student_code = ?", (payload.student_code,)):
        raise HTTPException(status_code=409, detail=f"Mã sinh viên '{payload.student_code}' đã tồn tại trong hệ thống")
    email_lower = payload.email.lower()
    if db.fetchone_dict("SELECT id FROM students WHERE LOWER(email) = ?", (email_lower,)):
        raise HTTPException(status_code=409, detail=f"Email '{payload.email}' đã được sử dụng bởi sinh viên khác")

    new_id = db.insert_and_get_id(
        """
        INSERT INTO students (student_code, full_name, date_of_birth, gender, email, hometown, class_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.student_code,
            payload.full_name,
            payload.date_of_birth.isoformat(),
            payload.gender,
            email_lower,
            payload.hometown,
            payload.class_id,
        ),
    )
    db.commit()
    return get_student(new_id, None, db)


@app.patch("/api/students/{student_id}", response_model=StudentResponse, tags=["Students"])
def update_student(
    student_id: int,
    payload: StudentUpdate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "cập nhật thông tin sinh viên")
    existing = db.fetchone_dict("SELECT * FROM students WHERE id = ?", (student_id,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy sinh viên với ID = {student_id}")
    data = payload.model_dump(exclude_unset=True)

    if "class_id" in data:
        if not db.fetchone_dict("SELECT id FROM classes WHERE id = ?", (data["class_id"],)):
            raise HTTPException(
                status_code=400,
                detail=f"Khóa ngoại không hợp lệ: Lớp học với class_id = {data['class_id']} không tồn tại",
            )
    if "student_code" in data and data["student_code"] != existing["student_code"]:
        if db.fetchone_dict("SELECT id FROM students WHERE student_code = ? AND id != ?", (data["student_code"], student_id)):
            raise HTTPException(status_code=409, detail=f"Mã sinh viên '{data['student_code']}' đã tồn tại")
    if "email" in data and data["email"]:
        data["email"] = data["email"].lower()
        if data["email"] != existing["email"].lower():
            if db.fetchone_dict("SELECT id FROM students WHERE LOWER(email) = ? AND id != ?", (data["email"], student_id)):
                raise HTTPException(status_code=409, detail=f"Email '{data['email']}' đã được sử dụng bởi sinh viên khác")
    if "date_of_birth" in data and data["date_of_birth"] is not None:
        data["date_of_birth"] = data["date_of_birth"].isoformat()

    if data:
        cols = ", ".join(f"{k} = ?" for k in data.keys())
        db.execute(f"UPDATE students SET {cols} WHERE id = ?", tuple(list(data.values()) + [student_id]))
        db.commit()
    return get_student(student_id, None, db)


@app.delete("/api/students/{student_id}", tags=["Students"])
def delete_student(
    student_id: int,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "xóa hồ sơ sinh viên")
    existing = db.fetchone_dict("SELECT * FROM students WHERE id = ?", (student_id,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy sinh viên với ID = {student_id}")
    sc_cnt = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM scores WHERE student_id = ?", (student_id,))["cnt"]
    if sc_cnt > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Không thể xóa sinh viên '{existing['full_name']}' ({existing['student_code']}) vì đã có {sc_cnt} bản ghi điểm thi (Ràng buộc khóa ngoại).",
        )
    db.execute("DELETE FROM enrollments WHERE student_id = ?", (student_id,))
    db.execute("DELETE FROM students WHERE id = ?", (student_id,))
    db.commit()
    return {"message": f"Đã xóa sinh viên '{existing['full_name']}' (ID={student_id}) thành công"}


# ==============================================================================
# 10. API QUẢN LÝ MÔN HỌC / HỌC PHẦN (/api/subjects)
# ==============================================================================
@app.get("/api/subjects", response_model=List[SubjectResponse], tags=["Subjects"])
def list_subjects(
    search: Optional[str] = Query(None),
    db: DBConnectionWrapper = Depends(get_db),
):
    rows = db.fetchall_dict(
        """
        SELECT sub.id, sub.subject_code, sub.subject_name, sub.credits, sub.department,
               COUNT(sc.id) AS score_count
        FROM subjects sub
        LEFT JOIN scores sc ON sc.subject_id = sub.id
        GROUP BY sub.id, sub.subject_code, sub.subject_name, sub.credits, sub.department
        ORDER BY sub.id ASC
        """
    )
    if search and search.strip():
        kw = search.strip().lower()
        rows = [
            r
            for r in rows
            if kw in (r["subject_code"] or "").lower()
            or kw in (r["subject_name"] or "").lower()
            or kw in (r["department"] or "").lower()
        ]
    return rows


@app.get("/api/subjects/{subject_id}", response_model=SubjectResponse, tags=["Subjects"])
def get_subject(subject_id: int, db: DBConnectionWrapper = Depends(get_db)):
    row = db.fetchone_dict(
        """
        SELECT sub.id, sub.subject_code, sub.subject_name, sub.credits, sub.department,
               COUNT(sc.id) AS score_count
        FROM subjects sub
        LEFT JOIN scores sc ON sc.subject_id = sub.id
        WHERE sub.id = ?
        GROUP BY sub.id, sub.subject_code, sub.subject_name, sub.credits, sub.department
        """,
        (subject_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy môn học với ID = {subject_id}")
    return row


@app.post("/api/subjects", response_model=SubjectResponse, status_code=201, tags=["Subjects"])
def create_subject(
    payload: SubjectCreate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "thêm học phần mới")
    if db.fetchone_dict("SELECT id FROM subjects WHERE subject_code = ?", (payload.subject_code,)):
        raise HTTPException(status_code=409, detail=f"Mã môn học '{payload.subject_code}' đã tồn tại trong hệ thống")
    new_id = db.insert_and_get_id(
        "INSERT INTO subjects (subject_code, subject_name, credits, department) VALUES (?, ?, ?, ?)",
        (payload.subject_code, payload.subject_name, payload.credits, payload.department),
    )
    db.commit()
    return {
        "id": new_id,
        "subject_code": payload.subject_code,
        "subject_name": payload.subject_name,
        "credits": payload.credits,
        "department": payload.department,
        "score_count": 0,
    }


@app.patch("/api/subjects/{subject_id}", response_model=SubjectResponse, tags=["Subjects"])
def update_subject(
    subject_id: int,
    payload: SubjectUpdate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "cập nhật học phần")
    existing = db.fetchone_dict("SELECT * FROM subjects WHERE id = ?", (subject_id,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy môn học với ID = {subject_id}")
    data = payload.model_dump(exclude_unset=True)
    if "subject_code" in data and data["subject_code"] != existing["subject_code"]:
        if db.fetchone_dict("SELECT id FROM subjects WHERE subject_code = ? AND id != ?", (data["subject_code"], subject_id)):
            raise HTTPException(status_code=409, detail=f"Mã môn học '{data['subject_code']}' đã tồn tại")
    if data:
        cols = ", ".join(f"{k} = ?" for k in data.keys())
        db.execute(f"UPDATE subjects SET {cols} WHERE id = ?", tuple(list(data.values()) + [subject_id]))
        db.commit()
    return get_subject(subject_id, db)


@app.delete("/api/subjects/{subject_id}", tags=["Subjects"])
def delete_subject(
    subject_id: int,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "xóa học phần")
    existing = db.fetchone_dict("SELECT * FROM subjects WHERE id = ?", (subject_id,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy môn học với ID = {subject_id}")
    sc_cnt = db.fetchone_dict("SELECT COUNT(*) AS cnt FROM scores WHERE subject_id = ?", (subject_id,))["cnt"]
    if sc_cnt > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Không thể xóa môn học '{existing['subject_code']}' vì đã có {sc_cnt} bản ghi điểm thi (Ràng buộc khóa ngoại).",
        )
    db.execute("DELETE FROM curriculum_items WHERE subject_id = ?", (subject_id,))
    db.execute("DELETE FROM course_sections WHERE subject_id = ?", (subject_id,))
    db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    db.commit()
    return {"message": f"Đã xóa môn học '{existing['subject_code']}' (ID={subject_id}) thành công"}


# ==============================================================================
# 11. API QUẢN LÝ ĐIỂM THI (/api/scores)
# ==============================================================================
def _serialize_score_row(r: Dict[str, Any]) -> Dict[str, Any]:
    final_s = float(r["final_score"])
    letter, gpa4 = convert_to_letter_and_gpa4(final_s)
    return {
        "id": r["id"],
        "student_id": r["student_id"],
        "student_code": r["student_code"],
        "student_name": r["student_name"],
        "class_code": r.get("class_code"),
        "subject_id": r["subject_id"],
        "subject_code": r["subject_code"],
        "subject_name": r["subject_name"],
        "credits": int(r["credits"]),
        "semester": r["semester"],
        "process_score": float(r["process_score"]),
        "exam_score": float(r["exam_score"]),
        "final_score": final_s,
        "letter_grade": letter,
        "gpa4_score": gpa4,
        "grade_rank": classify_grade(final_s),
        "passed": final_s >= 4.0,
    }


@app.get("/api/scores", response_model=List[ScoreResponse], tags=["Scores"])
def list_scores(
    search: Optional[str] = Query(None),
    student_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    semester: Optional[str] = Query(None),
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    rows = db.fetchall_dict(
        """
        SELECT sc.*, st.student_code, st.full_name AS student_name, c.class_code,
               sub.subject_code, sub.subject_name, sub.credits
        FROM scores sc
        JOIN students st ON sc.student_id = st.id
        JOIN classes c ON st.class_id = c.id
        JOIN subjects sub ON sc.subject_id = sub.id
        ORDER BY sc.id ASC
        """
    )
    if user and user["role"] == "STUDENT":
        rows = [r for r in rows if r["student_id"] == user.get("student_id")]
    elif user and user["role"] == "LECTURER":
        assigned = user.get("assigned_classes") or []
        if assigned and "ALL" not in assigned:
            rows = [r for r in rows if r["class_code"] in assigned]

    if student_id is not None:
        rows = [r for r in rows if r["student_id"] == student_id]
    if subject_id is not None:
        rows = [r for r in rows if r["subject_id"] == subject_id]
    if semester and semester.strip():
        sem_up = semester.strip().upper()
        rows = [r for r in rows if (r["semester"] or "").upper() == sem_up]
    if search and search.strip():
        kw = search.strip().lower()
        rows = [
            r
            for r in rows
            if kw in (r["student_code"] or "").lower()
            or kw in (r["student_name"] or "").lower()
            or kw in (r["subject_code"] or "").lower()
            or kw in (r["subject_name"] or "").lower()
            or kw in (r["semester"] or "").lower()
        ]
    return [_serialize_score_row(r) for r in rows]


@app.get("/api/scores/{score_id}", response_model=ScoreResponse, tags=["Scores"])
def get_score(score_id: int, db: DBConnectionWrapper = Depends(get_db)):
    row = db.fetchone_dict(
        """
        SELECT sc.*, st.student_code, st.full_name AS student_name, c.class_code,
               sub.subject_code, sub.subject_name, sub.credits
        FROM scores sc
        JOIN students st ON sc.student_id = st.id
        JOIN classes c ON st.class_id = c.id
        JOIN subjects sub ON sc.subject_id = sub.id
        WHERE sc.id = ?
        """,
        (score_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản ghi điểm thi với ID = {score_id}")
    return _serialize_score_row(row)


@app.post("/api/scores", response_model=ScoreResponse, status_code=201, tags=["Scores"])
def create_score(
    payload: ScoreCreate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN", "LECTURER"], "nhập điểm thi")
    st = db.fetchone_dict(
        "SELECT st.*, c.class_code FROM students st JOIN classes c ON st.class_id = c.id WHERE st.id = ?",
        (payload.student_id,),
    )
    if not st:
        raise HTTPException(
            status_code=400,
            detail=f"Khóa ngoại không hợp lệ: Sinh viên với student_id = {payload.student_id} không tồn tại",
        )
    if user and user["role"] == "LECTURER":
        assigned = user.get("assigned_classes") or []
        if assigned and "ALL" not in assigned and st["class_code"] not in assigned:
            raise HTTPException(
                status_code=403,
                detail=f"Giảng viên không được phân công nhập điểm cho lớp {st['class_code']}.",
            )
    sub = db.fetchone_dict("SELECT * FROM subjects WHERE id = ?", (payload.subject_id,))
    if not sub:
        raise HTTPException(
            status_code=400,
            detail=f"Khóa ngoại không hợp lệ: Môn học với subject_id = {payload.subject_id} không tồn tại",
        )
    dup = db.fetchone_dict(
        "SELECT id FROM scores WHERE student_id = ? AND subject_id = ? AND semester = ?",
        (payload.student_id, payload.subject_id, payload.semester),
    )
    if dup:
        raise HTTPException(
            status_code=409,
            detail=f"Sinh viên '{st['student_code']}' đã có điểm môn '{sub['subject_code']}' trong học kỳ '{payload.semester}'",
        )

    final_score = calculate_final_score(payload.process_score, payload.exam_score)
    new_id = db.insert_and_get_id(
        """
        INSERT INTO scores (student_id, subject_id, semester, process_score, exam_score, final_score)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payload.student_id,
            payload.subject_id,
            payload.semester,
            round(payload.process_score, 2),
            round(payload.exam_score, 2),
            final_score,
        ),
    )
    db.commit()
    return get_score(new_id, db)


@app.patch("/api/scores/{score_id}", response_model=ScoreResponse, tags=["Scores"])
def update_score(
    score_id: int,
    payload: ScoreUpdate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN", "LECTURER"], "cập nhật điểm thi")
    existing = db.fetchone_dict("SELECT * FROM scores WHERE id = ?", (score_id,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản ghi điểm thi với ID = {score_id}")

    data = payload.model_dump(exclude_unset=True)
    target_st = data.get("student_id", existing["student_id"])
    target_sub = data.get("subject_id", existing["subject_id"])
    target_sem = data.get("semester", existing["semester"])

    if "student_id" in data:
        if not db.fetchone_dict("SELECT id FROM students WHERE id = ?", (target_st,)):
            raise HTTPException(status_code=400, detail=f"Khóa ngoại không hợp lệ: student_id = {target_st} không tồn tại")
    if "subject_id" in data:
        if not db.fetchone_dict("SELECT id FROM subjects WHERE id = ?", (target_sub,)):
            raise HTTPException(status_code=400, detail=f"Khóa ngoại không hợp lệ: subject_id = {target_sub} không tồn tại")

    dup = db.fetchone_dict(
        "SELECT id FROM scores WHERE student_id = ? AND subject_id = ? AND semester = ? AND id != ?",
        (target_st, target_sub, target_sem, score_id),
    )
    if dup:
        raise HTTPException(status_code=409, detail="Bản ghi điểm cho sinh viên, môn học và học kỳ này đã tồn tại")

    proc = round(float(data.get("process_score", existing["process_score"])), 2)
    exam = round(float(data.get("exam_score", existing["exam_score"])), 2)
    final_val = calculate_final_score(proc, exam)

    db.execute(
        """
        UPDATE scores
        SET student_id = ?, subject_id = ?, semester = ?, process_score = ?, exam_score = ?, final_score = ?
        WHERE id = ?
        """,
        (target_st, target_sub, target_sem, proc, exam, final_val, score_id),
    )
    db.commit()
    return get_score(score_id, db)


@app.delete("/api/scores/{score_id}", tags=["Scores"])
def delete_score(
    score_id: int,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "xóa bản ghi điểm thi")
    existing = db.fetchone_dict("SELECT id FROM scores WHERE id = ?", (score_id,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản ghi điểm thi với ID = {score_id}")
    db.execute("DELETE FROM scores WHERE id = ?", (score_id,))
    db.commit()
    return {"message": f"Đã xóa bản ghi điểm thi (ID={score_id}) thành công"}


# ==============================================================================
# 12. API CHƯƠNG TRÌNH ĐÀO TẠO, ĐĂNG KÝ HỌC PHẦN, KẾT QUẢ GPA & CẢNH BÁO HỌC VỤ
# ==============================================================================
@app.get("/api/curriculum", tags=["Training"])
def list_curriculum(
    major: Optional[str] = Query(None),
    cohort: Optional[str] = Query(None),
    db: DBConnectionWrapper = Depends(get_db),
):
    rows = db.fetchall_dict(
        """
        SELECT ci.*, sub.subject_code, sub.subject_name, sub.credits, sub.department
        FROM curriculum_items ci
        JOIN subjects sub ON ci.subject_id = sub.id
        ORDER BY ci.major_name ASC, ci.semester_plan ASC, ci.id ASC
        """
    )
    if major and major.strip():
        rows = [r for r in rows if r["major_name"] == major.strip()]
    if cohort and cohort.strip():
        rows = [r for r in rows if r["cohort"] == cohort.strip()]
    return rows


@app.post("/api/curriculum", status_code=201, tags=["Training"])
def add_curriculum_item(
    payload: CurriculumCreate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "thêm học phần vào chương trình đào tạo")
    if not db.fetchone_dict("SELECT id FROM subjects WHERE id = ?", (payload.subject_id,)):
        raise HTTPException(status_code=400, detail="Học phần không tồn tại")
    new_id = db.insert_and_get_id(
        """
        INSERT INTO curriculum_items
        (major_name, cohort, subject_id, semester_plan, course_group, prerequisite_code)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payload.major_name.strip(),
            payload.cohort.strip(),
            payload.subject_id,
            payload.semester_plan,
            payload.course_group.strip(),
            payload.prerequisite_code.strip().upper() if payload.prerequisite_code else None,
        ),
    )
    db.commit()
    return {"id": new_id, "message": "Đã thêm học phần vào chương trình đào tạo"}


@app.get("/api/sections", tags=["Registration"])
def list_sections(
    semester: Optional[str] = Query(None),
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    rows = db.fetchall_dict(
        """
        SELECT cs.*, sub.subject_code, sub.subject_name, sub.credits, sub.department,
               COUNT(e.id) AS enrolled_count
        FROM course_sections cs
        JOIN subjects sub ON cs.subject_id = sub.id
        LEFT JOIN enrollments e ON e.section_id = cs.id
        GROUP BY cs.id, cs.section_code, cs.subject_id, cs.semester, cs.lecturer_name,
                 cs.schedule_text, cs.room, cs.max_capacity, cs.prerequisite_code,
                 cs.registration_open, sub.subject_code, sub.subject_name, sub.credits, sub.department
        ORDER BY cs.id ASC
        """
    )
    if semester and semester.strip():
        rows = [r for r in rows if r["semester"] == semester.strip().upper()]

    enrolled_ids = set()
    passed_codes = set()
    target_st_id = user.get("student_id") if user and user["role"] == "STUDENT" else None
    if target_st_id:
        for e in db.fetchall_dict("SELECT section_id FROM enrollments WHERE student_id = ?", (target_st_id,)):
            enrolled_ids.add(e["section_id"])
        for s in db.fetchall_dict(
            """
            SELECT sub.subject_code FROM scores sc
            JOIN subjects sub ON sc.subject_id = sub.id
            WHERE sc.student_id = ? AND sc.final_score >= 4.0
            """,
            (target_st_id,),
        ):
            passed_codes.add(s["subject_code"])

    result = []
    for r in rows:
        remaining = max(0, int(r["max_capacity"]) - int(r["enrolled_count"]))
        prereq = r.get("prerequisite_code")
        prereq_met = True if (not prereq or not target_st_id) else (prereq in passed_codes)
        result.append(
            {
                **r,
                "remaining_slots": remaining,
                "is_enrolled": r["id"] in enrolled_ids,
                "prerequisite_met": prereq_met,
            }
        )
    return result


@app.post("/api/sections", status_code=201, tags=["Registration"])
def create_section(
    payload: SectionCreate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN"], "mở lớp học phần mới")
    if not db.fetchone_dict("SELECT id FROM subjects WHERE id = ?", (payload.subject_id,)):
        raise HTTPException(status_code=400, detail="Học phần không tồn tại")
    if db.fetchone_dict("SELECT id FROM course_sections WHERE section_code = ?", (payload.section_code.upper(),)):
        raise HTTPException(status_code=409, detail=f"Mã lớp học phần '{payload.section_code}' đã tồn tại")
    new_id = db.insert_and_get_id(
        """
        INSERT INTO course_sections
        (section_code, subject_id, semester, lecturer_name, schedule_text, room, max_capacity, prerequisite_code, registration_open)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            payload.section_code.strip().upper(),
            payload.subject_id,
            payload.semester.strip().upper(),
            payload.lecturer_name.strip(),
            payload.schedule_text.strip(),
            payload.room.strip(),
            payload.max_capacity,
            payload.prerequisite_code.strip().upper() if payload.prerequisite_code else None,
        ),
    )
    db.commit()
    return {"id": new_id, "message": "Đã mở lớp học phần mới thành công"}


@app.get("/api/enrollments", tags=["Registration"])
def list_enrollments(
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    rows = db.fetchall_dict(
        """
        SELECT e.id, e.student_id, e.section_id, e.registered_at, e.status,
               st.student_code, st.full_name AS student_name,
               cs.section_code, cs.semester, cs.lecturer_name, cs.schedule_text, cs.room,
               sub.subject_code, sub.subject_name, sub.credits
        FROM enrollments e
        JOIN students st ON e.student_id = st.id
        JOIN course_sections cs ON e.section_id = cs.id
        JOIN subjects sub ON cs.subject_id = sub.id
        ORDER BY e.id DESC
        """
    )
    if user and user["role"] == "STUDENT":
        rows = [r for r in rows if r["student_id"] == user.get("student_id")]
    return rows


@app.post("/api/enrollments", status_code=201, tags=["Registration"])
def register_course_section(
    payload: EnrollmentCreate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN", "STUDENT"], "đăng ký học phần")
    target_student_id = payload.student_id
    if user and user["role"] == "STUDENT":
        target_student_id = user.get("student_id")
    if not target_student_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn sinh viên đăng ký học phần.")

    sec = db.fetchone_dict(
        """
        SELECT cs.*, sub.subject_code, sub.subject_name, COUNT(e.id) AS enrolled_count
        FROM course_sections cs
        JOIN subjects sub ON cs.subject_id = sub.id
        LEFT JOIN enrollments e ON e.section_id = cs.id
        WHERE cs.id = ?
        GROUP BY cs.id, cs.section_code, cs.subject_id, cs.semester, cs.lecturer_name,
                 cs.schedule_text, cs.room, cs.max_capacity, cs.prerequisite_code,
                 cs.registration_open, sub.subject_code, sub.subject_name
        """,
        (payload.section_id,),
    )
    if not sec:
        raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần.")
    if int(sec["enrolled_count"]) >= int(sec["max_capacity"]):
        raise HTTPException(status_code=400, detail=f"Lớp {sec['section_code']} đã hết sĩ số ({sec['max_capacity']}/{sec['max_capacity']}).")

    # Kiểm tra trùng đăng ký
    dup = db.fetchone_dict(
        "SELECT id FROM enrollments WHERE student_id = ? AND section_id = ?",
        (target_student_id, payload.section_id),
    )
    if dup:
        raise HTTPException(status_code=409, detail=f"Bạn đã đăng ký lớp học phần {sec['section_code']} trước đó.")

    # Kiểm tra học phần tiên quyết
    prereq = sec.get("prerequisite_code")
    if prereq:
        passed_prereq = db.fetchone_dict(
            """
            SELECT sc.id FROM scores sc
            JOIN subjects sub ON sc.subject_id = sub.id
            WHERE sc.student_id = ? AND sub.subject_code = ? AND sc.final_score >= 4.0
            """,
            (target_student_id, prereq),
        )
        if not passed_prereq:
            raise HTTPException(
                status_code=400,
                detail=f"Không đủ điều kiện tiên quyết: Cần hoàn thành đạt học phần {prereq} trước khi đăng ký {sec['subject_code']}.",
            )

    new_id = db.insert_and_get_id(
        "INSERT INTO enrollments (student_id, section_id, registered_at, status) VALUES (?, ?, ?, ?)",
        (target_student_id, payload.section_id, datetime.now().strftime("%Y-%m-%d %H:%M"), "Đã đăng ký"),
    )
    db.commit()
    return {"id": new_id, "message": f"Đăng ký thành công lớp {sec['section_code']} ({sec['subject_name']})"}


@app.delete("/api/enrollments/{enrollment_id}", tags=["Registration"])
def cancel_enrollment(
    enrollment_id: int,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN", "STUDENT"], "hủy đăng ký học phần")
    rec = db.fetchone_dict("SELECT * FROM enrollments WHERE id = ?", (enrollment_id,))
    if not rec:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiếu đăng ký học phần.")
    if user and user["role"] == "STUDENT" and rec["student_id"] != user.get("student_id"):
        raise HTTPException(status_code=403, detail="Không thể hủy đăng ký học phần của sinh viên khác.")
    db.execute("DELETE FROM enrollments WHERE id = ?", (enrollment_id,))
    db.commit()
    return {"message": "Đã hủy đăng ký học phần thành công"}


@app.get("/api/results", tags=["Academic Results"])
def get_academic_results(
    student_id: Optional[int] = Query(None),
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    students = db.fetchall_dict(
        """
        SELECT st.id, st.student_code, st.full_name, c.class_code, c.class_name
        FROM students st
        JOIN classes c ON st.class_id = c.id
        ORDER BY st.id ASC
        """
    )
    if user and user["role"] == "STUDENT":
        target_id = user.get("student_id")
        students = [s for s in students if s["id"] == target_id]
    elif user and user["role"] == "LECTURER":
        assigned = user.get("assigned_classes") or []
        if assigned and "ALL" not in assigned:
            students = [s for s in students if s["class_code"] in assigned]

    if student_id is not None:
        students = [s for s in students if s["id"] == student_id]

    if not students:
        return {"students": [], "selected": None}

    selected_st = students[0]
    summary = compute_student_academic_summary(db, selected_st["id"])
    return {
        "students": students,
        "selected": {
            **selected_st,
            **summary,
        },
    }


@app.get("/api/warnings", tags=["Academic Warnings"])
def list_academic_warnings(
    level: Optional[int] = Query(None),
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    warnings = compute_all_warnings(db)
    if user and user["role"] == "STUDENT":
        warnings = [w for w in warnings if w["student_id"] == user.get("student_id")]
    elif user and user["role"] == "LECTURER":
        assigned = user.get("assigned_classes") or []
        if assigned and "ALL" not in assigned:
            warnings = [w for w in warnings if w["class_code"] in assigned]
    if level is not None:
        warnings = [w for w in warnings if w["warning_level"] == level]

    level1 = sum(1 for w in warnings if w["warning_level"] == 1)
    level2 = sum(1 for w in warnings if w["warning_level"] == 2)
    resolved = sum(1 for w in warnings if w["handling_status"] == "Đã tư vấn học vụ")
    return {
        "summary": {
            "total": len(warnings),
            "level1": level1,
            "level2": level2,
            "resolved": resolved,
        },
        "items": warnings,
    }


@app.patch("/api/warnings/{student_id}", tags=["Academic Warnings"])
def update_warning_status(
    student_id: int,
    payload: WarningUpdate,
    user: Optional[Dict[str, Any]] = Depends(_parse_optional_user),
    db: DBConnectionWrapper = Depends(get_db),
):
    enforce_roles(user, ["ADMIN", "LECTURER"], "cập nhật trạng thái xử lý cảnh báo học vụ")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing = db.fetchone_dict("SELECT student_id FROM warning_records WHERE student_id = ?", (student_id,))
    if existing:
        db.execute(
            "UPDATE warning_records SET handling_status = ?, advisor_note = ?, updated_at = ? WHERE student_id = ?",
            (payload.handling_status.strip(), payload.advisor_note or "", now_str, student_id),
        )
    else:
        db.execute(
            "INSERT INTO warning_records (student_id, handling_status, advisor_note, updated_at) VALUES (?, ?, ?, ?)",
            (student_id, payload.handling_status.strip(), payload.advisor_note or "", now_str),
        )
    db.commit()
    return {"message": "Đã cập nhật trạng thái xử lý cảnh báo học vụ thành công"}


# ==============================================================================
# 13. PHỤC VỤ GIAO DIỆN FRONTEND TẠI "/" BẰNG STATICFILES
# ==============================================================================
@app.get("/", include_in_schema=False)
@app.get("/login", include_in_schema=False)
def serve_root():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="root_static")
