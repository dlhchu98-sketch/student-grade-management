import os
import urllib.parse
from datetime import date
from pathlib import Path
from typing import List, Optional

import pyodbc
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import (
     Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Unicode,
    UniqueConstraint,
    create_engine,
    func,
    or_,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# Load biến môi trường từ file .env (nếu có)
load_dotenv()

# ==============================================================================
# 1. CẤU HÌNH KẾT NỐI SQL SERVER & KHỞI TẠO DATABASE
# ==============================================================================
DB_SERVER = os.getenv("DB_SERVER", r".\SQLEXPRESS")
DB_NAME = os.getenv("DB_NAME", "StudentGradeManagementDB")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_TRUSTED = os.getenv("DB_TRUSTED_CONNECTION", "yes").lower() in ("yes", "true", "1")


def get_best_odbc_driver() -> str:
    """Tự động phát hiện ODBC Driver cho SQL Server đã cài đặt trên máy."""
    env_driver = os.getenv("DB_DRIVER")
    if env_driver:
        return env_driver
    available = pyodbc.drivers()
    for preferred in [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server",
    ]:
        if preferred in available:
            return preferred
    return "ODBC Driver 17 for SQL Server"


ODBC_DRIVER = get_best_odbc_driver()


def build_odbc_conn_str(database: str) -> str:
    """Tạo chuỗi kết nối ODBC chuẩn cho SQL Server."""
    parts = [
        f"DRIVER={{{ODBC_DRIVER}}}",
        f"SERVER={DB_SERVER}",
        f"DATABASE={database}",
        "TrustServerCertificate=yes",
    ]
    if DB_TRUSTED and not DB_USER:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={DB_USER}")
        parts.append(f"PWD={DB_PASSWORD}")
    return ";".join(parts) + ";"


def ensure_database_exists() -> None:
    """Tự động kiểm tra và khởi tạo Database trên SQL Server nếu chưa tồn tại."""
    master_conn_str = build_odbc_conn_str("master")
    with pyodbc.connect(master_conn_str, autocommit=True) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            IF DB_ID(N'{DB_NAME}') IS NULL
            BEGIN
                CREATE DATABASE [{DB_NAME}];
            END
            """
        )


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    ensure_database_exists()
    odbc_connect = urllib.parse.quote_plus(build_odbc_conn_str(DB_NAME))
    DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={odbc_connect}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ==============================================================================
# 2. MÔ HÌNH CƠ SỞ DỮ LIỆU (SQLALCHEMY ORM MODELS)
# ==============================================================================
class ClassModel(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    class_code = Column(String(50), unique=True, nullable=False, index=True)
    class_name = Column(Unicode(100), nullable=False)
    academic_year = Column(String(30), nullable=True, default="2024-2028")
    homeroom_teacher = Column(Unicode(100), nullable=True)

    students = relationship("StudentModel", back_populates="school_class")


class StudentModel(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_code = Column(String(50), unique=True, nullable=False, index=True)
    full_name = Column(Unicode(100), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    gender = Column(Unicode(20), nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    hometown = Column(Unicode(150), nullable=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False, index=True)

    school_class = relationship("ClassModel", back_populates="students")
    scores = relationship("ScoreModel", back_populates="student")


class SubjectModel(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    subject_code = Column(String(50), unique=True, nullable=False, index=True)
    subject_name = Column(Unicode(120), nullable=False)
    credits = Column(Integer, nullable=False)
    department = Column(Unicode(100), nullable=True)

    scores = relationship("ScoreModel", back_populates="subject")


class ScoreModel(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", "semester", name="uq_student_subject_semester"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    semester = Column(String(30), nullable=False, default="HK1-2026")
    process_score = Column(Float, nullable=False)
    exam_score = Column(Float, nullable=False)
    final_score = Column(Float, nullable=False)

    student = relationship("StudentModel", back_populates="scores")
    subject = relationship("SubjectModel", back_populates="scores")


# ==============================================================================
# 3. PYDANTIC SCHEMAS (KIỂM TRA DỮ LIỆU ĐẦU VÀO & ĐẦU RA)
# ==============================================================================
def calculate_final_score(process_score: float, exam_score: float) -> float:
    """Tính điểm tổng kết theo trọng số: 40% điểm quá trình + 60% điểm thi."""
    return round(process_score * 0.4 + exam_score * 0.6, 2)


def classify_grade(final_score: float) -> str:
    """Xếp loại học lực theo thang điểm 10."""
    if final_score >= 8.5:
        return "Giỏi (A)"
    if final_score >= 7.0:
        return "Khá (B)"
    if final_score >= 5.5:
        return "Trung bình (C)"
    if final_score >= 4.0:
        return "Trung bình yếu (D)"
    return "Kém / Trượt (F)"


# --- SCHEMAS LỚP HỌC ---
class ClassCreate(BaseModel):
    class_code: str = Field(..., min_length=2, max_length=50, description="Mã lớp học (duy nhất)")
    class_name: str = Field(..., min_length=2, max_length=100, description="Tên lớp học")
    academic_year: Optional[str] = Field("2024-2028", max_length=30, description="Niên khóa")
    homeroom_teacher: Optional[str] = Field(None, max_length=100, description="Giảng viên cố vấn")

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


# --- SCHEMAS SINH VIÊN ---
class StudentCreate(BaseModel):
    student_code: str = Field(..., min_length=2, max_length=50, description="Mã sinh viên (duy nhất)")
    full_name: str = Field(..., min_length=2, max_length=100, description="Họ và tên sinh viên")
    date_of_birth: date = Field(..., description="Ngày sinh (YYYY-MM-DD)")
    gender: str = Field(..., min_length=1, max_length=20, description="Giới tính (Nam/Nữ/Khác)")
    email: EmailStr = Field(..., description="Địa chỉ email hợp lệ (duy nhất)")
    hometown: Optional[str] = Field(None, max_length=150, description="Quê quán")
    class_id: int = Field(..., gt=0, description="ID lớp học (Khóa ngoại)")

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


# --- SCHEMAS MÔN HỌC ---
class SubjectCreate(BaseModel):
    subject_code: str = Field(..., min_length=2, max_length=50, description="Mã môn học (duy nhất)")
    subject_name: str = Field(..., min_length=2, max_length=120, description="Tên môn học")
    credits: int = Field(..., ge=1, le=15, description="Số tín chỉ (1 - 15)")
    department: Optional[str] = Field(None, max_length=100, description="Khoa/Bộ môn phụ trách")

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


# --- SCHEMAS ĐIỂM THI ---
class ScoreCreate(BaseModel):
    student_id: int = Field(..., gt=0, description="ID sinh viên (Khóa ngoại)")
    subject_id: int = Field(..., gt=0, description="ID môn học (Khóa ngoại)")
    semester: str = Field("HK1-2026", min_length=2, max_length=30, description="Học kỳ (VD: HK1-2026)")
    process_score: float = Field(..., ge=0.0, le=10.0, description="Điểm quá trình (0.0 - 10.0)")
    exam_score: float = Field(..., ge=0.0, le=10.0, description="Điểm thi kết thúc học phần (0.0 - 10.0)")

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
    grade_rank: str
    passed: bool


# ==============================================================================
# 4. KHỞI TẠO BẢNG & DỮ LIỆU BAN ĐẦU TRÊN SQL SERVER
# ==============================================================================
def init_db_and_seed() -> None:
    """Tạo các bảng trên SQL Server và khởi tạo dữ liệu mẫu ban đầu nếu bảng trống."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(ClassModel).count() == 0:
            classes = [
                ClassModel(
                    class_code="CNTT01-K18",
                    class_name="Công nghệ phần mềm 01 - K18",
                    academic_year="2024-2028",
                    homeroom_teacher="TS. Nguyễn Văn Minh",
                ),
                ClassModel(
                    class_code="CNTT02-K18",
                    class_name="Hệ thống thông tin 02 - K18",
                    academic_year="2024-2028",
                    homeroom_teacher="ThS. Trần Thị Thu Hà",
                ),
                ClassModel(
                    class_code="KHDL01-K18",
                    class_name="Khoa học dữ liệu & AI - K18",
                    academic_year="2024-2028",
                    homeroom_teacher="PGS.TS. Lê Hoàng Nam",
                ),
                ClassModel(
                    class_code="ATTT01-K18",
                    class_name="An toàn thông tin 01 - K18",
                    academic_year="2024-2028",
                    homeroom_teacher="TS. Phạm Quốc Bảo",
                ),
            ]
            db.add_all(classes)
            db.commit()
            for c in classes:
                db.refresh(c)

            subjects = [
                SubjectModel(
                    subject_code="IT3010",
                    subject_name="Hệ quản trị Cơ sở dữ liệu SQL Server",
                    credits=3,
                    department="Hệ thống thông tin",
                ),
                SubjectModel(
                    subject_code="IT3020",
                    subject_name="Phát triển Ứng dụng Web với FastAPI",
                    credits=3,
                    department="Công nghệ phần mềm",
                ),
                SubjectModel(
                    subject_code="IT3030",
                    subject_name="Cấu trúc dữ liệu và Giải thuật",
                    credits=4,
                    department="Khoa học máy tính",
                ),
                SubjectModel(
                    subject_code="IT3040",
                    subject_name="Trí tuệ nhân tạo & Học máy",
                    credits=3,
                    department="Khoa học dữ liệu",
                ),
                SubjectModel(
                    subject_code="IT3050",
                    subject_name="Mạng máy tính và Bảo mật",
                    credits=3,
                    department="An toàn thông tin",
                ),
            ]
            db.add_all(subjects)
            db.commit()
            for s in subjects:
                db.refresh(s)

            students = [
                StudentModel(
                    student_code="SV2024001",
                    full_name="Nguyễn Minh Quân",
                    date_of_birth=date(2005, 3, 15),
                    gender="Nam",
                    email="quan.nm24001@student.edu.vn",
                    hometown="Hà Nội",
                    class_id=classes[0].id,
                ),
                StudentModel(
                    student_code="SV2024002",
                    full_name="Trần Ngọc Ánh",
                    date_of_birth=date(2005, 7, 22),
                    gender="Nữ",
                    email="anh.tn24002@student.edu.vn",
                    hometown="Hải Phòng",
                    class_id=classes[0].id,
                ),
                StudentModel(
                    student_code="SV2024003",
                    full_name="Lê Hoàng Phúc",
                    date_of_birth=date(2005, 11, 8),
                    gender="Nam",
                    email="phuc.lh24003@student.edu.vn",
                    hometown="Đà Nẵng",
                    class_id=classes[1].id,
                ),
                StudentModel(
                    student_code="SV2024004",
                    full_name="Phạm Khánh Linh",
                    date_of_birth=date(2005, 1, 30),
                    gender="Nữ",
                    email="linh.pk24004@student.edu.vn",
                    hometown="Nam Định",
                    class_id=classes[1].id,
                ),
                StudentModel(
                    student_code="SV2024005",
                    full_name="Hoàng Đức Tuấn",
                    date_of_birth=date(2005, 5, 19),
                    gender="Nam",
                    email="tuan.hd24005@student.edu.vn",
                    hometown="Nghệ An",
                    class_id=classes[2].id,
                ),
                StudentModel(
                    student_code="SV2024006",
                    full_name="Vũ Phương Thảo",
                    date_of_birth=date(2005, 9, 12),
                    gender="Nữ",
                    email="thao.vp24006@student.edu.vn",
                    hometown="Quảng Ninh",
                    class_id=classes[3].id,
                ),
            ]
            db.add_all(students)
            db.commit()
            for st in students:
                db.refresh(st)

            sample_scores = [
                (students[0].id, subjects[0].id, "HK1-2026", 9.0, 8.5),
                (students[0].id, subjects[1].id, "HK1-2026", 8.5, 9.0),
                (students[1].id, subjects[0].id, "HK1-2026", 8.0, 7.5),
                (students[1].id, subjects[2].id, "HK1-2026", 7.5, 8.0),
                (students[2].id, subjects[0].id, "HK1-2026", 6.5, 7.0),
                (students[3].id, subjects[1].id, "HK1-2026", 9.5, 9.0),
                (students[4].id, subjects[3].id, "HK1-2026", 8.0, 8.5),
                (students[5].id, subjects[4].id, "HK1-2026", 5.5, 6.0),
            ]
            for st_id, sub_id, sem, proc, exam in sample_scores:
                db.add(
                    ScoreModel(
                        student_id=st_id,
                        subject_id=sub_id,
                        semester=sem,
                        process_score=proc,
                        exam_score=exam,
                        final_score=calculate_final_score(proc, exam),
                    )
                )
            db.commit()
    finally:
        db.close()


init_db_and_seed()


# ==============================================================================
# 5. KHỞI TẠO ỨNG DỤNG FASTAPI & DEPENDENCY
# ==============================================================================
app = FastAPI(
    title="Hệ thống Quản lý Sinh viên và Điểm thi",
    description="RESTful API Backend sử dụng FastAPI, SQL Server (SQLAlchemy + pyodbc) và Pydantic Validation.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_student(st: StudentModel) -> dict:
    return {
        "id": st.id,
        "student_code": st.student_code,
        "full_name": st.full_name,
        "date_of_birth": st.date_of_birth,
        "gender": st.gender,
        "email": st.email,
        "hometown": st.hometown,
        "class_id": st.class_id,
        "class_code": st.school_class.class_code if st.school_class else None,
        "class_name": st.school_class.class_name if st.school_class else None,
    }


def serialize_score(sc: ScoreModel) -> dict:
    return {
        "id": sc.id,
        "student_id": sc.student_id,
        "student_code": sc.student.student_code if sc.student else "",
        "student_name": sc.student.full_name if sc.student else "",
        "class_code": (
            sc.student.school_class.class_code
            if sc.student and sc.student.school_class
            else None
        ),
        "subject_id": sc.subject_id,
        "subject_code": sc.subject.subject_code if sc.subject else "",
        "subject_name": sc.subject.subject_name if sc.subject else "",
        "credits": sc.subject.credits if sc.subject else 0,
        "semester": sc.semester,
        "process_score": sc.process_score,
        "exam_score": sc.exam_score,
        "final_score": sc.final_score,
        "grade_rank": classify_grade(sc.final_score),
        "passed": sc.final_score >= 4.0,
    }


# ==============================================================================
# 6. API THỐNG KÊ DASHBOARD TỔNG QUAN
# ==============================================================================
@app.get("/api/stats", tags=["Dashboard"], summary="Lấy thống kê tổng quan cho Dashboard")
def get_dashboard_stats(db: Session = Depends(get_db)):
    total_classes = db.query(func.count(ClassModel.id)).scalar() or 0
    total_students = db.query(func.count(StudentModel.id)).scalar() or 0
    total_subjects = db.query(func.count(SubjectModel.id)).scalar() or 0
    total_scores = db.query(func.count(ScoreModel.id)).scalar() or 0

    avg_score_val = db.query(func.avg(ScoreModel.final_score)).scalar()
    avg_score = round(float(avg_score_val), 2) if avg_score_val is not None else 0.0

    passed_count = (
        db.query(func.count(ScoreModel.id)).filter(ScoreModel.final_score >= 4.0).scalar()
        or 0
    )
    pass_rate = round((passed_count / total_scores) * 100, 1) if total_scores > 0 else 0.0

    excellent_count = (
        db.query(func.count(ScoreModel.id)).filter(ScoreModel.final_score >= 8.5).scalar() or 0
    )
    good_count = (
        db.query(func.count(ScoreModel.id))
        .filter(ScoreModel.final_score >= 7.0, ScoreModel.final_score < 8.5)
        .scalar()
        or 0
    )
    average_count = (
        db.query(func.count(ScoreModel.id))
        .filter(ScoreModel.final_score >= 5.5, ScoreModel.final_score < 7.0)
        .scalar()
        or 0
    )
    weak_count = (
        db.query(func.count(ScoreModel.id)).filter(ScoreModel.final_score < 5.5).scalar() or 0
    )

    return {
        "total_classes": total_classes,
        "total_students": total_students,
        "total_subjects": total_subjects,
        "total_scores": total_scores,
        "average_score": avg_score,
        "pass_rate": pass_rate,
        "distribution": {
            "excellent": excellent_count,
            "good": good_count,
            "average": average_count,
            "weak": weak_count,
        },
        "database_info": {
            "server": DB_SERVER,
            "database": DB_NAME,
            "driver": ODBC_DRIVER,
        },
    }


# ==============================================================================
# 7. API QUẢN LÝ LỚP HỌC (/api/classes)
# ==============================================================================
@app.get(
    "/api/classes",
    response_model=List[ClassResponse],
    tags=["Classes"],
    summary="Danh sách lớp học",
)
def list_classes(
    search: Optional[str] = Query(None, description="Tìm theo mã lớp, tên lớp hoặc GVCN"),
    db: Session = Depends(get_db),
):
    query = db.query(ClassModel)
    if search and search.strip():
        kw = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ClassModel.class_code.ilike(kw),
                ClassModel.class_name.ilike(kw),
                ClassModel.homeroom_teacher.ilike(kw),
            )
        )
    classes = query.order_by(ClassModel.id.asc()).all()
    return [
        {
            "id": c.id,
            "class_code": c.class_code,
            "class_name": c.class_name,
            "academic_year": c.academic_year,
            "homeroom_teacher": c.homeroom_teacher,
            "student_count": len(c.students),
        }
        for c in classes
    ]


