# 假會員資料，測試用
members = [
    {
        "member_id": 1,
        "name": "王小明",
        "phone": "0912345678",
        "vip": True,
        "member_level": "vip",
        "total_visit_count": 12,
        "line_user_id": "U123456789",
        "total_amount": 5800,
        "favorite_product": "拿鐵",
        "face_image": "001.jpg",
        "birthday": "1996-08-21",
        "registration_source": "import",
        "created_at": "2026-07-09 10:00:00",
        "updated_at": "2026-07-09 10:00:00"
    },
    {
        "member_id": 2,
        "name": "李小華",
        "phone": "0922333444",
        "vip": False,
        "member_level": "normal",
        "total_visit_count": 3,
        "line_user_id": "U987654321",
        "total_amount": 900,
        "birthday": "1998-05-10",
        "registration_source": "import",
        "favorite_product": "美式咖啡",
        "face_image": "002.jpg",
        "created_at": "2026-07-09 10:00:00",
        "updated_at": "2026-07-09 10:00:00"
    },
    {
        "member_id": 3,
        "name": "陳大文",
        "phone": "0933555666",
        "vip": True,
        "member_level": "vip",
        "total_visit_count": 20,
        "line_user_id": "U111222333",
        "total_amount": 12000,
        "favorite_product": "焦糖瑪奇朵",
        "face_image": "003.jpg",
        "birthday": "1992-12-25",
        "registration_source": "import",
        "created_at": "2026-07-09 10:00:00",
        "updated_at": "2026-07-09 10:00:00"
    }
]


def get_member_by_id(member_id):
    for member in members:
        if member["member_id"] == member_id:
            return member
    return None


def get_member_by_name(name):
    for member in members:
        if member["name"] == name:
            return member
    return None


def get_member_by_face_image(face_image):
    for member in members:
        if member["face_image"] == face_image:
            return member
    return None


def get_member_by_image(filename):
    """
    給 services/face_service.py 使用。
    根據 member_images 裡的圖片檔名取得會員假資料。
    """

    return get_member_by_face_image(filename)

if __name__ == "__main__":
    print(get_member_by_id(1))
    print(get_member_by_name("李小華"))
    print(get_member_by_face_image("003.jpg"))