import os

from database.db import insert_member
from services.face_service import register_member_face


IMAGE_PATH = os.path.join("member_images", "004.jpg")


def main():
    print("========== 新會員完整流程測試 ==========")

    if not os.path.exists(IMAGE_PATH):
        print(f"測試失敗：找不到照片 {IMAGE_PATH}")
        return

    try:
        member_id = insert_member(
            name="測試新會員",
            phone="0900000004",
            vip=False,
            member_level="normal",
            line_user_id="H223456789",
            face_image=IMAGE_PATH.replace("\\", "/"),
            registration_source="backend"
        )

    except Exception as e:
        print(f"新增會員失敗：{e}")
        return

    print(f"新增會員成功，member_id：{member_id}")

    face_result = register_member_face(
        member_id=member_id,
        image_path=IMAGE_PATH
    )

    print("人臉建檔結果：")
    print(face_result)

    if not face_result.get("success"):
        print(
            "會員已新增，但人臉建檔失敗；"
            "請先檢查資料，不要直接再次執行。"
        )
        return

    print("========== 完整流程測試成功 ==========")
    print(f"member_id：{member_id}")
    print(f"face_id：{face_result.get('face_id')}")
    print(f"encoding 長度：{face_result.get('encoding_length')}")
    print(f"重新載入會員數：{face_result.get('loaded_member_count')}")


if __name__ == "__main__":
    main()