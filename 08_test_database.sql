/*==============================================================================
  FILE: 08_test_database.sql
  ĐỀ TÀI: HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐIỂM THI
  HỆ QUẢN TRỊ CSDL: MICROSOFT SQL SERVER (SSMS 22)
  MỤC ĐÍCH:
    Kiểm thử toàn diện 20 kịch bản T-SQL:
      - Kiểm thử Ràng buộc (PK, FK, UNIQUE, CHECK, DEFAULT)
      - Kiểm thử 4 User-Defined Functions (Scalar & Table-Valued UDF)
      - Kiểm thử 5 Stored Procedures nghiệp vụ + trường hợp báo lỗi
      - Kiểm thử 4 DML Triggers (bao gồm cả xử lý Multi-row INSERT/UPDATE/DELETE)
      - Kiểm thử 3 Giao dịch (Transactions: COMMIT khi hợp lệ & ROLLBACK khi lỗi)
    Tổng hợp bảng kết quả PASS / FAIL cuối script.
==============================================================================*/

USE [StudentGradeManagementDB];
GO

SET NOCOUNT ON;
GO

IF OBJECT_ID(N'tempdb..#TestSummary') IS NOT NULL
    DROP TABLE #TestSummary;

CREATE TABLE #TestSummary (
    TestID      INT IDENTITY(1,1) PRIMARY KEY,
    Category    NVARCHAR(50),
    TestName    NVARCHAR(200),
    Status      NVARCHAR(10),
    Detail      NVARCHAR(400)
);
GO

/*==============================================================================
  PHẦN 1: KIỂM THỬ RÀNG BUỘC TOÀN VẸN (CONSTRAINTS: UNIQUE, CHECK, FK)
==============================================================================*/

-- Test 1: Kiểm tra UNIQUE constraint khi thêm trùng mã lớp (class_code)
BEGIN TRY
    INSERT INTO dbo.classes (class_code, class_name) VALUES ('CNTT01-K18', N'Lớp trùng mã');
    INSERT INTO #TestSummary VALUES (N'Constraints', N'1. Chặn trùng mã lớp học (UQ_classes_class_code)', N'FAIL', N'Cho phép chèn trùng mã lớp');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Constraints', N'1. Chặn trùng mã lớp học (UQ_classes_class_code)', N'PASS', ERROR_MESSAGE());
END CATCH;

-- Test 2: Kiểm tra CHECK constraint số tín chỉ môn học (credits phải từ 1..15)
BEGIN TRY
    INSERT INTO dbo.subjects (subject_code, subject_name, credits) VALUES ('IT9999', N'Môn tín chỉ sai', 25);
    INSERT INTO #TestSummary VALUES (N'Constraints', N'2. Chặn số tín chỉ ngoài khoảng 1-15 (CK_subjects_credits_range)', N'FAIL', N'Cho phép credits = 25');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Constraints', N'2. Chặn số tín chỉ ngoài khoảng 1-15 (CK_subjects_credits_range)', N'PASS', ERROR_MESSAGE());
END CATCH;

-- Test 3: Kiểm tra FOREIGN KEY khi thêm sinh viên vào class_id không tồn tại
BEGIN TRY
    INSERT INTO dbo.students (student_code, full_name, date_of_birth, gender, email, class_id)
    VALUES ('SV_ERR_FK', N'Sinh viên lỗi FK', '2005-01-01', N'Nam', 'errfk@student.edu.vn', 999999);
    INSERT INTO #TestSummary VALUES (N'Constraints', N'3. Chặn khóa ngoại class_id không tồn tại (FK_students_classes)', N'FAIL', N'Cho phép class_id không tồn tại');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Constraints', N'3. Chặn khóa ngoại class_id không tồn tại (FK_students_classes)', N'PASS', ERROR_MESSAGE());
END CATCH;