@app.get(
    "/api/classes/{class_id}",
    response_model=ClassResponse,
    tags=["Classes"],
    summary="Chi tiết lớp học theo ID",
)
def get_class(class_id: int, db: Session = Depends(get_db)):
    cls_obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
    if not cls_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy lớp học với ID = {class_id}",
        )
    return {
        "id": cls_obj.id,
        "class_code": cls_obj.class_code,
        "class_name": cls_obj.class_name,
        "academic_year": cls_obj.academic_year,
        "homeroom_teacher": cls_obj.homeroom_teacher,
        "student_count": len(cls_obj.students),
    }


@app.post(
    "/api/classes",
    response_model=ClassResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Classes"],
    summary="Thêm lớp học mới",
)
def create_class(payload: ClassCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(ClassModel).filter(ClassModel.class_code == payload.class_code).first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mã lớp học '{payload.class_code}' đã tồn tại trong hệ thống",
        )
    new_cls = ClassModel(
        class_code=payload.class_code,
        class_name=payload.class_name,
        academic_year=payload.academic_year,
        homeroom_teacher=payload.homeroom_teacher,
    )
    db.add(new_cls)
    db.commit()
    db.refresh(new_cls)
    return {
        "id": new_cls.id,
        "class_code": new_cls.class_code,
        "class_name": new_cls.class_name,
        "academic_year": new_cls.academic_year,
        "homeroom_teacher": new_cls.homeroom_teacher,
        "student_count": 0,
    }


