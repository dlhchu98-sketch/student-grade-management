# BÁO CÁO ĐỒ ÁN MÔN HỌC
## HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐÀO TẠO ĐẠI HỌC

> **Bộ nhận diện đồng bộ:** Đỏ nhận diện `#C62828` • Xanh dương nhạt `#DCEBFA` • Xanh dương đậm `#245A85` • Nền `#F5F7FA` • Thẻ `#FFFFFF`  
> **Kiến trúc:** Web SPA (Sidebar cố định bên trái + Đăng nhập phân quyền 3 đối tượng) • Backend FastAPI + Pydantic • Cơ sở dữ liệu Microsoft SQL Server (SSMS 22)

---

## 1. Tổng quan và Mục tiêu Đề tài

Hệ thống Quản lý Sinh viên và Đào tạo Đại học được xây dựng nhằm tin học hóa khép kín quy trình quản trị học vụ tại trường đại học, đảm bảo tính chính xác, minh bạch dữ liệu và phân quyền chặt chẽ cho **3 nhóm đối tượng**:

1. **Quản trị viên / Phòng Đào tạo (`ADMIN`):** Quản lý toàn hệ thống (hồ sơ sinh viên, lớp học, khoa/ngành, học phần, chương trình đào tạo, lớp học phần, bảng điểm, cảnh báo học vụ, quản lý tài khoản và phân quyền).
2. **Giảng viên / Cố vấn học tập (`LECTURER`):** Theo dõi lớp được phân công, tra cứu chương trình đào tạo, nhập/cập nhật điểm thành phần (40% quá trình + 60% điểm thi), và theo dõi tư vấn sinh viên thuộc diện cảnh báo học vụ.
3. **Sinh viên (`STUDENT`):** Xem Dashboard cá nhân, tra cứu khung chương trình đào tạo, đăng ký / hủy đăng ký học phần trực tuyến (kiểm tra sĩ số và học phần tiên quyết), xem bảng điểm chi tiết, GPA hệ 10 & hệ 4 theo học kỳ và tích lũy, cùng trạng thái cảnh báo học vụ cá nhân.

---

## 2. Thiết kế Hệ thống Giao diện (Design System)

### 2.1. Bảng màu nhận diện đại học
| Thành phần | Mã màu | Mục đích sử dụng |
| :--- | :---: | :--- |
| Đỏ nhận diện | `#C62828` | Logo, vạch đánh dấu mục đang chọn trên Sidebar, nút hành động chính, cảnh báo học vụ |
| Xanh dương nhạt | `#DCEBFA` | Nền Sidebar trái, panel nhận diện đăng nhập, thẻ trạng thái được chọn |
| Xanh dương đậm | `#245A85` | Tiêu đề phụ, biểu đồ thống kê, liên kết và điểm nhấn thông tin |
| Đỏ nhạt | `#FCE8E8` | Nền badge cảnh báo, nút xóa, thông báo lỗi |
| Nền tổng thể | `#F5F7FA` | Nền vùng làm việc chính dịu mắt |
| Nền thẻ nội dung | `#FFFFFF` | Thẻ KPI, biểu mẫu, bảng dữ liệu, khung biểu đồ |
| Chữ chính / Chữ phụ | `#263445` / `#718096` | Đảm bảo độ tương phản cao, dễ đọc khi trình chiếu và thao tác |
| Thành công / Cảnh báo | `#27865B` / `#D69E2E` | Trạng thái đạt môn, hoàn tất tư vấn / cảnh báo mức 1 |

### 2.2. Bố cục Sidebar cố định bên trái & Responsive
- **Desktop:** Sidebar cố định bên trái (rộng `264px`), thu gọn được về dạng icon (`76px`) kèm tooltip; vùng nội dung bên phải có header gọn hiển thị breadcrumb, tên trang, thông báo cảnh báo học vụ và tài khoản đang đăng nhập.
- **Tablet & Mobile:** Sidebar tự động chuyển thành menu trượt (drawer) có nút mở menu trên header, đảm bảo không che khuất nội dung và giữ nguyên đầy đủ chức năng.
- **Kiểm soát phân quyền 2 lớp:** Menu điều hướng tự động ẩn/hiện theo vai trò đang đăng nhập **đồng thời** Backend FastAPI kiểm tra Bearer token và trả về `403 Forbidden` nếu gọi API vượt quyền.

---

