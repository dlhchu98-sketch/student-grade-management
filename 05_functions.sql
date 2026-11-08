/*==============================================================================
  FILE: 05_functions.sql
  ĐỀ TÀI: HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐIỂM THI
  HỆ QUẢN TRỊ CSDL: MICROSOFT SQL SERVER (SSMS 22)
  MỤC ĐÍCH:
    Xây dựng 4 User-Defined Functions (UDF) phục vụ tính toán và truy vấn:
      1. dbo.ufn_CalculateFinalScore    (Scalar Function): Tính điểm tổng kết môn học (40% QT + 60% Thi).
      2. dbo.ufn_GetGradeClassification (Scalar Function): Xếp loại học lực theo thang điểm 10.
      3. dbo.ufn_CalculateStudentGPA    (Scalar Function): Tính điểm trung bình tích lũy (GPA) có trọng số theo tín chỉ.
      4. dbo.ufn_GetClassHonorRoll      (Inline Table-Valued Function): Lấy danh sách sinh viên tiêu biểu / học bổng theo lớp.
==============================================================================*/

USE [StudentGradeManagementDB];
GO

/*------------------------------------------------------------------------------
  UDF 1: dbo.ufn_CalculateFinalScore (Scalar-Valued Function)
  Mô tả: Tính điểm tổng kết môn học từ điểm quá trình (40%) và điểm thi (60%).
------------------------------------------------------------------------------*/
CREATE OR ALTER FUNCTION dbo.ufn_CalculateFinalScore
(
    @ProcessScore FLOAT,
    @ExamScore    FLOAT
)
RETURNS FLOAT
WITH SCHEMABINDING
AS
BEGIN
    IF @ProcessScore IS NULL OR @ExamScore IS NULL
        RETURN NULL;

    IF @ProcessScore < 0.0 OR @ProcessScore > 10.0 OR @ExamScore < 0.0 OR @ExamScore > 10.0
        RETURN NULL;

    RETURN ROUND(@ProcessScore * 0.4 + @ExamScore * 0.6, 2);
END
GO

/*------------------------------------------------------------------------------
  UDF 2: dbo.ufn_GetGradeClassification (Scalar-Valued Function)
  Mô tả: Trả về xếp loại học lực tương ứng với điểm tổng kết.
------------------------------------------------------------------------------*/
CREATE OR ALTER FUNCTION dbo.ufn_GetGradeClassification
(
    @FinalScore FLOAT
)
RETURNS NVARCHAR(30)
WITH SCHEMABINDING
AS
BEGIN
    IF @FinalScore IS NULL
        RETURN N'Chưa có điểm';

    RETURN CASE
        WHEN @FinalScore >= 8.5 THEN N'Giỏi (A)'
        WHEN @FinalScore >= 7.0 THEN N'Khá (B)'
        WHEN @FinalScore >= 5.5 THEN N'Trung bình (C)'
        WHEN @FinalScore >= 4.0 THEN N'Trung bình yếu (D)'
        ELSE N'Kém / Trượt (F)'
    END;
END
GO

/*------------------------------------------------------------------------------
  UDF 3: dbo.ufn_CalculateStudentGPA (Scalar-Valued Function)
  Mô tả: Tính điểm trung bình tích lũy (GPA hệ 10) có trọng số theo số tín chỉ
         của một sinh viên dựa trên student_id.
------------------------------------------------------------------------------*/
CREATE OR ALTER FUNCTION dbo.ufn_CalculateStudentGPA
(
    @StudentId INT
)
RETURNS FLOAT
AS
BEGIN
    DECLARE @GPA FLOAT;

    SELECT 
        @GPA = ROUND(SUM(sc.final_score * sub.credits) / NULLIF(SUM(sub.credits), 0), 2)
    FROM dbo.scores sc
    INNER JOIN dbo.subjects sub ON sc.subject_id = sub.id
    WHERE sc.student_id = @StudentId;

    RETURN ISNULL(@GPA, 0.0);
END
GO

/*------------------------------------------------------------------------------
  UDF 4: dbo.ufn_GetClassHonorRoll (Inline Table-Valued Function)
  Mô tả: Trả về danh sách sinh viên có GPA từ @MinGPA trở lên (mặc định >= 7.0)
         theo lớp học (hoặc toàn trường nếu @ClassId = NULL).
------------------------------------------------------------------------------*/
CREATE OR ALTER FUNCTION dbo.ufn_GetClassHonorRoll
(
    @ClassId INT = NULL,
    @MinGPA  FLOAT = 7.0
)
RETURNS TABLE
AS
RETURN
(
    SELECT 
        st.id AS [StudentID],
        st.student_code AS [MaSV],
        st.full_name AS [HoTen],
        c.class_code AS [MaLop],
        c.class_name AS [TenLop],
        COUNT(sc.id) AS [SoMonDaHoc],
        SUM(sub.credits) AS [TongTinChi],
        ROUND(SUM(sc.final_score * sub.credits) / NULLIF(SUM(sub.credits), 0), 2) AS [GPA],
        dbo.ufn_GetGradeClassification(
            ROUND(SUM(sc.final_score * sub.credits) / NULLIF(SUM(sub.credits), 0), 2)
        ) AS [XepLoaiTichLuy]
    FROM dbo.students st
    INNER JOIN dbo.classes c ON st.class_id = c.id
    INNER JOIN dbo.scores sc ON st.id = sc.student_id
    INNER JOIN dbo.subjects sub ON sc.subject_id = sub.id
    WHERE (@ClassId IS NULL OR st.class_id = @ClassId)
    GROUP BY st.id, st.student_code, st.full_name, c.class_code, c.class_name
    HAVING ROUND(SUM(sc.final_score * sub.credits) / NULLIF(SUM(sub.credits), 0), 2) >= ISNULL(@MinGPA, 7.0)
);
GO

PRINT N'=== ĐÃ KHỞI TẠO THÀNH CÔNG 4 USER-DEFINED FUNCTIONS (05_functions.sql) ===';
GO
