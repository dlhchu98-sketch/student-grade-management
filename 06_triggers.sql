/*==============================================================================
  FILE: 06_triggers.sql
  ĐỀ TÀI: HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐIỂM THI
  HỆ QUẢN TRỊ CSDL: MICROSOFT SQL SERVER (SSMS 22)
  MỤC ĐÍCH:
    Xây dựng 4 DML Triggers (xử lý chuẩn xác trên tập nhiều dòng - Multi-row
    inserted / deleted) để kiểm soát toàn vẹn dữ liệu liên bảng:
      1. dbo.trg_Scores_ValidateAndSyncFinal (AFTER INSERT, UPDATE ON dbo.scores):
         - Ngăn nhập/cập nhật điểm cho sinh viên không thuộc lớp học hợp lệ.
         - Kiểm soát khoảng điểm [0.0, 10.0] và tự động tính lại final_score
           cho toàn bộ các dòng được thêm/sửa cùng lúc.
      2. dbo.trg_Classes_PreventDeleteLinked (INSTEAD OF DELETE ON dbo.classes):
         - Ngăn xóa một hoặc nhiều lớp học đang có sinh viên theo học.
      3. dbo.trg_Students_PreventDeleteLinked (INSTEAD OF DELETE ON dbo.students):
         - Ngăn xóa một hoặc nhiều sinh viên đã phát sinh dữ liệu điểm thi.
      4. dbo.trg_Subjects_PreventDeleteLinked (INSTEAD OF DELETE ON dbo.subjects):
         - Ngăn xóa một hoặc nhiều môn học đã phát sinh dữ liệu điểm thi.
==============================================================================*/

USE [StudentGradeManagementDB];
GO

/*------------------------------------------------------------------------------
  TRIGGER 1: dbo.trg_Scores_ValidateAndSyncFinal
  Bảng áp dụng: dbo.scores (AFTER INSERT, UPDATE)
  Xử lý đa dòng (Multi-row): Sử dụng bảng ảo `inserted` kết nối với `dbo.students`
  và `dbo.classes` để kiểm tra toàn bộ các dòng được INSERT/UPDATE trong 1 lệnh.
------------------------------------------------------------------------------*/
CREATE OR ALTER TRIGGER dbo.trg_Scores_ValidateAndSyncFinal
ON dbo.scores
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- Nếu lệnh không tác động dòng nào thì thoát ngay
    IF NOT EXISTS (SELECT 1 FROM inserted)
        RETURN;

    -- 1. Kiểm tra sinh viên được nhập điểm phải tồn tại và thuộc một lớp học hợp lệ
    IF EXISTS (
        SELECT 1
        FROM inserted i
        LEFT JOIN dbo.students st ON i.student_id = st.id
        LEFT JOIN dbo.classes c ON st.class_id = c.id
        WHERE st.id IS NULL OR c.id IS NULL
    )
    BEGIN
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        ;THROW 50201, N'Trigger [trg_Scores_ValidateAndSyncFinal]: Không thể nhập điểm cho sinh viên không tồn tại hoặc không thuộc lớp học hợp lệ.', 1;
    END

    -- 2. Kiểm soát tính hợp lệ của điểm quá trình và điểm thi (0.0 - 10.0) trên mọi dòng
    IF EXISTS (
        SELECT 1
        FROM inserted i
        WHERE i.process_score < 0.0 OR i.process_score > 10.0
           OR i.exam_score < 0.0 OR i.exam_score > 10.0
           OR LEN(LTRIM(RTRIM(ISNULL(i.semester, '')))) = 0
    )
    BEGIN
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        ;THROW 50202, N'Trigger [trg_Scores_ValidateAndSyncFinal]: Điểm quá trình, điểm thi phải trong khoảng [0.0, 10.0] và học kỳ không được để trống.', 1;
    END

    -- 3. Tự động đồng bộ điểm tổng kết (final_score = 40% QT + 60% Thi) cho tất cả dòng trong inserted
    UPDATE sc
    SET sc.final_score = ROUND(i.process_score * 0.4 + i.exam_score * 0.6, 2),
        sc.semester    = UPPER(LTRIM(RTRIM(i.semester)))
    FROM dbo.scores sc
    INNER JOIN inserted i ON sc.id = i.id
    WHERE ABS(sc.final_score - ROUND(i.process_score * 0.4 + i.exam_score * 0.6, 2)) > 0.0001
       OR sc.semester <> UPPER(LTRIM(RTRIM(i.semester)));
