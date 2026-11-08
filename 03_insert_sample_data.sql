/*==============================================================================
  FILE: 03_insert_sample_data.sql
  ĐỀ TÀI: HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐIỂM THI
  HỆ QUẢN TRỊ CSDL: MICROSOFT SQL SERVER (SSMS 22)
  MỤC ĐÍCH:
    - Chèn dữ liệu mẫu (DML INSERT) đầy đủ, có tính liên kết khóa ngoại chặt chẽ
      giữa 4 bảng: dbo.classes -> dbo.students, dbo.subjects -> dbo.scores.
    - Sử dụng MERGE / IF NOT EXISTS để script có thể chạy lại nhiều lần (Idempotent)
      mà không gây lỗi trùng khóa UNIQUE hay làm mất dữ liệu đang chạy trên FastAPI.
==============================================================================*/

USE [StudentGradeManagementDB];
GO

SET NOCOUNT ON;
GO

PRINT N'=== BẮT ĐẦU CHÈN DỮ LIỆU MẪU (03_insert_sample_data.sql) ===';

/*------------------------------------------------------------------------------
  1. DỮ LIỆU MẪU BẢNG LỚP HỌC (dbo.classes) - 5 Lớp học
------------------------------------------------------------------------------*/
DECLARE @SampleClasses TABLE (
    class_code VARCHAR(50),
    class_name NVARCHAR(100),
    academic_year VARCHAR(30),
    homeroom_teacher NVARCHAR(100)
);

INSERT INTO @SampleClasses VALUES
('CNTT01-K18', N'Công nghệ phần mềm 01 - K18', '2024-2028', N'TS. Nguyễn Văn Minh'),
('CNTT02-K18', N'Hệ thống thông tin 02 - K18', '2024-2028', N'ThS. Trần Thị Thu Hà'),
('KHDL01-K18', N'Khoa học dữ liệu & AI - K18', '2024-2028', N'PGS.TS. Lê Hoàng Nam'),
('ATTT01-K18', N'An toàn thông tin 01 - K18', '2024-2028', N'TS. Phạm Quốc Bảo'),
('KTMT01-K18', N'Kỹ thuật máy tính & IoT - K18', '2024-2028', N'TS. Đỗ Quang Huy');

INSERT INTO dbo.classes (class_code, class_name, academic_year, homeroom_teacher)
SELECT s.class_code, s.class_name, s.academic_year, s.homeroom_teacher
FROM @SampleClasses s
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.classes c WHERE c.class_code = s.class_code
);

PRINT N'>>> 1. Đã đồng bộ dữ liệu mẫu bảng dbo.classes.';
GO

/*------------------------------------------------------------------------------
  2. DỮ LIỆU MẪU BẢNG MÔN HỌC (dbo.subjects) - 6 Môn học
------------------------------------------------------------------------------*/
DECLARE @SampleSubjects TABLE (
    subject_code VARCHAR(50),
    subject_name NVARCHAR(120),
    credits INT,
    department NVARCHAR(100)
);

INSERT INTO @SampleSubjects VALUES
('IT3010', N'Hệ quản trị Cơ sở dữ liệu SQL Server', 3, N'Hệ thống thông tin'),
('IT3020', N'Phát triển Ứng dụng Web với FastAPI', 3, N'Công nghệ phần mềm'),
('IT3030', N'Cấu trúc dữ liệu và Giải thuật', 4, N'Khoa học máy tính'),
('IT3040', N'Trí tuệ nhân tạo & Học máy', 3, N'Khoa học dữ liệu'),
('IT3050', N'Mạng máy tính và Bảo mật', 3, N'An toàn thông tin'),
('IT3060', N'Phân tích và Thiết kế Hệ thống', 3, N'Hệ thống thông tin');

INSERT INTO dbo.subjects (subject_code, subject_name, credits, department)
SELECT s.subject_code, s.subject_name, s.credits, s.department
FROM @SampleSubjects s
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.subjects sub WHERE sub.subject_code = s.subject_code
);

PRINT N'>>> 2. Đã đồng bộ dữ liệu mẫu bảng dbo.subjects.';
GO

/*------------------------------------------------------------------------------
  3. DỮ LIỆU MẪU BẢNG SINH VIÊN (dbo.students) - 10 Sinh viên
------------------------------------------------------------------------------*/
DECLARE @SampleStudents TABLE (
    student_code VARCHAR(50),
    full_name NVARCHAR(100),
    date_of_birth DATE,
    gender NVARCHAR(20),
    email VARCHAR(120),
    hometown NVARCHAR(150),
    class_code VARCHAR(50)
);