@app.patch(
    "/api/classes/{class_id}",
    response_model=ClassResponse,
    tags=["Classes"],
    summary="Cập nhật lớp học theo ID",
)
def update_class(class_id: int, payload: ClassUpdate, db: Session = Depends(get_db)):
    cls_obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
    if not cls_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy lớp học với ID = {class_id}",
        )
    update_data = payload.model_dump(exclude_unset=True)
    if "class_code" in update_data and update_data["class_code"] != cls_obj.class_code:
        dup = (
            db.query(ClassModel)
            .filter(ClassModel.class_code == update_data["class_code"], ClassModel.id != class_id)
            .first()
        )
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Mã lớp học '{update_data['class_code']}' đã tồn tại",
            )
    for k, v in update_data.items():
        setattr(cls_obj, k, v)
    db.commit()
    db.refresh(cls_obj)
    return {
        "id": cls_obj.id,
        "class_code": cls_obj.class_code,
        "class_name": cls_obj.class_name,
        "academic_year": cls_obj.academic_year,
        "homeroom_teacher": cls_obj.homeroom_teacher,
        "student_count": len(cls_obj.students),
    }


@app.delete(
    "/api/classes/{class_id}",
    tags=["Classes"],
    summary="Xóa lớp học theo ID",
)
def delete_class(class_id: int, db: Session = Depends(get_db)):
    cls_obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
    if not cls_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy lớp học với ID = {class_id}",
        )
    student_count = (
        db.query(func.count(StudentModel.id))
        .filter(StudentModel.class_id == class_id)
        .scalar()
        or 0
    )
    if student_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể xóa lớp '{cls_obj.class_code}' vì đang có {student_count} sinh viên thuộc lớp này (Ràng buộc khóa ngoại).",
        )
    db.delete(cls_obj)
    db.commit()
    return {"message": f"Đã xóa lớp học '{cls_obj.class_code}' (ID={class_id}) thành công"}


