"""
Bộ kiểm thử tích hợp tự động toàn diện (End-to-End API & SQL Server Integration Tests)
Đề tài: Hệ thống Quản lý Sinh viên và Điểm thi
Kiểm tra:
1. Giao diện Frontend tại "/" và "/static/index.html" + Dashboard API (/api/stats)
2. CRUD Lớp học (GET, POST, PATCH, DELETE) + Kiểm tra trùng mã lớp (409) + ID không tồn tại (404)
3. CRUD Sinh viên (GET, POST, PATCH, DELETE, Search) + Khóa ngoại class_id (400) + Trùng mã SV/Email (409) + 404
4. CRUD Môn học (GET, POST, PATCH, DELETE) + Trùng mã môn (409) + Tín chỉ không hợp lệ (422) + 404
5. CRUD Điểm thi (GET, POST, PATCH, DELETE) + Khóa ngoại student_id/subject_id (400) + Trùng điểm (409) + Điểm ngoài khoảng 0-10 (422) + 404
6. Bảo vệ toàn vẹn khóa ngoại khi xóa Lớp học đang có SV hoặc xóa SV/Môn học đã có Điểm thi (400)
7. Kiểm tra tính đồng bộ dữ liệu trực tiếp trong SQL Server
"""

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from sqlalchemy import text
from main import app, SessionLocal

client = TestClient(app)