-- Test 4: Kiểm tra CHECK constraint giới tính sinh viên
BEGIN TRY
    DECLARE @ValidClassId INT = (SELECT TOP 1 id FROM dbo.classes ORDER BY id);
    INSERT INTO dbo.students (student_code, full_name, date_of_birth, gender, email, class_id)
    VALUES ('SV_ERR_GEN', N'Sinh viên lỗi giới tính', '2005-01-01', N'Không hợp lệ', 'errgen@student.edu.vn', @ValidClassId);
    INSERT INTO #TestSummary VALUES (N'Constraints', N'4. Chặn giới tính không hợp lệ (CK_students_gender_valid)', N'FAIL', N'Cho phép giới tính sai');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Constraints', N'4. Chặn giới tính không hợp lệ (CK_students_gender_valid)', N'PASS', ERROR_MESSAGE());
END CATCH;

/*==============================================================================
  PHẦN 2: KIỂM THỬ USER-DEFINED FUNCTIONS (05_functions.sql)
==============================================================================*/

-- Test 5: Kiểm thử hàm tính điểm tổng kết dbo.ufn_CalculateFinalScore(8.0, 9.0) -> 8.6
DECLARE @CalcFinal FLOAT = dbo.ufn_CalculateFinalScore(8.0, 9.0);
IF @CalcFinal = 8.6
    INSERT INTO #TestSummary VALUES (N'Functions', N'5. Hàm ufn_CalculateFinalScore(8.0, 9.0) = 8.6', N'PASS', CONCAT(N'Kết quả = ', @CalcFinal));
ELSE
    INSERT INTO #TestSummary VALUES (N'Functions', N'5. Hàm ufn_CalculateFinalScore(8.0, 9.0) = 8.6', N'FAIL', CONCAT(N'Kết quả sai = ', @CalcFinal));

-- Test 6: Kiểm thử hàm xếp loại học lực dbo.ufn_GetGradeClassification(8.6) -> Giỏi (A)
DECLARE @Rank NVARCHAR(30) = dbo.ufn_GetGradeClassification(8.6);
IF @Rank = N'Giỏi (A)'
    INSERT INTO #TestSummary VALUES (N'Functions', N'6. Hàm ufn_GetGradeClassification(8.6) = Giỏi (A)', N'PASS', CONCAT(N'Xếp loại = ', @Rank));
ELSE
    INSERT INTO #TestSummary VALUES (N'Functions', N'6. Hàm ufn_GetGradeClassification(8.6) = Giỏi (A)', N'FAIL', CONCAT(N'Xếp loại sai = ', @Rank));

-- Test 7: Kiểm thử hàm tính GPA tích lũy dbo.ufn_CalculateStudentGPA
DECLARE @FirstStudentId INT = (SELECT TOP 1 id FROM dbo.students WHERE student_code = 'SV2024001');
DECLARE @StudentGPA FLOAT = dbo.ufn_CalculateStudentGPA(@FirstStudentId);
IF @StudentGPA > 0.0
    INSERT INTO #TestSummary VALUES (N'Functions', N'7. Hàm ufn_CalculateStudentGPA tính GPA theo tín chỉ', N'PASS', CONCAT(N'GPA SV2024001 = ', @StudentGPA));
ELSE
    INSERT INTO #TestSummary VALUES (N'Functions', N'7. Hàm ufn_CalculateStudentGPA tính GPA theo tín chỉ', N'FAIL', N'GPA bằng 0');

-- Test 8: Kiểm thử hàm Table-Valued dbo.ufn_GetClassHonorRoll
DECLARE @HonorCount INT = (SELECT COUNT(*) FROM dbo.ufn_GetClassHonorRoll(NULL, 7.0));
IF @HonorCount >= 1
    INSERT INTO #TestSummary VALUES (N'Functions', N'8. Hàm bảng ufn_GetClassHonorRoll lấy danh sách SV giỏi/khá', N'PASS', CONCAT(N'Số SV đạt GPA >= 7.0: ', @HonorCount));
ELSE
    INSERT INTO #TestSummary VALUES (N'Functions', N'8. Hàm bảng ufn_GetClassHonorRoll lấy danh sách SV giỏi/khá', N'FAIL', N'Không trả về dữ liệu');