# ==============================================================================
# 8. API QUẢN LÝ SINH VIÊN (/api/students)
# ==============================================================================
@app.get(
    "/api/students",
    response_model=List[StudentResponse],
    tags=["Students"],
    summary="Danh sách sinh viên (hỗ trợ tìm kiếm và lọc theo lớp)",
)
def list_students(
    search: Optional[str] = Query(None, description="Tìm kiếm theo mã SV, họ tên, email, quê quán"),
    class_id: Optional[int] = Query(None, description="Lọc theo ID lớp học"),
    db: Session = Depends(get_db),
):
    query = db.query(StudentModel)
    if class_id is not None:
        query = query.filter(StudentModel.class_id == class_id)
    if search and search.strip():
        kw = f"%{search.strip()}%"
        query = query.filter(
            or_(
                StudentModel.student_code.ilike(kw),
                StudentModel.full_name.ilike(kw),
                StudentModel.email.ilike(kw),
                StudentModel.hometown.ilike(kw),
            )
        )
    students = query.order_by(StudentModel.id.asc()).all()
    return [serialize_student(st) for st in students]


@app.get(
    "/api/students/{student_id}",
    response_model=StudentResponse,
    tags=["Students"],
    summary="Chi tiết sinh viên theo ID",
)
def get_student(student_id: int, db: Session = Depends(get_db)):
    st = db.query(StudentModel).filter(StudentModel.id == student_id).first()
    if not st:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sinh viên với ID = {student_id}",
        )
    return serialize_student(st)