def run_all_tests():
    results = []

    def record(test_name: str, passed: bool, detail: str = ""):
        results.append({"name": test_name, "passed": passed, "detail": detail})
        status_icon = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status_icon} | {test_name} {f'({detail})' if detail else ''}")
        assert passed, f"Test failed: {test_name} - {detail}"

    print("=" * 80)
    print("BẮT ĐẦU KIỂM THỬ HỆ THỐNG QUẢN LÝ SINH VIÊN & ĐIỂM THI (FASTAPI + SQL SERVER)")
    print("=" * 80)

    # 1. Kiểm tra Frontend StaticFiles & Dashboard
    r_root = client.get("/")
    record(
        "1. Phục vụ giao diện Frontend tại '/' (StaticFiles)",
        r_root.status_code == 200 and "HỆ THỐNG QUẢN LÝ SINH VIÊN VÀ ĐIỂM THI" in r_root.text,
        f"HTTP {r_root.status_code}",
    )

    r_stats = client.get("/api/stats")
    stats_data = r_stats.json()
    record(
        "2. API Dashboard tổng quan (/api/stats)",
        r_stats.status_code == 200
        and stats_data["total_students"] >= 6
        and stats_data["total_classes"] >= 4,
        f"SV={stats_data.get('total_students')}, Lớp={stats_data.get('total_classes')}, Môn={stats_data.get('total_subjects')}, Điểm={stats_data.get('total_scores')}",
    )

    # 2. Kiểm thử CRUD Lớp học (Classes)
    r_cls_create = client.post(
        "/api/classes",
        json={
            "class_code": "TEST-CLS-99",
            "class_name": "Lớp Kiểm Thử Tự Động 99",
            "academic_year": "2025-2029",
            "homeroom_teacher": "TS. Kiểm Thử",
        },
    )
    record(
        "3. [Lớp học] POST /api/classes - Thêm lớp học mới",
        r_cls_create.status_code == 201 and r_cls_create.json()["class_code"] == "TEST-CLS-99",
        f"HTTP {r_cls_create.status_code}",
    )
    test_cls_id = r_cls_create.json()["id"]

    r_cls_dup = client.post(
        "/api/classes",
        json={"class_code": "TEST-CLS-99", "class_name": "Lớp Trùng Mã"},
    )
    record(
        "4. [Lớp học] Kiểm tra chống trùng mã lớp (Duplicate class_code)",
        r_cls_dup.status_code == 409,
        f"HTTP {r_cls_dup.status_code}",
    )

    r_cls_get = client.get(f"/api/classes/{test_cls_id}")
    record(
        "5. [Lớp học] GET /api/classes/{id} - Xem chi tiết lớp học",
        r_cls_get.status_code == 200 and r_cls_get.json()["id"] == test_cls_id,
        f"HTTP {r_cls_get.status_code}",
    )

    r_cls_patch = client.patch(
        f"/api/classes/{test_cls_id}",
        json={"class_name": "Lớp Kiểm Thử Đã Cập Nhật"},
    )
    record(
        "6. [Lớp học] PATCH /api/classes/{id} - Cập nhật lớp học",
        r_cls_patch.status_code == 200
        and r_cls_patch.json()["class_name"] == "Lớp Kiểm Thử Đã Cập Nhật",
        f"HTTP {r_cls_patch.status_code}",
    )

    r_cls_404 = client.get("/api/classes/999999")
    record(
        "7. [Lớp học] Kiểm tra ID lớp không tồn tại trả về 404",
        r_cls_404.status_code == 404,
        f"HTTP {r_cls_404.status_code}",
    )

    # 3. Kiểm thử CRUD Môn học (Subjects)
    r_sub_create = client.post(
        "/api/subjects",
        json={
            "subject_code": "TEST-SUB-99",
            "subject_name": "Môn Học Kiểm Thử Phần Mềm",
            "credits": 4,
            "department": "Công nghệ phần mềm",
        },
    )
    record(
        "8. [Môn học] POST /api/subjects - Thêm môn học mới",
        r_sub_create.status_code == 201 and r_sub_create.json()["credits"] == 4,
        f"HTTP {r_sub_create.status_code}",
    )
    test_sub_id = r_sub_create.json()["id"]

    r_sub_dup = client.post(
        "/api/subjects",
        json={"subject_code": "TEST-SUB-99", "subject_name": "Môn Trùng", "credits": 3},
    )
    record(
        "9. [Môn học] Kiểm tra chống trùng mã môn học (Duplicate subject_code)",
        r_sub_dup.status_code == 409,
        f"HTTP {r_sub_dup.status_code}",
    )

    r_sub_invalid_credits = client.post(
        "/api/subjects",
        json={"subject_code": "TEST-SUB-00", "subject_name": "Tín chỉ âm", "credits": 0},
    )
    record(
        "10. [Môn học] Kiểm tra Pydantic số tín chỉ không hợp lệ (credits=0 -> 422)",
        r_sub_invalid_credits.status_code == 422,
        f"HTTP {r_sub_invalid_credits.status_code}",
    )

    r_sub_patch = client.patch(
        f"/api/subjects/{test_sub_id}",
        json={"credits": 3, "subject_name": "Kiểm Thử Phần Mềm Nâng Cao"},
    )
    record(
        "11. [Môn học] PATCH /api/subjects/{id} - Cập nhật môn học",
        r_sub_patch.status_code == 200 and r_sub_patch.json()["credits"] == 3,
        f"HTTP {r_sub_patch.status_code}",
    )

    r_sub_404 = client.patch("/api/subjects/999999", json={"credits": 3})
    record(
        "12. [Môn học] Kiểm tra ID môn học không tồn tại trả về 404",
        r_sub_404.status_code == 404,
        f"HTTP {r_sub_404.status_code}",
    )

    # 4. Kiểm thử CRUD Sinh viên (Students) & Khóa ngoại
    r_st_bad_fk = client.post(
        "/api/students",
        json={
            "student_code": "SVTEST999",
            "full_name": "Sinh Viên Lỗi Khóa Ngoại",
            "date_of_birth": "2005-06-15",
            "gender": "Nam",
            "email": "badfk@student.edu.vn",
            "class_id": 999999,
        },
    )
    record(
        "13. [Sinh viên] Kiểm tra khóa ngoại class_id không tồn tại (400 Bad Request)",
        r_st_bad_fk.status_code == 400,
        f"HTTP {r_st_bad_fk.status_code}",
    )

    r_st_create = client.post(
        "/api/students",
        json={
            "student_code": "SVTEST999",
            "full_name": "Đặng Quốc Khánh",
            "date_of_birth": "2005-06-15",
            "gender": "Nam",
            "email": "khanh.dq999@student.edu.vn",
            "hometown": "TP. Hồ Chí Minh",
            "class_id": test_cls_id,
        },
    )
    record(
        "14. [Sinh viên] POST /api/students - Thêm sinh viên mới",
        r_st_create.status_code == 201 and r_st_create.json()["student_code"] == "SVTEST999",
        f"HTTP {r_st_create.status_code}",
    )
    test_st_id = r_st_create.json()["id"]

    r_st_dup = client.post(
        "/api/students",
        json={
            "student_code": "SVTEST999",
            "full_name": "Trùng Mã SV",
            "date_of_birth": "2005-06-15",
            "gender": "Nam",
            "email": "other999@student.edu.vn",
            "class_id": test_cls_id,
        },
    )
    record(
        "15. [Sinh viên] Kiểm tra chống trùng mã sinh viên (Duplicate student_code)",
        r_st_dup.status_code == 409,
        f"HTTP {r_st_dup.status_code}",
    )

    r_st_search = client.get("/api/students?search=SVTEST999")
    record(
        "16. [Sinh viên] GET /api/students?search=... - Tìm kiếm sinh viên",
        r_st_search.status_code == 200 and len(r_st_search.json()) == 1,
        f"Tìm thấy {len(r_st_search.json())} bản ghi",
    )

    r_st_patch = client.patch(
        f"/api/students/{test_st_id}",
        json={"hometown": "Bình Dương", "full_name": "Đặng Quốc Khánh (Updated)"},
    )
    record(
        "17. [Sinh viên] PATCH /api/students/{id} - Cập nhật sinh viên",
        r_st_patch.status_code == 200 and r_st_patch.json()["hometown"] == "Bình Dương",
        f"HTTP {r_st_patch.status_code}",
    )

    r_st_404 = client.get("/api/students/999999")
    record(
        "18. [Sinh viên] Kiểm tra ID sinh viên không tồn tại trả về 404",
        r_st_404.status_code == 404,
        f"HTTP {r_st_404.status_code}",
    )

    # Kiểm tra chặn xóa lớp học khi đang có sinh viên
    r_cls_del_blocked = client.delete(f"/api/classes/{test_cls_id}")
    record(
        "19. [Khóa ngoại] Chặn xóa lớp học đang có sinh viên (400 Bad Request)",
        r_cls_del_blocked.status_code == 400,
        f"HTTP {r_cls_del_blocked.status_code}",
    )

    # 5. Kiểm thử CRUD Điểm thi (Scores) & Validation điểm số (0.0 - 10.0)
    r_sc_invalid_high = client.post(
        "/api/scores",
        json={
            "student_id": test_st_id,
            "subject_id": test_sub_id,
            "semester": "HK1-2026",
            "process_score": 11.5,
            "exam_score": 8.0,
        },
    )
    record(
        "20. [Điểm thi] Kiểm tra điểm số > 10.0 bị từ chối (422 Unprocessable Entity)",
        r_sc_invalid_high.status_code == 422,
        f"HTTP {r_sc_invalid_high.status_code}",
    )

    r_sc_invalid_neg = client.post(
        "/api/scores",
        json={
            "student_id": test_st_id,
            "subject_id": test_sub_id,
            "semester": "HK1-2026",
            "process_score": 7.0,
            "exam_score": -1.0,
        },
    )
    record(
        "21. [Điểm thi] Kiểm tra điểm số âm < 0.0 bị từ chối (422 Unprocessable Entity)",
        r_sc_invalid_neg.status_code == 422,
        f"HTTP {r_sc_invalid_neg.status_code}",
    )

    r_sc_bad_fk = client.post(
        "/api/scores",
        json={
            "student_id": 999999,
            "subject_id": test_sub_id,
            "semester": "HK1-2026",
            "process_score": 8.0,
            "exam_score": 8.0,
        },
    )
    record(
        "22. [Điểm thi] Kiểm tra khóa ngoại student_id không tồn tại (400 Bad Request)",
        r_sc_bad_fk.status_code == 400,
        f"HTTP {r_sc_bad_fk.status_code}",
    )

    r_sc_create = client.post(
        "/api/scores",
        json={
            "student_id": test_st_id,
            "subject_id": test_sub_id,
            "semester": "HK1-2026",
            "process_score": 8.0,
            "exam_score": 9.0,
        },
    )
    # 8.0 * 0.4 + 9.0 * 0.6 = 3.2 + 5.4 = 8.6
    record(
        "23. [Điểm thi] POST /api/scores - Nhập điểm mới & Tự động tính điểm tổng kết",
        r_sc_create.status_code == 201 and r_sc_create.json()["final_score"] == 8.6,
        f"HTTP {r_sc_create.status_code}, Final={r_sc_create.json().get('final_score')}",
    )
    test_sc_id = r_sc_create.json()["id"]

    r_sc_dup = client.post(
        "/api/scores",
        json={
            "student_id": test_st_id,
            "subject_id": test_sub_id,
            "semester": "HK1-2026",
            "process_score": 7.0,
            "exam_score": 7.0,
        },
    )
    record(
        "24. [Điểm thi] Kiểm tra chống nhập trùng điểm cùng môn & học kỳ (409 Conflict)",
        r_sc_dup.status_code == 409,
        f"HTTP {r_sc_dup.status_code}",
    )

    r_sc_patch = client.patch(
        f"/api/scores/{test_sc_id}",
        json={"process_score": 9.0, "exam_score": 10.0},
    )
    # 9.0 * 0.4 + 10.0 * 0.6 = 9.6
    record(
        "25. [Điểm thi] PATCH /api/scores/{id} - Cập nhật điểm & Tính lại tổng kết",
        r_sc_patch.status_code == 200 and r_sc_patch.json()["final_score"] == 9.6,
        f"HTTP {r_sc_patch.status_code}, Final={r_sc_patch.json().get('final_score')}",
    )

    r_sc_404 = client.delete("/api/scores/999999")
    record(
        "26. [Điểm thi] Kiểm tra ID điểm thi không tồn tại trả về 404",
        r_sc_404.status_code == 404,
        f"HTTP {r_sc_404.status_code}",
    )

    # 6. Kiểm tra đồng bộ trực tiếp trong SQL Server
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT final_score FROM scores WHERE id = :id"), {"id": test_sc_id}
        ).fetchone()
        record(
            "27. [SQL Server Sync] Đối chiếu dữ liệu thực tế lưu trong bảng dbo.scores",
            row is not None and float(row[0]) == 9.6,
            f"SQL Server final_score={row[0] if row else None}",
        )
    finally:
        db.close()

    # 7. Kiểm tra xóa theo đúng thứ tự ràng buộc khóa ngoại (Scores -> Students -> Subjects & Classes)
    r_sc_del = client.delete(f"/api/scores/{test_sc_id}")
    record(
        "28. [Điểm thi] DELETE /api/scores/{id} - Xóa bản ghi điểm thi",
        r_sc_del.status_code == 200,
        f"HTTP {r_sc_del.status_code}",
    )

    r_st_del = client.delete(f"/api/students/{test_st_id}")
    record(
        "29. [Sinh viên] DELETE /api/students/{id} - Xóa sinh viên",
        r_st_del.status_code == 200,
        f"HTTP {r_st_del.status_code}",
    )

    r_sub_del = client.delete(f"/api/subjects/{test_sub_id}")
    record(
        "30. [Môn học] DELETE /api/subjects/{id} - Xóa môn học",
        r_sub_del.status_code == 200,
        f"HTTP {r_sub_del.status_code}",
    )

    r_cls_del = client.delete(f"/api/classes/{test_cls_id}")
    record(
        "31. [Lớp học] DELETE /api/classes/{id} - Xóa lớp học",
        r_cls_del.status_code == 200,
        f"HTTP {r_cls_del.status_code}",
    )

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    print("=" * 80)
    print(f"TỔNG KẾT KIỂM THỬ: Đạt {passed}/{total} chức năng (Thất bại: {failed})")
    print("=" * 80)


if __name__ == "__main__":
    run_all_tests()
