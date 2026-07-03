from flask import Blueprint
from database.fake_db import members

member_bp = Blueprint("member", __name__)


@member_bp.route("/member")
def member():
    html = """
    <h1>會員資料頁</h1>
    <p><a href="/member/add">新增會員</a></p>

    <table border="1" cellpadding="8">
        <tr>
            <th>會員編號</th>
            <th>姓名</th>
            <th>VIP</th>
            <th>LINE ID</th>
            <th>圖片</th>
        </tr>
    """

    for m in members:
        html += f"""
        <tr>
            <td>{m["member_id"]}</td>
            <td>{m["name"]}</td>
            <td>{"是" if m["vip"] else "否"}</td>
            <td>{m["line_id"]}</td>
            <td>{m["image"]}</td>
        </tr>
        """

    html += """
    </table>
    """

    return html


@member_bp.route("/member/add")
def add_member_page():
    return """
    <h1>新增會員</h1>

    <form>
        <p>姓名：<input type="text" name="name"></p>
        <p>電話：<input type="text" name="phone"></p>
        <p>Email：<input type="text" name="email"></p>
        <p>LINE ID：<input type="text" name="line_id"></p>
        <p>是否 VIP：
            <select name="vip">
                <option value="0">一般會員</option>
                <option value="1">VIP會員</option>
            </select>
        </p>
        <button type="submit">新增會員</button>
    </form>

    <p><a href="/member">回會員列表</a></p>
    """