INSERT INTO @SampleStudents VALUES
('SV2024001', N'Nguyễn Minh Quân', '2005-03-15', N'Nam', 'quan.nm24001@student.edu.vn', N'Hà Nội', 'CNTT01-K18'),
('SV2024002', N'Trần Ngọc Ánh', '2005-07-22', N'Nữ', 'anh.tn24002@student.edu.vn', N'Hải Phòng', 'CNTT01-K18'),
('SV2024003', N'Lê Hoàng Phúc', '2005-11-08', N'Nam', 'phuc.lh24003@student.edu.vn', N'Đà Nẵng', 'CNTT02-K18'),
('SV2024004', N'Phạm Khánh Linh', '2005-01-30', N'Nữ', 'linh.pk24004@student.edu.vn', N'Nam Định', 'CNTT02-K18'),
('SV2024005', N'Hoàng Đức Tuấn', '2005-05-19', N'Nam', 'tuan.hd24005@student.edu.vn', N'Nghệ An', 'KHDL01-K18'),
('SV2024006', N'Vũ Phương Thảo', '2005-09-12', N'Nữ', 'thao.vp24006@student.edu.vn', N'Quảng Ninh', 'ATTT01-K18'),
('SV2024007', N'Đặng Quốc Bảo', '2005-04-05', N'Nam', 'bao.dq24007@student.edu.vn', N'Thanh Hóa', 'CNTT01-K18'),
('SV2024008', N'Bùi Thanh Mai', '2005-12-18', N'Nữ', 'mai.bt24008@student.edu.vn', N'Thái Bình', 'KHDL01-K18'),
('SV2024009', N'Ngô Gia Huy', '2005-08-25', N'Nam', 'huy.ng24009@student.edu.vn', N'Bắc Ninh', 'KTMT01-K18'),
('SV2024010', N'Đỗ Ngọc Hân', '2005-02-14', N'Nữ', 'han.dn24010@student.edu.vn', N'Hà Nam', 'ATTT01-K18');

INSERT INTO dbo.students (student_code, full_name, date_of_birth, gender, email, hometown, class_id)
SELECT 
    s.student_code,
    s.full_name,
    s.date_of_birth,
    s.gender,
    s.email,
    s.hometown,
    c.id
FROM @SampleStudents s
INNER JOIN dbo.classes c ON c.class_code = s.class_code
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.students st WHERE st.student_code = s.student_code OR st.email = s.email
);

PRINT N'>>> 3. Đã đồng bộ dữ liệu mẫu bảng dbo.students.';
GO

/*------------------------------------------------------------------------------
  4. DỮ LIỆU MẪU BẢNG ĐIỂM THI (dbo.scores) - 14 Bản ghi điểm các cấp độ học lực
------------------------------------------------------------------------------*/
DECLARE @SampleScores TABLE (
    student_code VARCHAR(50),
    subject_code VARCHAR(50),
    semester VARCHAR(30),
    process_score FLOAT,
    exam_score FLOAT
);

INSERT INTO @SampleScores VALUES
('SV2024001', 'IT3010', 'HK1-2026', 9.0, 8.5),
('SV2024001', 'IT3020', 'HK1-2026', 8.5, 9.0),
('SV2024001', 'IT3030', 'HK1-2026', 9.5, 9.0),
('SV2024002', 'IT3010', 'HK1-2026', 8.0, 7.5),
('SV2024002', 'IT3030', 'HK1-2026', 7.5, 8.0),
('SV2024003', 'IT3010', 'HK1-2026', 6.5, 7.0),
('SV2024003', 'IT3060', 'HK1-2026', 6.0, 5.5),
('SV2024004', 'IT3020', 'HK1-2026', 9.5, 9.0),
('SV2024005', 'IT3040', 'HK1-2026', 8.0, 8.5),
('SV2024006', 'IT3050', 'HK1-2026', 5.5, 6.0),
('SV2024007', 'IT3010', 'HK1-2026', 4.5, 4.0),
('SV2024008', 'IT3040', 'HK1-2026', 9.0, 9.5),
('SV2024009', 'IT3030', 'HK1-2026', 3.5, 3.0),
('SV2024010', 'IT3050', 'HK1-2026', 7.0, 7.5);

INSERT INTO dbo.scores (student_id, subject_id, semester, process_score, exam_score, final_score)
SELECT 
    st.id,
    sub.id,
    sc.semester,
    sc.process_score,
    sc.exam_score,
    ROUND(sc.process_score * 0.4 + sc.exam_score * 0.6, 2)
FROM @SampleScores sc
INNER JOIN dbo.students st ON st.student_code = sc.student_code
INNER JOIN dbo.subjects sub ON sub.subject_code = sc.subject_code
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.scores existing
    WHERE existing.student_id = st.id
      AND existing.subject_id = sub.id
      AND existing.semester = sc.semester
);

PRINT N'>>> 4. Đã đồng bộ dữ liệu mẫu bảng dbo.scores.';
GO

-- 5. Thống kê số lượng bản ghi sau khi nạp dữ liệu mẫu
SELECT 
    (SELECT COUNT(*) FROM dbo.classes)  AS [TongSoLopHoc],
    (SELECT COUNT(*) FROM dbo.subjects) AS [TongSoMonHoc],
    (SELECT COUNT(*) FROM dbo.students) AS [TongSoSinhVien],
    (SELECT COUNT(*) FROM dbo.scores)   AS [TongSoDiemThi];
GO
