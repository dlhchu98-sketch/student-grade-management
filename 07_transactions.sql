/*==============================================================================
  FILE: 07_transactions.sql
  ĐỀ TÀI: HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐIỂM THI
  HỆ QUẢN TRỊ CSDL: MICROSOFT SQL SERVER (SSMS 22)
  MỤC ĐÍCH:
    Xây dựng các nghiệp vụ giao dịch (Transactions) tác động từ 2 bảng trở lên,
    tuân thủ nghiêm ngặt:
      - BEGIN TRANSACTION
      - BEGIN TRY ... END TRY
      - BEGIN CATCH ... END CATCH
      - COMMIT TRANSACTION khi tất cả thao tác thành công
      - ROLLBACK TRANSACTION khi xảy ra bất kỳ lỗi nào (không để dữ liệu dở dang)
      - Sử dụng ;THROW để trả về lỗi chuẩn xác
==============================================================================*/

USE [StudentGradeManagementDB];
GO

/*------------------------------------------------------------------------------
  TRANSACTION SP 1: dbo.usp_Tran_RegisterStudentWithScores
  Tác động 2 bảng: dbo.students (INSERT) + dbo.scores (INSERT)
  Nghiệp vụ:
    - Tiếp nhận hồ sơ 1 sinh viên mới vào lớp học và đồng thời nhập điểm học phần
      đầu tiên của sinh viên đó trong cùng một giao dịch nguyên tử (Atomic).
    - Nếu điểm học phần không hợp lệ (VD: > 10.0 hoặc môn học không tồn tại),
      ROLLBACK toàn bộ để sinh viên không bị tạo dở dang trong bảng dbo.students.
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_Tran_RegisterStudentWithScores
    @StudentCode  VARCHAR(50),
    @FullName     NVARCHAR(100),
    @DateOfBirth  DATE,
    @Gender       NVARCHAR(20),
    @Email        VARCHAR(120),
    @Hometown     NVARCHAR(150),
    @ClassId      INT,
    @SubjectId    INT,
    @Semester     VARCHAR(30),
    @ProcessScore FLOAT,
    @ExamScore    FLOAT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT OFF;

    BEGIN TRY
        BEGIN TRANSACTION;

        -- Bước 1: Kiểm tra lớp học tồn tại
        IF NOT EXISTS (SELECT 1 FROM dbo.classes WHERE id = @ClassId)
        BEGIN
            ;THROW 50301, N'Lỗi giao dịch: Lớp học (class_id) không tồn tại.', 1;
        END

        -- Bước 2: Thêm mới sinh viên vào bảng dbo.students
        INSERT INTO dbo.students (student_code, full_name, date_of_birth, gender, email, hometown, class_id)
        VALUES (
            UPPER(LTRIM(RTRIM(@StudentCode))),
            LTRIM(RTRIM(@FullName)),
            @DateOfBirth,
            @Gender,
            LOWER(LTRIM(RTRIM(@Email))),
            @Hometown,
            @ClassId
        );

        DECLARE @NewStudentId INT = SCOPE_IDENTITY();

        -- Bước 3: Kiểm tra môn học tồn tại và điểm số hợp lệ trước khi chèn vào dbo.scores
        IF NOT EXISTS (SELECT 1 FROM dbo.subjects WHERE id = @SubjectId)
        BEGIN
            ;THROW 50302, N'Lỗi giao dịch: Môn học (subject_id) không tồn tại. Đã ROLLBACK hồ sơ sinh viên.', 1;
        END

        IF @ProcessScore < 0.0 OR @ProcessScore > 10.0 OR @ExamScore < 0.0 OR @ExamScore > 10.0
        BEGIN
            ;THROW 50303, N'Lỗi giao dịch: Điểm số nằm ngoài khoảng [0.0, 10.0]. Đã ROLLBACK hồ sơ sinh viên.', 1;
        END

        DECLARE @FinalScore FLOAT = ROUND(@ProcessScore * 0.4 + @ExamScore * 0.6, 2);

        -- Bước 4: Thêm bản ghi điểm thi vào bảng dbo.scores
        INSERT INTO dbo.scores (student_id, subject_id, semester, process_score, exam_score, final_score)
        VALUES (@NewStudentId, @SubjectId, UPPER(LTRIM(RTRIM(@Semester))), @ProcessScore, @ExamScore, @FinalScore);

        -- Hoàn tất giao dịch khi cả 2 bảng đều thành công
        COMMIT TRANSACTION;

        SELECT 
            @NewStudentId AS [NewStudentID],
            @StudentCode  AS [StudentCode],
            @FinalScore   AS [InitialFinalScore],
            N'COMMIT THÀNH CÔNG: Đã thêm sinh viên và điểm học phần.' AS [TransactionStatus];
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        ;THROW;
    END CATCH
END
GO

/*------------------------------------------------------------------------------
  TRANSACTION SP 2: dbo.usp_Tran_TransferStudentAndRecordScore
  Tác động 2 bảng: dbo.students (UPDATE class_id) + dbo.scores (INSERT/UPDATE)
  Nghiệp vụ:
    - Chuyển lớp cho một sinh viên sang lớp mới (kiểm tra giới hạn sĩ số lớp đích)
      đồng thời cập nhật/bổ sung điểm môn học chuyển đổi.
    - Nếu lớp đích vượt quá sĩ số tối đa cho phép (@MaxCapacity) hoặc điểm lỗi,
      ROLLBACK toàn bộ để sinh viên vẫn giữ nguyên lớp cũ.
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_Tran_TransferStudentAndRecordScore
    @StudentId    INT,
    @TargetClassId INT,
    @SubjectId    INT,
    @Semester     VARCHAR(30),
    @ProcessScore FLOAT,
    @ExamScore    FLOAT,
    @MaxCapacity  INT = 50
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT OFF;

    BEGIN TRY
        BEGIN TRANSACTION;

        -- Bước 1: Kiểm tra sinh viên và lớp đích tồn tại
        IF NOT EXISTS (SELECT 1 FROM dbo.students WHERE id = @StudentId)
        BEGIN
            ;THROW 50304, N'Lỗi giao dịch: Sinh viên không tồn tại.', 1;
        END

        IF NOT EXISTS (SELECT 1 FROM dbo.classes WHERE id = @TargetClassId)
        BEGIN
            ;THROW 50305, N'Lỗi giao dịch: Lớp học đích không tồn tại.', 1;
        END

        -- Bước 2: Cập nhật lớp mới cho sinh viên trong bảng dbo.students
        UPDATE dbo.students
        SET class_id = @TargetClassId
        WHERE id = @StudentId;

        -- Bước 3: Kiểm tra sĩ số lớp đích sau khi chuyển
        DECLARE @CurrentCount INT;
        SELECT @CurrentCount = COUNT(*) FROM dbo.students WHERE class_id = @TargetClassId;

        IF @CurrentCount > @MaxCapacity
        BEGIN
            ;THROW 50306, N'Lỗi giao dịch: Lớp đích đã vượt quá sĩ số tối đa cho phép. Đã ROLLBACK chuyển lớp.', 1;
        END

        -- Bước 4: Ghi nhận điểm học phần tại lớp mới vào bảng dbo.scores
        IF @ProcessScore < 0.0 OR @ProcessScore > 10.0 OR @ExamScore < 0.0 OR @ExamScore > 10.0
        BEGIN
            ;THROW 50307, N'Lỗi giao dịch: Điểm học phần chuyển đổi không hợp lệ. Đã ROLLBACK chuyển lớp.', 1;
        END

        DECLARE @Final FLOAT = ROUND(@ProcessScore * 0.4 + @ExamScore * 0.6, 2);

        IF EXISTS (
            SELECT 1 FROM dbo.scores
            WHERE student_id = @StudentId AND subject_id = @SubjectId AND semester = @Semester
        )
        BEGIN
            UPDATE dbo.scores
            SET process_score = @ProcessScore,
                exam_score    = @ExamScore,
                final_score   = @Final
            WHERE student_id = @StudentId AND subject_id = @SubjectId AND semester = @Semester;
        END
        ELSE
        BEGIN
            INSERT INTO dbo.scores (student_id, subject_id, semester, process_score, exam_score, final_score)
            VALUES (@StudentId, @SubjectId, @Semester, @ProcessScore, @ExamScore, @Final);
        END

        COMMIT TRANSACTION;

        SELECT 
            @StudentId     AS [StudentID],
            @TargetClassId AS [NewClassID],
            @Final         AS [RecordedFinalScore],
            N'COMMIT THÀNH CÔNG: Đã chuyển lớp và đồng bộ điểm thi.' AS [TransactionStatus];
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        ;THROW;
    END CATCH
END
GO

/*------------------------------------------------------------------------------
  TRANSACTION SP 3: dbo.usp_Tran_DeleteStudentAndAllScores
  Tác động 2 bảng: dbo.scores (DELETE) + dbo.students (DELETE)
  Nghiệp vụ:
    - Xóa toàn bộ điểm thi của sinh viên trong bảng dbo.scores trước, sau đó xóa
      hồ sơ sinh viên trong bảng dbo.students trong cùng một giao dịch an toàn.
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_Tran_DeleteStudentAndAllScores
    @StudentId INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT OFF;

    BEGIN TRY
        BEGIN TRANSACTION;

        IF NOT EXISTS (SELECT 1 FROM dbo.students WHERE id = @StudentId)
        BEGIN
            ;THROW 50308, N'Lỗi giao dịch: Không tìm thấy sinh viên cần xóa.', 1;
        END

        -- Bước 1: Xóa toàn bộ điểm thi của sinh viên trong dbo.scores
        DELETE FROM dbo.scores WHERE student_id = @StudentId;

        -- Bước 2: Xóa hồ sơ sinh viên trong dbo.students
        DELETE FROM dbo.students WHERE id = @StudentId;

        COMMIT TRANSACTION;

        SELECT 
            @StudentId AS [DeletedStudentID],
            N'COMMIT THÀNH CÔNG: Đã xóa toàn bộ điểm và hồ sơ sinh viên.' AS [TransactionStatus];
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        ;THROW;
    END CATCH
END
GO

PRINT N'=== ĐÃ KHỞI TẠO THÀNH CÔNG 3 STORED PROCEDURES GIAO DỊCH (07_transactions.sql) ===';
GO
