from flask import Blueprint, request, redirect
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
            <th>操作</th>
        </tr>
    """

    for m in members:
        member_id = m["member_id"]

        html += f"""
        <tr>
            <td>{m["member_id"]}</td>
            <td>{m["name"]}</td>
            <td>{"是" if m["vip"] else "否"}</td>
            <td>{m["line_id"]}</td>
            <td>{m["image"]}</td>
            <td>
                <a href="/member/edit/{member_id}">修改</a>
                <a href="/member/delete/{member_id}">刪除</a>
            </td>   
        </tr>
            
        """

    html += """
    </table>
    """

    return html


@member_bp.route("/member/add", methods=["GET", "POST"])
def add_member_page():
    if request.method == "POST":
        new_member = {
            "member_id": len(members) + 1,
            "name": request.form.get("name"),
            "vip": request.form.get("vip") == "1",
            "line_id": request.form.get("line_id"),
            "image": "none"
        }

        members.append(new_member)

        return redirect("/member")

    return """
    <h1>新增會員</h1>

    <form method="POST">
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


@member_bp.route("/member/delete/<int:member_id>")
def delete_member(member_id):
    for m in members:
        if m["member_id"] == member_id:
            members.remove(m)
            break

    return redirect("/member")


@member_bp.route("/member/edit/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):
    target_member = None

    for m in members:
        if m["member_id"] == member_id:
            target_member = m
            break

    if target_member is None:
        return "找不到會員"

    if request.method == "POST":
        target_member["name"] = request.form.get("name")
        target_member["vip"] = request.form.get("vip") == "1"
        target_member["line_id"] = request.form.get("line_id")

        return redirect("/member")

    vip_selected = "selected" if target_member["vip"] else ""
    normal_selected = "" if target_member["vip"] else "selected"

    return f"""
    <h1>修改會員</h1>

    <form method="POST">
        <p>會員編號：{target_member['member_id']}</p>
        <p>姓名：<input type="text" name="name" value="{target_member['name']}"></p>
        <p>LINE ID：<input type="text" name="line_id" value="{target_member['line_id']}"></p>
        <p>是否 VIP：
            <select name="vip">
                <option value="0" {normal_selected}>一般會員</option>
                <option value="1" {vip_selected}>VIP會員</option>
            </select>
        </p>
        <button type="submit">儲存修改</button>
    </form>

    <p><a href="/member">回會員列表</a></p>
    """