## 3. Thiết kế Cơ sở dữ liệu & Lập trình SQL Server

Toàn bộ thiết kế ERD, lược đồ quan hệ chuẩn hóa **3NF** (`classes`, `students`, `subjects`, `scores`) cùng 8 kịch bản T-SQL (`01_create_database.sql` đến `08_test_database.sql`) được giữ nguyên toàn vẹn nghiệp vụ và chi tiết tại [DATABASE_DESIGN_AND_SSMS22_GUIDE.md](file:///C:/Users/dlhch/.gemini/antigravity/scratch/student-grade-management/DATABASE_DESIGN_AND_SSMS22_GUIDE.md):

- **4 bảng cốt lõi chuẩn 3NF:** `dbo.classes`, `dbo.students`, `dbo.subjects`, `dbo.scores` (PK, FK, UNIQUE bộ 3 `(student_id, subject_id, semester)`, CHECK điểm `[0.0..10.0]` và tín chỉ `[1..15]`).
- **Các bảng học vụ & xác thực mở rộng:** `app_accounts` (3 đối tượng, băm mật khẩu `PBKDF2-HMAC-SHA256`), `curriculum_items`, `course_sections`, `enrollments`, `warning_records`.
- **SQL nâng cao:** 5 Stored Procedures, 4 User-Defined Functions, 4 Multi-row DML Triggers và 3 Stored Procedures Giao dịch (`BEGIN TRAN`, `TRY...CATCH`, `COMMIT/ROLLBACK`).

---

## 4. Kiến trúc API Backend & Nghiệp vụ Học vụ

| Nhóm API | Endpoint tiêu biểu | Phân quyền Backend |
| :--- | :--- | :--- |
| Xác thực 3 đối tượng | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout` | Công khai / Bearer Token |
| Quản lý tài khoản | `GET/POST/PATCH /api/auth/accounts` | Chỉ `ADMIN` (chặn `403`) |
| Dashboard thống kê | `GET /api/stats` | Theo vai trò đang đăng nhập |
| Quản lý đào tạo | `/api/students`, `/api/classes`, `/api/subjects`, `/api/curriculum`, `/api/sections` | CRUD `ADMIN`; xem phạm vi `LECTURER` |
| Đăng ký học phần | `GET/POST/DELETE /api/enrollments` | `STUDENT` & `ADMIN` (kiểm tra sĩ số & tiên quyết) |
| Điểm & GPA (10/4) | `/api/scores`, `GET /api/results` | Nhập/sửa `ADMIN` & `LECTURER`; SV chỉ xem của mình |
| Cảnh báo học vụ | `GET /api/warnings`, `PATCH /api/warnings/{student_id}` | Rà soát tự động; cập nhật xử lý `ADMIN` & `LECTURER` |

---

## 5. Tài khoản Kiểm thử 3 Đối tượng

| Đối tượng | Tên đăng nhập | Mật khẩu | Phạm vi truy cập |
| :--- | :---: | :---: | :--- |
| **1. Phòng Đào tạo (Admin)** | `admin` | `admin123` | Toàn quyền hệ thống (12 phân hệ) |
| **2. Giảng viên** | `gv.minh` | `gv123` | Xem lớp `CNTT01-K18`, `ATTT01-K18`, nhập/sửa điểm, cập nhật cảnh báo |
| **3. Sinh viên** | `SV2024001` | `sv123` | Dashboard cá nhân, CTĐT, Đăng ký học phần, Bảng điểm GPA (10/4), Cảnh báo cá nhân |

---

## 6. Kết quả Kiểm thử & Tài liệu Nộp

- **T-SQL SSMS 22 (`08_test_database.sql`):** 20/20 PASS.
- **FastAPI Backend & RBAC (`test_api.py` + kiểm thử phân quyền 3 đối tượng):** Đạt toàn bộ kiểm thử CRUD, ràng buộc toàn vẹn `400/404/409/422` và chặn vượt quyền `403`.
- **Slide thuyết trình bảo vệ:** [BAO_CAO_DO_AN.pptx](file:///C:/Users/dlhch/.gemini/antigravity/scratch/student-grade-management/BAO_CAO_DO_AN.pptx) (20 slide chuẩn 16:9) và [SLIDE_THUYET_TRINH.pdf](file:///C:/Users/dlhch/.gemini/antigravity/scratch/student-grade-management/SLIDE_THUYET_TRINH.pdf).
