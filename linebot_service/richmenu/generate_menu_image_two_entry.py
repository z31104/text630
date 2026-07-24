"""
產生 LINE Rich Menu 用的圖片（左右兩個入口：加入會員／我的會員）。
輸出：linebot_service/richmenu/two_entry_menu.png（2500x843，符合 LINE 官方尺寸建議）

左半邊（x=0, y=0, width=1250, height=843）：加入會員 -> /register
右半邊（x=1250, y=0, width=1250, height=843）：我的會員 -> LIFF -> /coupons

這張圖只負責畫面本身；LINE Rich Menu 的兩個「可點擊區域」與各自的
URI Action，要在 LINE Official Account Manager 的圖文選單編輯器裡手動
框出這兩個區域並填入對應網址（跟這個專案原本 register_menu.png 的
上傳方式一樣，不透過 Messaging API 建立）。
"""

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 2500, 843
HALF_WIDTH = WIDTH // 2

WHITE = (255, 255, 255)

LEFT_TOP_COLOR = (37, 99, 235)      # #2563eb
LEFT_BOTTOM_COLOR = (29, 78, 216)   # #1d4ed8
LEFT_LIGHT = (191, 219, 254)        # #bfdbfe

RIGHT_TOP_COLOR = (217, 119, 6)     # #d97706
RIGHT_BOTTOM_COLOR = (180, 83, 9)   # #b45309
RIGHT_LIGHT = (254, 215, 170)       # #fed7aa

FONT_BOLD = "C:/Windows/Fonts/msjhbd.ttc"
FONT_REGULAR = "C:/Windows/Fonts/msjh.ttc"


def draw_gradient(draw, width, height, top_color, bottom_color):
    for y in range(height):
        t = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def add_soft_circle(img, cx, cy, radius, color, alpha):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(color[0], color[1], color[2], alpha),
    )
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def draw_gift_icon(draw, x, y, size, ribbon_color):
    box_top = y + size * 0.38
    box_h = size * 0.5
    box_w = size * 0.82
    box_x = x - box_w / 2

    draw.rounded_rectangle(
        [box_x, box_top, box_x + box_w, box_top + box_h],
        radius=14, fill=WHITE
    )

    lid_h = size * 0.14
    draw.rounded_rectangle(
        [box_x - 10, box_top - lid_h, box_x + box_w + 10, box_top + 10],
        radius=10, fill=WHITE
    )

    ribbon_w = size * 0.12
    draw.rectangle(
        [x - ribbon_w / 2, box_top - lid_h, x + ribbon_w / 2, box_top + box_h],
        fill=ribbon_color
    )

    bow_r = size * 0.11
    draw.ellipse([x - bow_r * 1.6, box_top - lid_h - bow_r * 1.1,
                  x - bow_r * 0.2, box_top - lid_h + bow_r * 0.5], fill=WHITE)
    draw.ellipse([x + bow_r * 0.2, box_top - lid_h - bow_r * 1.1,
                  x + bow_r * 1.6, box_top - lid_h + bow_r * 0.5], fill=WHITE)


def draw_coupon_icon(draw, x, y, size, accent_color):
    card_w = size * 0.92
    card_h = size * 0.6
    card_x = x - card_w / 2
    card_y = y + size * 0.2

    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=18, fill=WHITE
    )

    # 票根分隔線的位置（靠右側約 30%）
    stub_x = card_x + card_w * 0.7

    # 上下各挖一個小圓，做出「撕票口」的視覺效果
    notch_r = size * 0.06
    draw.ellipse(
        [stub_x - notch_r, card_y - notch_r, stub_x + notch_r, card_y + notch_r],
        fill=accent_color
    )
    draw.ellipse(
        [stub_x - notch_r, card_y + card_h - notch_r, stub_x + notch_r, card_y + card_h + notch_r],
        fill=accent_color
    )

    # 中間的虛線
    dash_top = card_y + notch_r * 1.6
    dash_bottom = card_y + card_h - notch_r * 1.6
    dash_count = 6
    dash_len = (dash_bottom - dash_top) / (dash_count * 2 - 1)
    for i in range(dash_count):
        seg_top = dash_top + i * dash_len * 2
        draw.line(
            [(stub_x, seg_top), (stub_x, seg_top + dash_len)],
            fill=accent_color, width=4
        )

    # 票根區塊裡畫一個小星星，代表優惠券
    star_cx = card_x + card_w * 0.85
    star_cy = card_y + card_h / 2
    star_r = size * 0.07
    star_points = []
    import math
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = star_r if i % 2 == 0 else star_r * 0.45
        star_points.append((star_cx + r * math.cos(angle), star_cy - r * math.sin(angle)))
    draw.polygon(star_points, fill=accent_color)


