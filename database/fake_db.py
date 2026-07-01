# 假會員資料

members = [
    {
        "member_id": 1,
        "name": "王小明",
        "vip": True,
        "line_id": "U123456789",
        "image": "001.jpg"
    },
    {
        "member_id": 2,
        "name": "李小華",
        "vip": False,
        "line_id": "U987654321",
        "image": "002.jpg"
    },
    {
        "member_id": 3,
        "name": "陳大文",
        "vip": True,
        "line_id": "U111222333",
        "image": "003.jpg"
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


def get_member_by_image(image):
    for member in members:
        if member["image"] == image:
            return member
    return None


if __name__ == "__main__":
    print(get_member_by_id(1))
    print(get_member_by_name("李小華"))
    print(get_member_by_image("003.jpg"))