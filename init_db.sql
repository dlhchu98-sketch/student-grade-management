/*==============================================================================
  SCRIPT KHỞI TẠO CƠ SỞ DỮ LIỆU SQL SERVER
  ĐỀ TÀI: HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐIỂM THI (StudentGradeManagementDB)
  Lưu ý: Khi chạy `uvicorn main:app --reload`, hệ thống đã tự động tạo Database,
  các bảng và dữ liệu mẫu. File SQL này dùng để tham khảo hoặc chạy trực tiếp
  trên SQL Server Management Studio (SSMS).
==============================================================================*/

IF DB_ID(N'StudentGradeManagementDB') IS NULL
BEGIN
    CREATE DATABASE [StudentGradeManagementDB];
END
GO

USE [StudentGradeManagementDB];
GO

-- 1. Bảng Lớp học (classes)
IF OBJECT_ID(N'dbo.classes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.classes (
        id INT IDENTITY(1,1) PRIMARY KEY,
        class_code VARCHAR(50) NOT NULL UNIQUE,
        class_name NVARCHAR(100) NOT NULL,
        academic_year VARCHAR(30) NULL DEFAULT '2024-2028',
        homeroom_teacher NVARCHAR(100) NULL
    );
END
GO

-- 2. Bảng Sinh viên (students)
IF OBJECT_ID(N'dbo.students', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.students (
        id INT IDENTITY(1,1) PRIMARY KEY,
        student_code VARCHAR(50) NOT NULL UNIQUE,
        full_name NVARCHAR(100) NOT NULL,
        date_of_birth DATE NOT NULL,
        gender NVARCHAR(20) NOT NULL,
        email VARCHAR(120) NOT NULL UNIQUE,
        hometown NVARCHAR(150) NULL,
        class_id INT NOT NULL,
        CONSTRAINT FK_students_classes FOREIGN KEY (class_id) REFERENCES dbo.classes(id)
    );
END
GO

-- 3. Bảng Môn học (subjects)
IF OBJECT_ID(N'dbo.subjects', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.subjects (
        id INT IDENTITY(1,1) PRIMARY KEY,
        subject_code VARCHAR(50) NOT NULL UNIQUE,
        subject_name NVARCHAR(120) NOT NULL,
        credits INT NOT NULL CHECK (credits BETWEEN 1 AND 15),
        department NVARCHAR(100) NULL
    );
END
GO

-- 4. Bảng Điểm thi (scores)
IF OBJECT_ID(N'dbo.scores', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.scores (
        id INT IDENTITY(1,1) PRIMARY KEY,
        student_id INT NOT NULL,
        subject_id INT NOT NULL,
        semester VARCHAR(30) NOT NULL DEFAULT 'HK1-2026',
        process_score FLOAT NOT NULL CHECK (process_score BETWEEN 0.0 AND 10.0),
        exam_score FLOAT NOT NULL CHECK (exam_score BETWEEN 0.0 AND 10.0),
        final_score FLOAT NOT NULL CHECK (final_score BETWEEN 0.0 AND 10.0),
        CONSTRAINT FK_scores_students FOREIGN KEY (student_id) REFERENCES dbo.students(id),
        CONSTRAINT FK_scores_subjects FOREIGN KEY (subject_id) REFERENCES dbo.subjects(id),
        CONSTRAINT uq_student_subject_semester UNIQUE (student_id, subject_id, semester)
    );
END
GO