def draw_tag(draw, x, y, text, font, base_color):
    padding_x, padding_y = 36, 18
    bbox = draw.textbbox((0, 0), text, font=font)
    tag_w = bbox[2] - bbox[0]
    tag_h = bbox[3] - bbox[1]
    draw.rounded_rectangle(
        [x, y, x + tag_w + padding_x * 2, y + tag_h + padding_y * 2],
        radius=999, fill=WHITE
    )
    draw.text((x + padding_x, y + padding_y - bbox[1]), text, font=font, fill=base_color)


def render_half(width, height, top_color, bottom_color, light_color,
                 icon_fn, title, subtitle, tag_text):
    base = Image.new("RGB", (width, height), top_color)
    draw = ImageDraw.Draw(base)
    draw_gradient(draw, width, height, top_color, bottom_color)

    img = base.convert("RGBA")
    img = add_soft_circle(img, width - 160, 110, 260, WHITE, 22)
    img = add_soft_circle(img, 130, height - 70, 190, WHITE, 16)

    draw = ImageDraw.Draw(img)

    icon_fn(draw, 250, height / 2 - 230, 380)

    title_font = ImageFont.truetype(FONT_BOLD, 118)
    subtitle_font = ImageFont.truetype(FONT_REGULAR, 50)
    tag_font = ImageFont.truetype(FONT_BOLD, 38)

    text_x = 500

    draw.text((text_x, 300), title, font=title_font, fill=WHITE)
    draw.text((text_x, 460), subtitle, font=subtitle_font, fill=light_color)

    draw_tag(draw, text_x, 570, tag_text, tag_font, top_color)

    return img.convert("RGB")


def main():
    left = render_half(
        HALF_WIDTH, HEIGHT, LEFT_TOP_COLOR, LEFT_BOTTOM_COLOR, LEFT_LIGHT,
        icon_fn=lambda draw, x, y, size: draw_gift_icon(draw, x, y, size, LEFT_TOP_COLOR),
        title="加入會員",
        subtitle="立即註冊．領取入會禮",
        tag_text="點我註冊 >",
    )

    right = render_half(
        HALF_WIDTH, HEIGHT, RIGHT_TOP_COLOR, RIGHT_BOTTOM_COLOR, RIGHT_LIGHT,
        icon_fn=lambda draw, x, y, size: draw_coupon_icon(draw, x, y, size, RIGHT_TOP_COLOR),
        title="我的會員",
        subtitle="查看優惠券",
        tag_text="點我查看 >",
    )

    canvas = Image.new("RGB", (WIDTH, HEIGHT))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (HALF_WIDTH, 0))

    # 中間畫一條細分隔線，讓兩個入口在視覺上更清楚是分開的按鈕
    divider = ImageDraw.Draw(canvas)
    divider.line([(HALF_WIDTH, 0), (HALF_WIDTH, HEIGHT)], fill=WHITE, width=4)

    canvas.save("linebot_service/richmenu/two_entry_menu.png", "PNG")
    print("已輸出 linebot_service/richmenu/two_entry_menu.png")


if __name__ == "__main__":
    main()