/*==============================================================================
  PHẦN 3: KIỂM THỬ STORED PROCEDURES NGHIỆP VỤ (04_stored_procedures.sql)
==============================================================================*/

-- Test 9: Kiểm thử SP usp_UpsertStudentScore (Hợp lệ)
BEGIN TRY
    EXEC dbo.usp_UpsertStudentScore 
        @StudentCode = 'SV2024001',
        @SubjectCode = 'IT3010',
        @Semester    = 'HK1-2026',
        @ProcessScore = 9.0,
        @ExamScore    = 8.5;
    INSERT INTO #TestSummary VALUES (N'Stored Procedures', N'9. SP usp_UpsertStudentScore cập nhật & tính điểm tổng kết', N'PASS', N'Thực thi thành công cho SV2024001 - IT3010');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Stored Procedures', N'9. SP usp_UpsertStudentScore cập nhật & tính điểm tổng kết', N'FAIL', ERROR_MESSAGE());
END CATCH;

-- Test 10: Kiểm thử SP usp_UpsertStudentScore chặn điểm > 10.0
BEGIN TRY
    EXEC dbo.usp_UpsertStudentScore 
        @StudentCode = 'SV2024001',
        @SubjectCode = 'IT3010',
        @Semester    = 'HK1-2026',
        @ProcessScore = 12.0,
        @ExamScore    = 8.5;
    INSERT INTO #TestSummary VALUES (N'Stored Procedures', N'10. SP usp_UpsertStudentScore chặn điểm > 10.0', N'FAIL', N'Cho phép điểm 12.0');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Stored Procedures', N'10. SP usp_UpsertStudentScore chặn điểm > 10.0', N'PASS', ERROR_MESSAGE());
END CATCH;

-- Test 11: Kiểm thử SP usp_GetStudentTranscriptAndGPA
BEGIN TRY
    EXEC dbo.usp_GetStudentTranscriptAndGPA @StudentCode = 'SV2024001';
    INSERT INTO #TestSummary VALUES (N'Stored Procedures', N'11. SP usp_GetStudentTranscriptAndGPA xuất bảng điểm & GPA', N'PASS', N'Truy xuất thành công bảng điểm SV2024001');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Stored Procedures', N'11. SP usp_GetStudentTranscriptAndGPA xuất bảng điểm & GPA', N'FAIL', ERROR_MESSAGE());
END CATCH;

-- Test 12: Kiểm thử SP usp_StatsByClass & usp_StatsBySubject & usp_SearchStudentsAdvanced
BEGIN TRY
    EXEC dbo.usp_StatsByClass @ClassCode = 'CNTT01-K18';
    EXEC dbo.usp_StatsBySubject @SubjectCode = 'IT3010', @Semester = 'HK1-2026';
    EXEC dbo.usp_SearchStudentsAdvanced @Keyword = N'Nguyễn', @MinGPA = 5.0;
    INSERT INTO #TestSummary VALUES (N'Stored Procedures', N'12. SP Thống kê theo Lớp, Môn học & Tìm kiếm nâng cao', N'PASS', N'Thực thi thành công cả 3 SP thống kê/tìm kiếm');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Stored Procedures', N'12. SP Thống kê theo Lớp, Môn học & Tìm kiếm nâng cao', N'FAIL', ERROR_MESSAGE());
END CATCH;

/*==============================================================================
  PHẦN 4: KIỂM THỬ DML TRIGGERS & XỬ LÝ NHIỀU DÒNG (MULTI-ROW TRIGGERS)
==============================================================================*/