END
GO

/*------------------------------------------------------------------------------
  TRIGGER 2: dbo.trg_Classes_PreventDeleteLinked
  Bảng áp dụng: dbo.classes (INSTEAD OF DELETE)
  Xử lý đa dòng (Multi-row): Kiểm tra tập `deleted`; nếu bất kỳ lớp nào đang có
  sinh viên trong `dbo.students` thì chặn xóa và báo lỗi nghiệp vụ rõ ràng.
------------------------------------------------------------------------------*/
CREATE OR ALTER TRIGGER dbo.trg_Classes_PreventDeleteLinked
ON dbo.classes
INSTEAD OF DELETE
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM deleted)
        RETURN;

    -- Kiểm tra nếu có bất kỳ lớp học nào trong tập deleted đang có sinh viên
    IF EXISTS (
        SELECT 1
        FROM deleted d
        INNER JOIN dbo.students st ON st.class_id = d.id
    )
    BEGIN
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        ;THROW 50203, N'Trigger [trg_Classes_PreventDeleteLinked]: Không thể xóa lớp học vì đang có sinh viên thuộc lớp này.', 1;
    END

    -- Cho phép xóa các lớp học không có dữ liệu liên kết (bật lại NOCOUNT OFF để trả đúng rowcount cho ORM)
    SET NOCOUNT OFF;
    DELETE c
    FROM dbo.classes c
    INNER JOIN deleted d ON c.id = d.id;
END
GO

/*------------------------------------------------------------------------------
  TRIGGER 3: dbo.trg_Students_PreventDeleteLinked
  Bảng áp dụng: dbo.students (INSTEAD OF DELETE)
  Xử lý đa dòng (Multi-row): Ngăn xóa sinh viên đã có điểm thi trong `dbo.scores`.
------------------------------------------------------------------------------*/
CREATE OR ALTER TRIGGER dbo.trg_Students_PreventDeleteLinked
ON dbo.students
INSTEAD OF DELETE
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM deleted)
        RETURN;

    IF EXISTS (
        SELECT 1
        FROM deleted d
        INNER JOIN dbo.scores sc ON sc.student_id = d.id
    )
    BEGIN
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        ;THROW 50204, N'Trigger [trg_Students_PreventDeleteLinked]: Không thể xóa sinh viên đã có dữ liệu điểm thi trong hệ thống.', 1;
    END

    SET NOCOUNT OFF;
    DELETE st
    FROM dbo.students st
    INNER JOIN deleted d ON st.id = d.id;
END
GO

/*------------------------------------------------------------------------------
  TRIGGER 4: dbo.trg_Subjects_PreventDeleteLinked
  Bảng áp dụng: dbo.subjects (INSTEAD OF DELETE)
  Xử lý đa dòng (Multi-row): Ngăn xóa môn học đã có điểm thi trong `dbo.scores`.
------------------------------------------------------------------------------*/
CREATE OR ALTER TRIGGER dbo.trg_Subjects_PreventDeleteLinked
ON dbo.subjects
INSTEAD OF DELETE
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM deleted)
        RETURN;

    IF EXISTS (
        SELECT 1
        FROM deleted d
        INNER JOIN dbo.scores sc ON sc.subject_id = d.id
    )
    BEGIN
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        ;THROW 50205, N'Trigger [trg_Subjects_PreventDeleteLinked]: Không thể xóa môn học đã phát sinh bản ghi điểm thi.', 1;
    END

    SET NOCOUNT OFF;
    DELETE sub
    FROM dbo.subjects sub
    INNER JOIN deleted d ON sub.id = d.id;
END
GO

PRINT N'=== ĐÃ KHỞI TẠO THÀNH CÔNG 4 DML TRIGGERS ĐA DÒNG (06_triggers.sql) ===';
GO