@app.post(
    "/api/students",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Students"],
    summary="Thêm sinh viên mới",
)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    # 1. Kiểm tra khóa ngoại class_id
    cls_obj = db.query(ClassModel).filter(ClassModel.id == payload.class_id).first()
    if not cls_obj:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Khóa ngoại không hợp lệ: Lớp học với class_id = {payload.class_id} không tồn tại",
        )
    # 2. Kiểm tra trùng mã sinh viên
    if db.query(StudentModel).filter(StudentModel.student_code == payload.student_code).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mã sinh viên '{payload.student_code}' đã tồn tại trong hệ thống",
        )
    # 3. Kiểm tra trùng email
    if db.query(StudentModel).filter(StudentModel.email == payload.email.lower()).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{payload.email}' đã được sử dụng bởi sinh viên khác",
        )

    new_st = StudentModel(
        student_code=payload.student_code,
        full_name=payload.full_name,
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        email=payload.email.lower(),
        hometown=payload.hometown,
        class_id=payload.class_id,
    )
    db.add(new_st)
    db.commit()
    db.refresh(new_st)
    return serialize_student(new_st)


@app.patch(
    "/api/students/{student_id}",
    response_model=StudentResponse,
    tags=["Students"],
    summary="Cập nhật thông tin sinh viên theo ID",
)
def update_student(student_id: int, payload: StudentUpdate, db: Session = Depends(get_db)):
    st = db.query(StudentModel).filter(StudentModel.id == student_id).first()
    if not st:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sinh viên với ID = {student_id}",
        )

    update_data = payload.model_dump(exclude_unset=True)

    # Kiểm tra khóa ngoại nếu cập nhật class_id
    if "class_id" in update_data:
        cls_obj = db.query(ClassModel).filter(ClassModel.id == update_data["class_id"]).first()
        if not cls_obj:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Khóa ngoại không hợp lệ: Lớp học với class_id = {update_data['class_id']} không tồn tại",
            )

    # Kiểm tra trùng mã SV
    if "student_code" in update_data and update_data["student_code"] != st.student_code:
        if (
            db.query(StudentModel)
            .filter(
                StudentModel.student_code == update_data["student_code"],
                StudentModel.id != student_id,
            )
            .first()
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Mã sinh viên '{update_data['student_code']}' đã tồn tại",
            )

    # Kiểm tra trùng email
    if "email" in update_data and update_data["email"]:
        update_data["email"] = update_data["email"].lower()
        if update_data["email"] != st.email:
            if (
                db.query(StudentModel)
                .filter(
                    StudentModel.email == update_data["email"],
                    StudentModel.id != student_id,
                )
                .first()
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Email '{update_data['email']}' đã được sử dụng bởi sinh viên khác",
                )

    for k, v in update_data.items():
        setattr(st, k, v)
    db.commit()
    db.refresh(st)
    return serialize_student(st)


