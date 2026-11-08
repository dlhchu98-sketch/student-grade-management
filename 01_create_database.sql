/*==============================================================================
  FILE: 01_create_database.sql
  ĐỀ TÀI: HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐIỂM THI
  HỆ QUẢN TRỊ CSDL: MICROSOFT SQL SERVER (SSMS 22)
  MỤC ĐÍCH:
    - Khởi tạo Cơ sở dữ liệu [StudentGradeManagementDB] nếu chưa tồn tại.
    - Thiết lập các cấu hình chuẩn cho Database (Recovery Model, Snapshot Isolation).
    - Kiểm tra trạng thái sẵn sàng của Database.
==============================================================================*/

USE [master];
GO

-- 1. Kiểm tra và tạo mới Database StudentGradeManagementDB nếu chưa tồn tại
IF DB_ID(N'StudentGradeManagementDB') IS NULL
BEGIN
    PRINT N'>>> Đang khởi tạo cơ sở dữ liệu [StudentGradeManagementDB]...';
    CREATE DATABASE [StudentGradeManagementDB];
    PRINT N'>>> Đã khởi tạo [StudentGradeManagementDB] thành công.';
END
ELSE
BEGIN
    PRINT N'>>> Cơ sở dữ liệu [StudentGradeManagementDB] đã tồn tại. Tiếp tục cấu hình...';
END
GO

-- 2. Thiết lập các thuộc tính an toàn giao dịch và hiệu năng cho Database
-- Sử dụng WITH ROLLBACK IMMEDIATE để không bị treo khi đang có kết nối từ FastAPI hoặc SSMS 22
ALTER DATABASE [StudentGradeManagementDB] SET RECOVERY SIMPLE WITH ROLLBACK IMMEDIATE;
ALTER DATABASE [StudentGradeManagementDB] SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;
ALTER DATABASE [StudentGradeManagementDB] SET MULTI_USER WITH ROLLBACK IMMEDIATE;
GO

USE [StudentGradeManagementDB];
GO

-- 3. Truy vấn xác nhận thông tin Database vừa khởi tạo
SELECT 
    DB_ID(N'StudentGradeManagementDB') AS [DatabaseID],
    DB_NAME() AS [DatabaseName],
    create_date AS [CreatedDate],
    collation_name AS [Collation],
    recovery_model_desc AS [RecoveryModel],
    state_desc AS [Status]
FROM sys.databases
WHERE name = N'StudentGradeManagementDB';
GO