-- Test 13: Trigger trg_Scores_ValidateAndSyncFinal tự động tính lại final_score khi INSERT nhiều dòng cùng lúc (Multi-row INSERT)
BEGIN TRY
    DECLARE @St1 INT = (SELECT id FROM dbo.students WHERE student_code = 'SV2024002');
    DECLARE @St2 INT = (SELECT id FROM dbo.students WHERE student_code = 'SV2024003');
    DECLARE @SubTest INT = (SELECT id FROM dbo.subjects WHERE subject_code = 'IT3040');

    -- Chèn 2 dòng cùng lúc với final_score cố tình truyền bằng 0.0 để kiểm tra Trigger tự động tính lại cho cả 2 dòng
    INSERT INTO dbo.scores (student_id, subject_id, semester, process_score, exam_score, final_score)
    VALUES 
        (@St1, @SubTest, 'HK2-2026-TEST', 8.0, 9.0, 0.0), -- Kỳ vọng Trigger cập nhật final_score = 8.6
        (@St2, @SubTest, 'HK2-2026-TEST', 7.0, 8.0, 0.0); -- Kỳ vọng Trigger cập nhật final_score = 7.6

    DECLARE @VerifyCount INT = (
        SELECT COUNT(*) FROM dbo.scores
        WHERE semester = 'HK2-2026-TEST' AND final_score IN (8.6, 7.6)
    );

    -- Dọn dẹp 2 dòng test
    DELETE FROM dbo.scores WHERE semester = 'HK2-2026-TEST';

    IF @VerifyCount = 2
        INSERT INTO #TestSummary VALUES (N'Triggers (Multi-row)', N'13. Trigger trg_Scores_ValidateAndSyncFinal xử lý INSERT nhiều dòng', N'PASS', N'Tự động đồng bộ final_score (8.6 và 7.6) cho cả 2 dòng');
    ELSE
        INSERT INTO #TestSummary VALUES (N'Triggers (Multi-row)', N'13. Trigger trg_Scores_ValidateAndSyncFinal xử lý INSERT nhiều dòng', N'FAIL', CONCAT(N'VerifyCount = ', @VerifyCount));
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Triggers (Multi-row)', N'13. Trigger trg_Scores_ValidateAndSyncFinal xử lý INSERT nhiều dòng', N'FAIL', ERROR_MESSAGE());
END CATCH;

-- Test 14: Trigger trg_Classes_PreventDeleteLinked chặn xóa nhiều lớp học đang có sinh viên (Multi-row DELETE)
BEGIN TRY
    DELETE FROM dbo.classes WHERE class_code IN ('CNTT01-K18', 'CNTT02-K18');
    INSERT INTO #TestSummary VALUES (N'Triggers (Multi-row)', N'14. Trigger trg_Classes_PreventDeleteLinked chặn xóa lớp đang có SV', N'FAIL', N'Cho phép xóa lớp đang có sinh viên');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Triggers (Multi-row)', N'14. Trigger trg_Classes_PreventDeleteLinked chặn xóa lớp đang có SV', N'PASS', ERROR_MESSAGE());
END CATCH;

-- Test 15: Trigger trg_Students_PreventDeleteLinked chặn xóa sinh viên đã có điểm thi
BEGIN TRY
    DELETE FROM dbo.students WHERE student_code IN ('SV2024001', 'SV2024002');
    INSERT INTO #TestSummary VALUES (N'Triggers (Multi-row)', N'15. Trigger trg_Students_PreventDeleteLinked chặn xóa SV đã có điểm', N'FAIL', N'Cho phép xóa SV đã có điểm');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Triggers (Multi-row)', N'15. Trigger trg_Students_PreventDeleteLinked chặn xóa SV đã có điểm', N'PASS', ERROR_MESSAGE());
END CATCH;

-- Test 16: Trigger trg_Subjects_PreventDeleteLinked chặn xóa môn học đã có điểm thi
BEGIN TRY
    DELETE FROM dbo.subjects WHERE subject_code = 'IT3010';
    INSERT INTO #TestSummary VALUES (N'Triggers (Multi-row)', N'16. Trigger trg_Subjects_PreventDeleteLinked chặn xóa môn đã có điểm', N'FAIL', N'Cho phép xóa môn học đã có điểm');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Triggers (Multi-row)', N'16. Trigger trg_Subjects_PreventDeleteLinked chặn xóa môn đã có điểm', N'PASS', ERROR_MESSAGE());
END CATCH;

