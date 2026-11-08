/*==============================================================================
  FILE: 04_stored_procedures.sql
  ĐỀ TÀI: HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐIỂM THI
  HỆ QUẢN TRỊ CSDL: MICROSOFT SQL SERVER (SSMS 22)
  MỤC ĐÍCH:
    Xây dựng 5 Stored Procedures xử lý nghiệp vụ cốt lõi:
      1. dbo.usp_UpsertStudentScore        : Kiểm tra điều kiện hợp lệ, nhập mới hoặc cập nhật điểm môn học & tự tính điểm tổng kết.
      2. dbo.usp_GetStudentTranscriptAndGPA: Xem bảng điểm chi tiết và tính GPA tích lũy (hệ 10 & hệ 4) của sinh viên.
      3. dbo.usp_StatsByClass              : Thống kê kết quả học tập theo Lớp học.
      4. dbo.usp_StatsBySubject            : Thống kê phổ điểm và tỷ lệ qua môn theo Môn học & Học kỳ.
      5. dbo.usp_SearchStudentsAdvanced    : Tìm kiếm sinh viên đa điều kiện kèm GPA và tổng tín chỉ.
==============================================================================*/

USE [StudentGradeManagementDB];
GO

/*------------------------------------------------------------------------------
  SP 1: dbo.usp_UpsertStudentScore
  Nghiệp vụ: Kiểm tra tính hợp lệ khi nhập điểm (khóa ngoại SV, môn học, khoảng điểm
             0.0 - 10.0), tự động tính điểm tổng kết (40% QT + 60% Thi). Nếu SV chưa
             có điểm môn đó trong học kỳ thì INSERT, nếu đã có thì UPDATE.
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_UpsertStudentScore
    @StudentCode   VARCHAR(50),
    @SubjectCode   VARCHAR(50),
    @Semester      VARCHAR(30) = 'HK1-2026',
    @ProcessScore  FLOAT,
    @ExamScore     FLOAT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @StudentId INT;
    DECLARE @SubjectId INT;
    DECLARE @FinalScore FLOAT;

    -- 1. Kiểm tra tính hợp lệ của điểm số (0.0 - 10.0)
    IF @ProcessScore IS NULL OR @ProcessScore < 0.0 OR @ProcessScore > 10.0
    BEGIN
        ;THROW 50101, N'Lỗi nghiệp vụ: Điểm quá trình phải nằm trong khoảng từ 0.0 đến 10.0.', 1;
    END

    IF @ExamScore IS NULL OR @ExamScore < 0.0 OR @ExamScore > 10.0
    BEGIN
        ;THROW 50102, N'Lỗi nghiệp vụ: Điểm thi kết thúc học phần phải nằm trong khoảng từ 0.0 đến 10.0.', 1;
    END

    -- 2. Kiểm tra sinh viên tồn tại và thuộc lớp học hợp lệ
    SELECT @StudentId = s.id
    FROM dbo.students s
    INNER JOIN dbo.classes c ON s.class_id = c.id
    WHERE s.student_code = UPPER(LTRIM(RTRIM(@StudentCode)));

    IF @StudentId IS NULL
    BEGIN
        ;THROW 50103, N'Lỗi khóa ngoại: Mã sinh viên không tồn tại hoặc chưa được phân lớp hợp lệ.', 1;
    END

    -- 3. Kiểm tra môn học tồn tại
    SELECT @SubjectId = sub.id
    FROM dbo.subjects sub
    WHERE sub.subject_code = UPPER(LTRIM(RTRIM(@SubjectCode)));

    IF @SubjectId IS NULL
    BEGIN
        ;THROW 50104, N'Lỗi khóa ngoại: Mã môn học không tồn tại trong hệ thống.', 1;
    END

    -- 4. Tính điểm tổng kết môn học (40% điểm quá trình + 60% điểm thi)
    SET @Semester = UPPER(LTRIM(RTRIM(@Semester)));
    SET @FinalScore = ROUND(@ProcessScore * 0.4 + @ExamScore * 0.6, 2);

    -- 5. Thực hiện Upsert (INSERT hoặc UPDATE)
    IF EXISTS (
        SELECT 1 FROM dbo.scores
        WHERE student_id = @StudentId AND subject_id = @SubjectId AND semester = @Semester
    )
    BEGIN
        UPDATE dbo.scores
        SET process_score = ROUND(@ProcessScore, 2),
            exam_score    = ROUND(@ExamScore, 2),
            final_score   = @FinalScore
        WHERE student_id = @StudentId AND subject_id = @SubjectId AND semester = @Semester;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.scores (student_id, subject_id, semester, process_score, exam_score, final_score)
        VALUES (@StudentId, @SubjectId, @Semester, ROUND(@ProcessScore, 2), ROUND(@ExamScore, 2), @FinalScore);
    END

    -- 6. Trả về kết quả điểm vừa lưu
    SELECT 
        sc.id AS [ScoreID],
        st.student_code AS [MaSV],
        st.full_name AS [HoTen],
        c.class_code AS [MaLop],
        sub.subject_code AS [MaMon],
        sub.subject_name AS [TenMonHoc],
        sub.credits AS [SoTinChi],
        sc.semester AS [HocKy],
        sc.process_score AS [DiemQuaTrinh],
        sc.exam_score AS [DiemThi],
        sc.final_score AS [DiemTongKet],
        CASE 
            WHEN sc.final_score >= 8.5 THEN N'Giỏi (A)'
            WHEN sc.final_score >= 7.0 THEN N'Khá (B)'
            WHEN sc.final_score >= 5.5 THEN N'Trung bình (C)'
            WHEN sc.final_score >= 4.0 THEN N'Trung bình yếu (D)'
            ELSE N'Kém / Trượt (F)'
        END AS [XepLoai],
        CASE WHEN sc.final_score >= 4.0 THEN N'Đạt' ELSE N'Học lại' END AS [KetQua]
    FROM dbo.scores sc
    INNER JOIN dbo.students st ON sc.student_id = st.id
    INNER JOIN dbo.classes c ON st.class_id = c.id
    INNER JOIN dbo.subjects sub ON sc.subject_id = sub.id
    WHERE sc.student_id = @StudentId AND sc.subject_id = @SubjectId AND sc.semester = @Semester;
END
GO

/*------------------------------------------------------------------------------
  SP 2: dbo.usp_GetStudentTranscriptAndGPA
  Nghiệp vụ: Truy xuất bảng điểm các môn và tính điểm trung bình tích lũy (GPA)
             có trọng số theo tín chỉ của một sinh viên.
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_GetStudentTranscriptAndGPA
    @StudentCode VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @StudentId INT;
    SELECT @StudentId = id FROM dbo.students WHERE student_code = UPPER(LTRIM(RTRIM(@StudentCode)));

    IF @StudentId IS NULL
    BEGIN
        ;THROW 50105, N'Không tìm thấy sinh viên với mã được cung cấp.', 1;
    END

    -- Result Set 1: Thông tin tổng hợp và GPA tích lũy của sinh viên
    SELECT 
        st.id AS [StudentID],
        st.student_code AS [MaSV],
        st.full_name AS [HoTen],
        c.class_code AS [MaLop],
        c.class_name AS [TenLop],
        COUNT(sc.id) AS [SoMonDaHoc],
        ISNULL(SUM(sub.credits), 0) AS [TongTinChiDangKy],
        ISNULL(SUM(CASE WHEN sc.final_score >= 4.0 THEN sub.credits ELSE 0 END), 0) AS [TinChiTichLuy],
        ISNULL(ROUND(SUM(sc.final_score * sub.credits) / NULLIF(SUM(sub.credits), 0), 2), 0.0) AS [GPA_He10],
        ISNULL(ROUND(
            SUM((CASE 
                    WHEN sc.final_score >= 8.5 THEN 4.0
                    WHEN sc.final_score >= 7.0 THEN 3.0
                    WHEN sc.final_score >= 5.5 THEN 2.0
                    WHEN sc.final_score >= 4.0 THEN 1.0
                    ELSE 0.0
                 END) * sub.credits) / NULLIF(SUM(sub.credits), 0), 2), 0.0) AS [GPA_He4]
    FROM dbo.students st
    INNER JOIN dbo.classes c ON st.class_id = c.id
    LEFT JOIN dbo.scores sc ON st.id = sc.student_id
    LEFT JOIN dbo.subjects sub ON sc.subject_id = sub.id
    WHERE st.id = @StudentId
    GROUP BY st.id, st.student_code, st.full_name, c.class_code, c.class_name;

    -- Result Set 2: Chi tiết điểm từng môn học
    SELECT 
        sub.subject_code AS [MaMon],
        sub.subject_name AS [TenMonHoc],
        sub.credits AS [SoTinChi],
        sc.semester AS [HocKy],
        sc.process_score AS [DiemQT],
        sc.exam_score AS [DiemThi],
        sc.final_score AS [DiemTongKet],
        CASE 
            WHEN sc.final_score >= 8.5 THEN N'Giỏi (A)'
            WHEN sc.final_score >= 7.0 THEN N'Khá (B)'
            WHEN sc.final_score >= 5.5 THEN N'Trung bình (C)'
            WHEN sc.final_score >= 4.0 THEN N'Trung bình yếu (D)'
            ELSE N'Kém / Trượt (F)'
        END AS [XepLoai]
    FROM dbo.scores sc
    INNER JOIN dbo.subjects sub ON sc.subject_id = sub.id
    WHERE sc.student_id = @StudentId
    ORDER BY sc.semester DESC, sub.subject_code ASC;
END
GO

/*------------------------------------------------------------------------------
  SP 3: dbo.usp_StatsByClass
  Nghiệp vụ: Thống kê kết quả học tập theo Lớp học (sĩ số, số lượt điểm, điểm TB,
             số lượng Giỏi/Khá/TB/Yếu-Kém, tỷ lệ qua môn %).
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_StatsByClass
    @ClassCode VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT 
        c.id AS [ClassID],
        c.class_code AS [MaLop],
        c.class_name AS [TenLop],
        c.homeroom_teacher AS [GiangVienCoVan],
        COUNT(DISTINCT st.id) AS [SiSoSinhVien],
        COUNT(sc.id) AS [TongLuotDiem],
        ISNULL(ROUND(AVG(sc.final_score), 2), 0.0) AS [DiemTrungBinhLop],
        SUM(CASE WHEN sc.final_score >= 8.5 THEN 1 ELSE 0 END) AS [SL_Gioi],
        SUM(CASE WHEN sc.final_score >= 7.0 AND sc.final_score < 8.5 THEN 1 ELSE 0 END) AS [SL_Kha],
        SUM(CASE WHEN sc.final_score >= 5.5 AND sc.final_score < 7.0 THEN 1 ELSE 0 END) AS [SL_TrungBinh],
        SUM(CASE WHEN sc.final_score < 5.5 AND sc.id IS NOT NULL THEN 1 ELSE 0 END) AS [SL_YeuKem],
        ISNULL(
            ROUND(
                100.0 * SUM(CASE WHEN sc.final_score >= 4.0 THEN 1 ELSE 0 END) / NULLIF(COUNT(sc.id), 0),
                1
            ),
            0.0
        ) AS [TyLeQuaMon_PhanTram]
    FROM dbo.classes c
    LEFT JOIN dbo.students st ON c.id = st.class_id
    LEFT JOIN dbo.scores sc ON st.id = sc.student_id
    WHERE (@ClassCode IS NULL OR c.class_code = UPPER(LTRIM(RTRIM(@ClassCode))))
    GROUP BY c.id, c.class_code, c.class_name, c.homeroom_teacher
    ORDER BY c.class_code ASC;
END
GO

/*------------------------------------------------------------------------------
  SP 4: dbo.usp_StatsBySubject
  Nghiệp vụ: Thống kê kết quả điểm thi theo Môn học và Học kỳ.
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_StatsBySubject
    @SubjectCode VARCHAR(50) = NULL,
    @Semester    VARCHAR(30) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT 
        sub.id AS [SubjectID],
        sub.subject_code AS [MaMon],
        sub.subject_name AS [TenMonHoc],
        sub.credits AS [SoTinChi],
        sub.department AS [BoMon],
        COUNT(sc.id) AS [SoSinhVienDuThi],
        ISNULL(ROUND(AVG(sc.final_score), 2), 0.0) AS [DiemTrungBinh],
        ISNULL(MAX(sc.final_score), 0.0) AS [DiemCaoNhat],
        ISNULL(MIN(sc.final_score), 0.0) AS [DiemThapNhat],
        SUM(CASE WHEN sc.final_score >= 4.0 THEN 1 ELSE 0 END) AS [SoSV_Dat],
        SUM(CASE WHEN sc.final_score < 4.0 AND sc.id IS NOT NULL THEN 1 ELSE 0 END) AS [SoSV_HocLai],
        ISNULL(
            ROUND(
                100.0 * SUM(CASE WHEN sc.final_score >= 4.0 THEN 1 ELSE 0 END) / NULLIF(COUNT(sc.id), 0),
                1
            ),
            0.0
        ) AS [TyLeDat_PhanTram]
    FROM dbo.subjects sub
    LEFT JOIN dbo.scores sc 
        ON sub.id = sc.subject_id
       AND (@Semester IS NULL OR sc.semester = UPPER(LTRIM(RTRIM(@Semester))))
    WHERE (@SubjectCode IS NULL OR sub.subject_code = UPPER(LTRIM(RTRIM(@SubjectCode))))
    GROUP BY sub.id, sub.subject_code, sub.subject_name, sub.credits, sub.department
    ORDER BY sub.subject_code ASC;
END
GO

/*------------------------------------------------------------------------------
  SP 5: dbo.usp_SearchStudentsAdvanced
  Nghiệp vụ: Tìm kiếm sinh viên theo từ khóa (mã SV, họ tên, email, quê quán),
             lọc theo mã lớp, giới tính và khoảng điểm GPA tích lũy.
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_SearchStudentsAdvanced
    @Keyword   NVARCHAR(100) = NULL,
    @ClassCode VARCHAR(50)   = NULL,
    @Gender    NVARCHAR(20)  = NULL,
    @MinGPA    FLOAT         = NULL,
    @MaxGPA    FLOAT         = NULL
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH CTE_StudentGPA AS (
        SELECT 
            st.id,
            st.student_code,
            st.full_name,
            st.date_of_birth,
            st.gender,
            st.email,
            st.hometown,
            c.class_code,
            c.class_name,
            COUNT(sc.id) AS subject_count,
            ISNULL(SUM(CASE WHEN sc.final_score >= 4.0 THEN sub.credits ELSE 0 END), 0) AS accumulated_credits,
            ISNULL(ROUND(SUM(sc.final_score * sub.credits) / NULLIF(SUM(sub.credits), 0), 2), 0.0) AS gpa_10
        FROM dbo.students st
        INNER JOIN dbo.classes c ON st.class_id = c.id
        LEFT JOIN dbo.scores sc ON st.id = sc.student_id
        LEFT JOIN dbo.subjects sub ON sc.subject_id = sub.id
        WHERE (@Keyword IS NULL 
               OR st.student_code LIKE '%' + @Keyword + '%'
               OR st.full_name LIKE N'%' + @Keyword + N'%'
               OR st.email LIKE '%' + @Keyword + '%'
               OR st.hometown LIKE N'%' + @Keyword + N'%')
          AND (@ClassCode IS NULL OR c.class_code = UPPER(LTRIM(RTRIM(@ClassCode))))
          AND (@Gender IS NULL OR st.gender = @Gender)
        GROUP BY st.id, st.student_code, st.full_name, st.date_of_birth, st.gender, st.email, st.hometown, c.class_code, c.class_name
    )
    SELECT 
        id AS [StudentID],
        student_code AS [MaSV],
        full_name AS [HoTen],
        date_of_birth AS [NgaySinh],
        gender AS [GioiTinh],
        email AS [Email],
        hometown AS [QueQuan],
        class_code AS [MaLop],
        class_name AS [TenLop],
        subject_count AS [SoMonDaHoc],
        accumulated_credits AS [TinChiTichLuy],
        gpa_10 AS [GPA_He10]
    FROM CTE_StudentGPA
    WHERE (@MinGPA IS NULL OR gpa_10 >= @MinGPA)
      AND (@MaxGPA IS NULL OR gpa_10 <= @MaxGPA)
    ORDER BY gpa_10 DESC, student_code ASC;
END
GO

PRINT N'=== ĐÃ KHỞI TẠO THÀNH CÔNG 5 STORED PROCEDURES (04_stored_procedures.sql) ===';
GO