@app.delete(
    "/api/students/{student_id}",
    tags=["Students"],
    summary="Xóa sinh viên theo ID",
)
def delete_student(student_id: int, db: Session = Depends(get_db)):
    st = db.query(StudentModel).filter(StudentModel.id == student_id).first()
    if not st:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sinh viên với ID = {student_id}",
        )
    score_count = (
        db.query(func.count(ScoreModel.id))
        .filter(ScoreModel.student_id == student_id)
        .scalar()
        or 0
    )
    if score_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể xóa sinh viên '{st.full_name}' ({st.student_code}) vì đã có {score_count} bản ghi điểm thi (Ràng buộc khóa ngoại).",
        )
    db.delete(st)
    db.commit()
    return {"message": f"Đã xóa sinh viên '{st.full_name}' (ID={student_id}) thành công"}


# ==============================================================================
# 9. API QUẢN LÝ MÔN HỌC (/api/subjects)
# ==============================================================================
@app.get(
    "/api/subjects",
    response_model=List[SubjectResponse],
    tags=["Subjects"],
    summary="Danh sách môn học",
)
def list_subjects(
    search: Optional[str] = Query(None, description="Tìm kiếm theo mã môn, tên môn hoặc bộ môn"),
    db: Session = Depends(get_db),
):
    query = db.query(SubjectModel)
    if search and search.strip():
        kw = f"%{search.strip()}%"
        query = query.filter(
            or_(
                SubjectModel.subject_code.ilike(kw),
                SubjectModel.subject_name.ilike(kw),
                SubjectModel.department.ilike(kw),
            )
        )
    subjects = query.order_by(SubjectModel.id.asc()).all()
    return [
        {
            "id": s.id,
            "subject_code": s.subject_code,
            "subject_name": s.subject_name,
            "credits": s.credits,
            "department": s.department,
            "score_count": len(s.scores),
        }
        for s in subjects
    ]


@app.get(
    "/api/subjects/{subject_id}",
    response_model=SubjectResponse,
    tags=["Subjects"],
    summary="Chi tiết môn học theo ID",
)
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    sub = db.query(SubjectModel).filter(SubjectModel.id == subject_id).first()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy môn học với ID = {subject_id}",
        )
    return {
        "id": sub.id,
        "subject_code": sub.subject_code,
        "subject_name": sub.subject_name,
        "credits": sub.credits,
        "department": sub.department,
        "score_count": len(sub.scores),
    }


