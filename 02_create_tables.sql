/*==============================================================================
  FILE: 02_create_tables.sql
  ĐỀ TÀI: HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐIỂM THI
  HỆ QUẢN TRỊ CSDL: MICROSOFT SQL SERVER (SSMS 22)
  MỤC ĐÍCH:
    - Tạo 4 bảng chuẩn hóa 3NF đồng bộ 100% với Backend FastAPI (main.py):
        1. dbo.classes   (Lớp học)
        2. dbo.students  (Sinh viên)
        3. dbo.subjects  (Môn học)
        4. dbo.scores    (Điểm thi)
    - Thiết lập đầy đủ các ràng buộc:
        + PRIMARY KEY (Khóa chính tự tăng IDENTITY(1,1))
        + FOREIGN KEY (Khóa ngoại tham chiếu chặt chẽ)
        + UNIQUE CONSTRAINT (Chống trùng mã lớp, mã SV, email, mã môn, điểm học kỳ)
        + CHECK CONSTRAINT (Kiểm tra giới tính, ngày sinh, tín chỉ 1-15, điểm 0.0-10.0)
        + DEFAULT CONSTRAINT (Giá trị mặc định cho niên khóa và học kỳ)
==============================================================================*/

USE [StudentGradeManagementDB];
GO

SET NOCOUNT ON;
GO

/*------------------------------------------------------------------------------
  1. BẢNG LỚP HỌC (dbo.classes)
------------------------------------------------------------------------------*/
IF OBJECT_ID(N'dbo.classes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.classes (
        id INT IDENTITY(1,1) NOT NULL,
        class_code VARCHAR(50) NOT NULL,
        class_name NVARCHAR(100) NOT NULL,
        academic_year VARCHAR(30) NULL CONSTRAINT DF_classes_academic_year DEFAULT ('2024-2028'),
        homeroom_teacher NVARCHAR(100) NULL,
        CONSTRAINT PK_classes PRIMARY KEY CLUSTERED (id ASC),
        CONSTRAINT UQ_classes_class_code UNIQUE NONCLUSTERED (class_code ASC)
    );
    PRINT N'>>> Đã tạo bảng dbo.classes.';
END
GO

-- Bổ sung DEFAULT / CHECK constraints cho dbo.classes nếu bảng đã được tạo trước đó bởi ORM
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_classes_code_not_empty')
BEGIN
    ALTER TABLE dbo.classes
    ADD CONSTRAINT CK_classes_code_not_empty CHECK (LEN(LTRIM(RTRIM(class_code))) >= 2);
END

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_classes_name_not_empty')
BEGIN
    ALTER TABLE dbo.classes
    ADD CONSTRAINT CK_classes_name_not_empty CHECK (LEN(LTRIM(RTRIM(class_name))) >= 2);
END

IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints dc
    INNER JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
    WHERE dc.parent_object_id = OBJECT_ID(N'dbo.classes') AND c.name = N'academic_year'
)
BEGIN
    ALTER TABLE dbo.classes
    ADD CONSTRAINT DF_classes_academic_year DEFAULT ('2024-2028') FOR academic_year;
END
GO

