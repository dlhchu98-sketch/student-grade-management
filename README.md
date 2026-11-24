# 🎓 Hệ thống Quản lý Sinh viên và Điểm thi (Student & Grade Management System)

Hệ thống quản lý giáo dục toàn diện được xây dựng với **FastAPI** (Backend), **Microsoft SQL Server** (Cơ sở dữ liệu), **Pydantic** (Kiểm tra dữ liệu) và **HTML5 / CSS3 / JavaScript Fetch API** (Frontend phục vụ tại `/` bằng `StaticFiles`).

---

## ✨ Tính năng Chính (Phiên bản Nâng cấp Design System & Phân quyền 3 Đối tượng)

1. **Cổng Đăng nhập & Phân quyền 3 Đối tượng (Frontend + Backend API `403`):**
   - **Phòng Đào tạo / Quản trị viên (`ADMIN`):** `admin` / `admin123` — Toàn quyền quản lý 12 phân hệ & tài khoản.
   - **Giảng viên (`LECTURER`):** `gv.minh` / `gv123` (hoặc `gv.ha` / `gv123`) — Theo dõi lớp phụ trách, nhập/sửa điểm, cập nhật tư vấn cảnh báo học vụ.
   - **Sinh viên (`STUDENT`):** `SV2024001` / `sv123` (hoặc `SV2024006` / `sv123`) — Dashboard cá nhân, Chương trình đào tạo, Đăng ký học phần (kiểm tra sĩ số & tiên quyết), Bảng điểm GPA hệ 10 & hệ 4, Cảnh báo học vụ cá nhân.
2. **Giao diện Sidebar Cố định Bên trái & Bộ nhận diện Đại học (`#C62828` – `#DCEBFA`):**
   - Sidebar cố định bên trái (thu gọn icon-only + tooltip, chuyển menu trượt trên mobile), nội dung bên phải không bị che khuất.
   - Đồng bộ toàn bộ 12 trang chức năng: Dashboard (kèm thẻ *Tình hình học tập*), Quản lý Sinh viên (phân trang), Khoa–Ngành/Lớp học, Học phần, Chương trình đào tạo, Học kỳ & Lớp học phần, Đăng ký học phần, Quản lý điểm, Kết quả học tập & GPA (10/4), Cảnh báo học vụ, Tài khoản & Phân quyền, Cài đặt.
3. **Báo cáo & Slide Thuyết trình Đồng bộ:**
   - [BAO_CAO_DO_AN.pptx](BAO_CAO_DO_AN.pptx) (20 slide 16:9 đồng bộ màu sắc, sơ đồ ERD/Use Case/Kiến trúc, biểu đồ thật).
   - [SLIDE_THUYET_TRINH.pdf](SLIDE_THUYET_TRINH.pdf) & [BAO_CAO_DO_AN.md](BAO_CAO_DO_AN.md).
4. **Kiểm tra Toàn vẹn Dữ liệu Nghiêm ngặt (SQL Server + FastAPI Pydantic):**
   - **Khóa chính (Primary Key):** Tự tăng (`IDENTITY(1,1)`), trả về `404 Not Found` khi truy vấn/sửa/xóa ID không tồn tại.
   - **Khóa ngoại (Foreign Key):** Kiểm tra sự tồn tại của `class_id`, `student_id`, `subject_id` khi thêm/sửa (`400 Bad Request`), và chặn xóa Lớp học/Sinh viên/Môn học đang có dữ liệu phụ thuộc (`400 Bad Request`).
   - **Dữ liệu trùng lặp (Unique Constraints):** Chống trùng `class_code`, `student_code`, `email`, `subject_code`, và bộ ba `(student_id, subject_id, semester)` (`409 Conflict`).
   - **Tính hợp lệ của điểm số & tín chỉ (Pydantic Validation):** Điểm quá trình và điểm thi bắt buộc trong khoảng `0.0 – 10.0`, số tín chỉ trong khoảng `1 – 15` (`422 Unprocessable Entity`).

---

## 📂 Cấu trúc Thư mục Dự án

```text
student-grade-management/
├── main.py                              # Backend FastAPI, SQLAlchemy Models, Pydantic Schemas, RESTful APIs & StaticFiles
├── static/
│   └── index.html                       # Giao diện người dùng (HTML5 + CSS3 + Vanilla JS Fetch API)
├── 01_create_database.sql               # DDL khởi tạo Database StudentGradeManagementDB trên SQL Server
├── 02_create_tables.sql                 # DDL tạo 4 bảng (3NF) + PK, FK, UNIQUE, CHECK, DEFAULT constraints
├── 03_insert_sample_data.sql            # DML chèn dữ liệu mẫu có tính liên kết (Lớp, Môn, Sinh viên, Điểm)
├── 04_stored_procedures.sql             # 5 Stored Procedures xử lý nghiệp vụ & thống kê
├── 05_functions.sql                     # 4 User-Defined Functions (Scalar & Inline Table-Valued UDF)
├── 06_triggers.sql                      # 4 DML Triggers đa dòng (Multi-row inserted/deleted) kiểm soát toàn vẹn
├── 07_transactions.sql                  # 3 Stored Procedures Giao dịch (BEGIN TRAN, TRY...CATCH, COMMIT/ROLLBACK)
├── 08_test_database.sql                 # Bộ kiểm thử tự động 20 kịch bản T-SQL trên SSMS 22
├── DATABASE_DESIGN_AND_SSMS22_GUIDE.md  # Tài liệu ERD, Lược đồ quan hệ, Chuẩn hóa 3NF & Hướng dẫn SSMS 22
├── test_api.py                          # Bộ kiểm thử tích hợp tự động 31 kịch bản FastAPI + SQL Server
├── requirements.txt                     # Danh sách các thư viện Python cần thiết
├── .env.example                         # File mẫu hướng dẫn cấu hình kết nối SQL Server
├── .gitignore                           # Loại trừ file nhạy cảm (.env, __pycache__, .venv)
└── README.md                            # Tài liệu hướng dẫn cài đặt và chạy dự án
```

---

## 🚀 Hướng dẫn Clone, Cài đặt và Chạy Dự án

### Bước 1: Clone dự án từ GitHub
```bash
git clone https://github.com/dlhchu98-sketch/student-grade-management.git
cd student-grade-management
```

### Bước 2: Cài đặt thư viện Python
```bash
pip install -r requirements.txt
```

### Bước 3: Cấu hình kết nối SQL Server (Tùy chọn)
Mặc định, ứng dụng tự động kết nối tới `.\SQLEXPRESS` bằng **Windows Authentication** và tự động khởi tạo Database `StudentGradeManagementDB` cùng dữ liệu mẫu nếu chưa tồn tại.

Nếu bạn dùng tên Server khác hoặc tài khoản `sa`, hãy sao chép `.env.example` thành `.env`:
```bash
cp .env.example .env
```
Sau đó chỉnh sửa các thông số trong `.env`:
```env
DB_SERVER=.\SQLEXPRESS
DB_NAME=StudentGradeManagementDB
DB_TRUSTED_CONNECTION=yes
```

### Bước 4: Khởi chạy Backend & Frontend
```bash
uvicorn main:app --reload
```
- **Giao diện Web (Frontend):** Truy cập [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Tài liệu API (Swagger UI):** Truy cập [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Bước 5: Chạy bộ kiểm thử tự động
```bash
python test_api.py
```