/*==============================================================================
  PHẦN 5: KIỂM THỬ GIAO DỊCH AN TOÀN (TRANSACTIONS: COMMIT & ROLLBACK)
==============================================================================*/

-- Test 17: Giao dịch ROLLBACK khi điểm không hợp lệ -> Sinh viên KHÔNG bị tạo dở dang trong dbo.students
BEGIN TRY
    DECLARE @ClsId INT = (SELECT TOP 1 id FROM dbo.classes WHERE class_code = 'CNTT01-K18');
    DECLARE @SubId INT = (SELECT TOP 1 id FROM dbo.subjects WHERE subject_code = 'IT3010');

    EXEC dbo.usp_Tran_RegisterStudentWithScores
        @StudentCode  = 'SV_ROLLBACK_01',
        @FullName     = N'Sinh Viên Kiểm Thử Rollback',
        @DateOfBirth  = '2005-05-05',
        @Gender       = N'Nam',
        @Email        = 'rollback01@student.edu.vn',
        @Hometown     = N'Hà Nội',
        @ClassId      = @ClsId,
        @SubjectId    = @SubId,
        @Semester     = 'HK1-2026',
        @ProcessScore = 8.0,
        @ExamScore    = 15.0; -- Điểm > 10.0 gây lỗi ở bước 3 sau khi đã INSERT dbo.students
END TRY
BEGIN CATCH
    -- Kiểm tra chắc chắn rằng sinh viên SV_ROLLBACK_01 đã được ROLLBACK khỏi dbo.students
    IF NOT EXISTS (SELECT 1 FROM dbo.students WHERE student_code = 'SV_ROLLBACK_01')
        INSERT INTO #TestSummary VALUES (N'Transactions', N'17. ROLLBACK usp_Tran_RegisterStudentWithScores khi điểm lỗi', N'PASS', N'Đã ROLLBACK hoàn toàn, không để lại sinh viên dở dang');
    ELSE
        INSERT INTO #TestSummary VALUES (N'Transactions', N'17. ROLLBACK usp_Tran_RegisterStudentWithScores khi điểm lỗi', N'FAIL', N'Dữ liệu sinh viên bị lưu dở dang');
END CATCH;

