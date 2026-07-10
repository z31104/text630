"""
產生 LINE Rich Menu 用的圖片（單一整寬按鈕：會員註冊）。
輸出：linebot_service/richmenu/register_menu.png（2500x843，符合 LINE 官方尺寸建議）
之後直接把這張圖上傳到 LINE Official Account Manager 的圖文選單編輯器即可，不需要透過 Flask。
"""

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 2500, 843

TOP_COLOR = (37, 99, 235)      # #2563eb，跟網站按鈕同色
BOTTOM_COLOR = (29, 78, 216)   # #1d4ed8，深一階做漸層
WHITE = (255, 255, 255)
LIGHT_BLUE = (191, 219, 254)   # #bfdbfe

FONT_BOLD = "C:/Windows/Fonts/msjhbd.ttc"
FONT_REGULAR = "C:/Windows/Fonts/msjh.ttc"


def draw_gradient(draw):
    for y in range(HEIGHT):
        t = y / HEIGHT
        r = int(TOP_COLOR[0] + (BOTTOM_COLOR[0] - TOP_COLOR[0]) * t)
        g = int(TOP_COLOR[1] + (BOTTOM_COLOR[1] - TOP_COLOR[1]) * t)
        b = int(TOP_COLOR[2] + (BOTTOM_COLOR[2] - TOP_COLOR[2]) * t)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))


def draw_soft_circle(img, cx, cy, radius, color, alpha):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(color[0], color[1], color[2], alpha),
    )
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def draw_gift_icon(draw, x, y, size):
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
        fill=(37, 99, 235)
    )

    bow_r = size * 0.11
    draw.ellipse([x - bow_r * 1.6, box_top - lid_h - bow_r * 1.1,
                  x - bow_r * 0.2, box_top - lid_h + bow_r * 0.5], fill=WHITE)
    draw.ellipse([x + bow_r * 0.2, box_top - lid_h - bow_r * 1.1,
                  x + bow_r * 1.6, box_top - lid_h + bow_r * 0.5], fill=WHITE)


def main():
    base = Image.new("RGB", (WIDTH, HEIGHT), TOP_COLOR)
    draw = ImageDraw.Draw(base)
    draw_gradient(draw)

    img = base.convert("RGBA")
    img = draw_soft_circle(img, WIDTH - 260, 120, 380, WHITE, 22)
    img = draw_soft_circle(img, 200, HEIGHT - 80, 260, WHITE, 18)
    img = draw_soft_circle(img, WIDTH - 620, HEIGHT - 40, 180, WHITE, 15)

    draw = ImageDraw.Draw(img)

    draw_gift_icon(draw, 430, HEIGHT / 2 - 230, 460)

    title_font = ImageFont.truetype(FONT_BOLD, 150)
    subtitle_font = ImageFont.truetype(FONT_REGULAR, 62)
    tag_font = ImageFont.truetype(FONT_BOLD, 44)

    text_x = 760

    draw.text((text_x, 300), "加入會員", font=title_font, fill=WHITE)
    draw.text((text_x, 480), "立即註冊．領取入會禮", font=subtitle_font, fill=LIGHT_BLUE)

    tag_text = "點我註冊 >"
    tag_padding_x, tag_padding_y = 36, 18
    bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
    tag_w = bbox[2] - bbox[0]
    tag_h = bbox[3] - bbox[1]
    tag_x, tag_y = text_x, 600
    draw.rounded_rectangle(
        [tag_x, tag_y, tag_x + tag_w + tag_padding_x * 2, tag_y + tag_h + tag_padding_y * 2],
        radius=999, fill=WHITE
    )
    draw.text((tag_x + tag_padding_x, tag_y + tag_padding_y - bbox[1]), tag_text, font=tag_font, fill=TOP_COLOR)

    img.convert("RGB").save("linebot_service/richmenu/register_menu.png", "PNG")
    print("已輸出 linebot_service/richmenu/register_menu.png")


if __name__ == "__main__":
    main()