/*------------------------------------------------------------------------------
  2. BẢNG SINH VIÊN (dbo.students)
------------------------------------------------------------------------------*/
IF OBJECT_ID(N'dbo.students', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.students (
        id INT IDENTITY(1,1) NOT NULL,
        student_code VARCHAR(50) NOT NULL,
        full_name NVARCHAR(100) NOT NULL,
        date_of_birth DATE NOT NULL,
        gender NVARCHAR(20) NOT NULL,
        email VARCHAR(120) NOT NULL,
        hometown NVARCHAR(150) NULL,
        class_id INT NOT NULL,
        CONSTRAINT PK_students PRIMARY KEY CLUSTERED (id ASC),
        CONSTRAINT UQ_students_student_code UNIQUE NONCLUSTERED (student_code ASC),
        CONSTRAINT UQ_students_email UNIQUE NONCLUSTERED (email ASC),
        CONSTRAINT FK_students_classes FOREIGN KEY (class_id) REFERENCES dbo.classes(id)
    );
    PRINT N'>>> Đã tạo bảng dbo.students.';
END
GO

-- Bổ sung CHECK constraints cho dbo.students
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_students_code_not_empty')
BEGIN
    ALTER TABLE dbo.students
    ADD CONSTRAINT CK_students_code_not_empty CHECK (LEN(LTRIM(RTRIM(student_code))) >= 2);
END

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_students_gender_valid')
BEGIN
    ALTER TABLE dbo.students
    ADD CONSTRAINT CK_students_gender_valid CHECK (gender IN (N'Nam', N'Nữ', N'Khác'));
END

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_students_dob_valid')
BEGIN
    ALTER TABLE dbo.students
    ADD CONSTRAINT CK_students_dob_valid CHECK (date_of_birth >= '1950-01-01' AND date_of_birth <= CAST(GETDATE() AS DATE));
END

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_students_email_format')
BEGIN
    ALTER TABLE dbo.students
    ADD CONSTRAINT CK_students_email_format CHECK (email LIKE '%_@_%._%');
END
GO

/*------------------------------------------------------------------------------
  3. BẢNG MÔN HỌC (dbo.subjects)
------------------------------------------------------------------------------*/
IF OBJECT_ID(N'dbo.subjects', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.subjects (
        id INT IDENTITY(1,1) NOT NULL,
        subject_code VARCHAR(50) NOT NULL,
        subject_name NVARCHAR(120) NOT NULL,
        credits INT NOT NULL,
        department NVARCHAR(100) NULL,
        CONSTRAINT PK_subjects PRIMARY KEY CLUSTERED (id ASC),
        CONSTRAINT UQ_subjects_subject_code UNIQUE NONCLUSTERED (subject_code ASC)
    );
    PRINT N'>>> Đã tạo bảng dbo.subjects.';
END
GO

-- Bổ sung CHECK constraints cho dbo.subjects
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_subjects_code_not_empty')
BEGIN
    ALTER TABLE dbo.subjects
    ADD CONSTRAINT CK_subjects_code_not_empty CHECK (LEN(LTRIM(RTRIM(subject_code))) >= 2);
END

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_subjects_credits_range')
BEGIN
    ALTER TABLE dbo.subjects
    ADD CONSTRAINT CK_subjects_credits_range CHECK (credits >= 1 AND credits <= 15);
END
GO

/*------------------------------------------------------------------------------
  4. BẢNG ĐIỂM THI (dbo.scores)
------------------------------------------------------------------------------*/
IF OBJECT_ID(N'dbo.scores', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.scores (
        id INT IDENTITY(1,1) NOT NULL,
        student_id INT NOT NULL,
        subject_id INT NOT NULL,
        semester VARCHAR(30) NOT NULL CONSTRAINT DF_scores_semester DEFAULT ('HK1-2026'),
        process_score FLOAT NOT NULL,
        exam_score FLOAT NOT NULL,
        final_score FLOAT NOT NULL,
        CONSTRAINT PK_scores PRIMARY KEY CLUSTERED (id ASC),
        CONSTRAINT FK_scores_students FOREIGN KEY (student_id) REFERENCES dbo.students(id),
        CONSTRAINT FK_scores_subjects FOREIGN KEY (subject_id) REFERENCES dbo.subjects(id),
        CONSTRAINT uq_student_subject_semester UNIQUE NONCLUSTERED (student_id ASC, subject_id ASC, semester ASC)
    );
    PRINT N'>>> Đã tạo bảng dbo.scores.';
END
GO

-- Bổ sung DEFAULT & CHECK constraints cho dbo.scores
IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints dc
    INNER JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
    WHERE dc.parent_object_id = OBJECT_ID(N'dbo.scores') AND c.name = N'semester'
)
BEGIN
    ALTER TABLE dbo.scores
    ADD CONSTRAINT DF_scores_semester DEFAULT ('HK1-2026') FOR semester;
END

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_scores_process_range')
BEGIN
    ALTER TABLE dbo.scores
    ADD CONSTRAINT CK_scores_process_range CHECK (process_score >= 0.0 AND process_score <= 10.0);
END

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_scores_exam_range')
BEGIN
    ALTER TABLE dbo.scores
    ADD CONSTRAINT CK_scores_exam_range CHECK (exam_score >= 0.0 AND exam_score <= 10.0);
END

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_scores_final_range')
BEGIN
    ALTER TABLE dbo.scores
    ADD CONSTRAINT CK_scores_final_range CHECK (final_score >= 0.0 AND final_score <= 10.0);
END
GO

-- 5. Hiển thị danh sách các bảng và ràng buộc đã thiết lập trong Database
SELECT 
    t.name AS [TableName],
    kc.name AS [ConstraintName],
    kc.type_desc AS [ConstraintType]
FROM sys.tables t
LEFT JOIN sys.objects kc ON t.object_id = kc.parent_object_id
WHERE t.name IN (N'classes', N'students', N'subjects', N'scores')
  AND kc.type IN ('PK', 'F', 'UQ', 'C', 'D')
ORDER BY t.name, kc.type_desc;
GO