-- Test 18: Giao dịch COMMIT thành công khi thêm đồng thời Sinh viên + Điểm thi và xóa sạch qua giao dịch
BEGIN TRY
    DECLARE @ClsId2 INT = (SELECT TOP 1 id FROM dbo.classes WHERE class_code = 'CNTT01-K18');
    DECLARE @SubId2 INT = (SELECT TOP 1 id FROM dbo.subjects WHERE subject_code = 'IT3010');

    EXEC dbo.usp_Tran_RegisterStudentWithScores
        @StudentCode  = 'SV_COMMIT_01',
        @FullName     = N'Sinh Viên Kiểm Thử Commit',
        @DateOfBirth  = '2005-06-06',
        @Gender       = N'Nữ',
        @Email        = 'commit01@student.edu.vn',
        @Hometown     = N'Đà Nẵng',
        @ClassId      = @ClsId2,
        @SubjectId    = @SubId2,
        @Semester     = 'HK1-2026',
        @ProcessScore = 9.0,
        @ExamScore    = 8.0;

    DECLARE @CreatedStId INT = (SELECT id FROM dbo.students WHERE student_code = 'SV_COMMIT_01');

    -- Kiểm thử chuyển lớp + cập nhật điểm qua giao dịch (ROLLBACK khi vượt sĩ số tối đa @MaxCapacity = 1)
    BEGIN TRY
        DECLARE @OtherClsId INT = (SELECT TOP 1 id FROM dbo.classes WHERE class_code = 'CNTT02-K18');
        EXEC dbo.usp_Tran_TransferStudentAndRecordScore
            @StudentId     = @CreatedStId,
            @TargetClassId = @OtherClsId,
            @SubjectId     = @SubId2,
            @Semester      = 'HK1-2026',
            @ProcessScore  = 9.0,
            @ExamScore     = 9.0,
            @MaxCapacity   = 1; -- Cố tình đặt sĩ số tối đa = 1 để kích hoạt ROLLBACK
        INSERT INTO #TestSummary VALUES (N'Transactions', N'18. ROLLBACK usp_Tran_TransferStudentAndRecordScore khi vượt sĩ số', N'FAIL', N'Không chặn khi vượt sĩ số');
    END TRY
    BEGIN CATCH
        IF ERROR_NUMBER() = 50306
            INSERT INTO #TestSummary VALUES (N'Transactions', N'18. ROLLBACK usp_Tran_TransferStudentAndRecordScore khi vượt sĩ số', N'PASS', ERROR_MESSAGE());
        ELSE
            INSERT INTO #TestSummary VALUES (N'Transactions', N'18. ROLLBACK usp_Tran_TransferStudentAndRecordScore khi vượt sĩ số', N'FAIL', ERROR_MESSAGE());
    END CATCH;

    -- Kiểm thử chuyển lớp + cập nhật điểm hợp lệ (COMMIT khi @MaxCapacity = 50)
    EXEC dbo.usp_Tran_TransferStudentAndRecordScore
        @StudentId     = @CreatedStId,
        @TargetClassId = @OtherClsId,
        @SubjectId     = @SubId2,
        @Semester      = 'HK1-2026',
        @ProcessScore  = 9.5,
        @ExamScore     = 9.5,
        @MaxCapacity   = 50;

    IF EXISTS (SELECT 1 FROM dbo.students WHERE id = @CreatedStId AND class_id = @OtherClsId)
        INSERT INTO #TestSummary VALUES (N'Transactions', N'19. COMMIT usp_Tran_TransferStudentAndRecordScore chuyển lớp & điểm', N'PASS', N'Chuyển lớp và cập nhật điểm thành công');
    ELSE
        INSERT INTO #TestSummary VALUES (N'Transactions', N'19. COMMIT usp_Tran_TransferStudentAndRecordScore chuyển lớp & điểm', N'FAIL', N'Chưa cập nhật lớp');

    -- Dọn dẹp bằng Giao dịch xóa toàn bộ điểm + sinh viên (usp_Tran_DeleteStudentAndAllScores)
    EXEC dbo.usp_Tran_DeleteStudentAndAllScores @StudentId = @CreatedStId;

    IF NOT EXISTS (SELECT 1 FROM dbo.students WHERE id = @CreatedStId)
        INSERT INTO #TestSummary VALUES (N'Transactions', N'20. COMMIT usp_Tran_Register & usp_Tran_DeleteStudentAndAllScores', N'PASS', N'Tạo mới và xóa liên bảng trong giao dịch thành công');
    ELSE
        INSERT INTO #TestSummary VALUES (N'Transactions', N'20. COMMIT usp_Tran_Register & usp_Tran_DeleteStudentAndAllScores', N'FAIL', N'Chưa xóa sạch dữ liệu');
END TRY
BEGIN CATCH
    INSERT INTO #TestSummary VALUES (N'Transactions', N'19. COMMIT usp_Tran_Register & usp_Tran_DeleteStudentAndAllScores', N'FAIL', ERROR_MESSAGE());
END CATCH;

/*==============================================================================
  XUẤT BÁO CÁO KẾT QUẢ KIỂM THỬ DATABASE & T-SQL
==============================================================================*/
SELECT 
    TestID   AS [STT],
    Category AS [Nhóm Kiểm Thử],
    TestName AS [Kịch Bản Kiểm Thử],
    Status   AS [Kết Quả],
    Detail   AS [Chi Tiết / Thông Điệp]
FROM #TestSummary
ORDER BY TestID ASC;

SELECT 
    COUNT(*) AS [Tổng Số Kịch Bản],
    SUM(CASE WHEN Status = N'PASS' THEN 1 ELSE 0 END) AS [Số Kịch Bản ĐẠT (PASS)],
    SUM(CASE WHEN Status = N'FAIL' THEN 1 ELSE 0 END) AS [Số Kịch Bản CHƯA ĐẠT (FAIL)]
FROM #TestSummary;
GO