@app.post(
    "/api/subjects",
    response_model=SubjectResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Subjects"],
    summary="Thêm môn học mới",
)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_db)):
    if db.query(SubjectModel).filter(SubjectModel.subject_code == payload.subject_code).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mã môn học '{payload.subject_code}' đã tồn tại trong hệ thống",
        )
    new_sub = SubjectModel(
        subject_code=payload.subject_code,
        subject_name=payload.subject_name,
        credits=payload.credits,
        department=payload.department,
    )
    db.add(new_sub)
    db.commit()
    db.refresh(new_sub)
    return {
        "id": new_sub.id,
        "subject_code": new_sub.subject_code,
        "subject_name": new_sub.subject_name,
        "credits": new_sub.credits,
        "department": new_sub.department,
        "score_count": 0,
    }


@app.patch(
    "/api/subjects/{subject_id}",
    response_model=SubjectResponse,
    tags=["Subjects"],
    summary="Cập nhật môn học theo ID",
)
def update_subject(subject_id: int, payload: SubjectUpdate, db: Session = Depends(get_db)):
    sub = db.query(SubjectModel).filter(SubjectModel.id == subject_id).first()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy môn học với ID = {subject_id}",
        )
    update_data = payload.model_dump(exclude_unset=True)
    if "subject_code" in update_data and update_data["subject_code"] != sub.subject_code:
        if (
            db.query(SubjectModel)
            .filter(
                SubjectModel.subject_code == update_data["subject_code"],
                SubjectModel.id != subject_id,
            )
            .first()
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Mã môn học '{update_data['subject_code']}' đã tồn tại",
            )
    for k, v in update_data.items():
        setattr(sub, k, v)
    db.commit()
    db.refresh(sub)
    return {
        "id": sub.id,
        "subject_code": sub.subject_code,
        "subject_name": sub.subject_name,
        "credits": sub.credits,
        "department": sub.department,
        "score_count": len(sub.scores),
    }


@app.delete(
    "/api/subjects/{subject_id}",
    tags=["Subjects"],
    summary="Xóa môn học theo ID",
)
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    sub = db.query(SubjectModel).filter(SubjectModel.id == subject_id).first()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy môn học với ID = {subject_id}",
        )
    score_count = (
        db.query(func.count(ScoreModel.id))
        .filter(ScoreModel.subject_id == subject_id)
        .scalar()
        or 0
    )
    if score_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể xóa môn học '{sub.subject_code}' vì đã có {score_count} bản ghi điểm thi (Ràng buộc khóa ngoại).",
        )
    db.delete(sub)
    db.commit()
    return {"message": f"Đã xóa môn học '{sub.subject_code}' (ID={subject_id}) thành công"}


# ==============================================================================
# 10. API QUẢN LÝ ĐIỂM THI (/api/scores)
# ==============================================================================
@app.get(
    "/api/scores",
    response_model=List[ScoreResponse],
    tags=["Scores"],
    summary="Danh sách điểm thi (lọc theo sinh viên, môn học, học kỳ, từ khóa)",
)
def list_scores(
    search: Optional[str] = Query(None, description="Tìm kiếm theo mã SV, tên SV, mã môn, tên môn"),
    student_id: Optional[int] = Query(None, description="Lọc theo ID sinh viên"),
    subject_id: Optional[int] = Query(None, description="Lọc theo ID môn học"),
    semester: Optional[str] = Query(None, description="Lọc theo học kỳ"),
    db: Session = Depends(get_db),
):
    query = db.query(ScoreModel).join(StudentModel).join(SubjectModel)
    if student_id is not None:
        query = query.filter(ScoreModel.student_id == student_id)
    if subject_id is not None:
        query = query.filter(ScoreModel.subject_id == subject_id)
    if semester and semester.strip():
        query = query.filter(ScoreModel.semester == semester.strip().upper())
    if search and search.strip():
        kw = f"%{search.strip()}%"
        query = query.filter(
            or_(
                StudentModel.student_code.ilike(kw),
                StudentModel.full_name.ilike(kw),
                SubjectModel.subject_code.ilike(kw),
                SubjectModel.subject_name.ilike(kw),
                ScoreModel.semester.ilike(kw),
            )
        )
    scores = query.order_by(ScoreModel.id.asc()).all()
    return [serialize_score(sc) for sc in scores]


@app.get(
    "/api/scores/{score_id}",
    response_model=ScoreResponse,
    tags=["Scores"],
    summary="Chi tiết bản ghi điểm thi theo ID",
)
def get_score(score_id: int, db: Session = Depends(get_db)):
    sc = db.query(ScoreModel).filter(ScoreModel.id == score_id).first()
    if not sc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy bản ghi điểm thi với ID = {score_id}",
        )
    return serialize_score(sc)


@app.post(
    "/api/scores",
    response_model=ScoreResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Scores"],
    summary="Nhập điểm thi mới",
)
def create_score(payload: ScoreCreate, db: Session = Depends(get_db)):
    # 1. Kiểm tra khóa ngoại student_id
    st = db.query(StudentModel).filter(StudentModel.id == payload.student_id).first()
    if not st:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Khóa ngoại không hợp lệ: Sinh viên với student_id = {payload.student_id} không tồn tại",
        )
    # 2. Kiểm tra khóa ngoại subject_id
    sub = db.query(SubjectModel).filter(SubjectModel.id == payload.subject_id).first()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Khóa ngoại không hợp lệ: Môn học với subject_id = {payload.subject_id} không tồn tại",
        )
    # 3. Kiểm tra trùng lặp điểm (student_id, subject_id, semester)
    dup = (
        db.query(ScoreModel)
        .filter(
            ScoreModel.student_id == payload.student_id,
            ScoreModel.subject_id == payload.subject_id,
            ScoreModel.semester == payload.semester,
        )
        .first()
    )
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sinh viên '{st.student_code}' đã có điểm môn '{sub.subject_code}' trong học kỳ '{payload.semester}'",
        )

    final_score = calculate_final_score(payload.process_score, payload.exam_score)
    new_sc = ScoreModel(
        student_id=payload.student_id,
        subject_id=payload.subject_id,
        semester=payload.semester,
        process_score=round(payload.process_score, 2),
        exam_score=round(payload.exam_score, 2),
        final_score=final_score,
    )
    db.add(new_sc)
    db.commit()
    db.refresh(new_sc)
    return serialize_score(new_sc)


@app.patch(
    "/api/scores/{score_id}",
    response_model=ScoreResponse,
    tags=["Scores"],
    summary="Cập nhật điểm thi theo ID",
)
def update_score(score_id: int, payload: ScoreUpdate, db: Session = Depends(get_db)):
    sc = db.query(ScoreModel).filter(ScoreModel.id == score_id).first()
    if not sc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy bản ghi điểm thi với ID = {score_id}",
        )

    update_data = payload.model_dump(exclude_unset=True)
    target_student_id = update_data.get("student_id", sc.student_id)
    target_subject_id = update_data.get("subject_id", sc.subject_id)
    target_semester = update_data.get("semester", sc.semester)

    if "student_id" in update_data:
        if not db.query(StudentModel).filter(StudentModel.id == target_student_id).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Khóa ngoại không hợp lệ: Sinh viên với student_id = {target_student_id} không tồn tại",
            )
    if "subject_id" in update_data:
        if not db.query(SubjectModel).filter(SubjectModel.id == target_subject_id).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Khóa ngoại không hợp lệ: Môn học với subject_id = {target_subject_id} không tồn tại",
            )

    # Kiểm tra trùng lặp nếu thay đổi bộ 3 (student_id, subject_id, semester)
    dup = (
        db.query(ScoreModel)
        .filter(
            ScoreModel.student_id == target_student_id,
            ScoreModel.subject_id == target_subject_id,
            ScoreModel.semester == target_semester,
            ScoreModel.id != score_id,
        )
        .first()
    )
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bản ghi điểm cho sinh viên, môn học và học kỳ này đã tồn tại",
        )

    for k, v in update_data.items():
        if k in ("process_score", "exam_score") and v is not None:
            setattr(sc, k, round(float(v), 2))
        else:
            setattr(sc, k, v)

    sc.final_score = calculate_final_score(sc.process_score, sc.exam_score)
    db.commit()
    db.refresh(sc)
    return serialize_score(sc)


@app.delete(
    "/api/scores/{score_id}",
    tags=["Scores"],
    summary="Xóa bản ghi điểm thi theo ID",
)
def delete_score(score_id: int, db: Session = Depends(get_db)):
    sc = db.query(ScoreModel).filter(ScoreModel.id == score_id).first()
    if not sc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy bản ghi điểm thi với ID = {score_id}",
        )
    db.delete(sc)
    db.commit()
    return {"message": f"Đã xóa bản ghi điểm thi (ID={score_id}) thành công"}


# ==============================================================================
# 11. PHỤC VỤ GIAO DIỆN FRONTEND TẠI "/" BẰNG STATICFILES
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)


@app.get("/", include_in_schema=False)
def serve_root():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="root_static")
