import os
import cv2
import time
import threading
from datetime import datetime
from flask import Blueprint, Response
from services.visit_service import build_subject_key

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from services.face_service import (
    detect_face,
    recognize_face,
    draw_face_boxes,
    log_recognition_result,
    update_recognition_last_seen,
    close_recognition_visit,
    send_line_notify
)

camera_bp = Blueprint("camera", __name__)

# =============================
# 攝影機設定
# =============================

def get_int_env(name, default):
    """安全讀取整數環境變數，讀不到就使用預設值。"""
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# 0: 內建鏡頭，1: 外接 Logi C270 HD WebCam
CAMERA_INDEX = get_int_env("CAMERA_INDEX", 1)
CAMERA_WIDTH = get_int_env("CAMERA_WIDTH", 640)
CAMERA_HEIGHT = get_int_env("CAMERA_HEIGHT", 480)
CAMERA_FPS = get_int_env("CAMERA_FPS", 30)

# 每 3 秒才重新做人臉辨識
last_recognition_time = 0

# 上一次辨識結果，給畫框顯示用
last_result = {
    "subject_type": "none",
    "member_id": None,
    "visitor_id": None,
    "visitor_code": None,
    "member_id": None,
    "name": "No Face",
    "phone": None,
    "vip": False,
    "member_level": "guest",
    "visit_count": 0,
    "line_user_id": None,
    "registration_source": None,
    "total_amount": 0,
    "favorite_product": None,
    "face_image": None,
    "confidence": 0,
    "recognition_status": "no_face",
    "member_level_text": "No Face"
}


# 記錄每個會員目前是否在店內，用來計算 visit_time / leave_time / stay_minutes
active_visits = {}
active_visits_lock = threading.Lock()

# 訪客上一次產生 recognition log 的時間
last_guest_log_time = 0

# 設定參數
RECOGNITION_INTERVAL = 3       # 每 3 秒做一次人臉比對
LAST_SEEN_UPDATE_INTERVAL = 15 # 每 15 秒更新一次資料庫
GUEST_LOG_INTERVAL = 60        # Guest 每 60 秒最多記錄一次，避免太頻繁
MIN_CONFIDENCE = 0.6           # 信心值低於 0.6 的會員辨識結果先不記錄
LEAVE_TIMEOUT = 60             # 超過 60 秒沒再看到同一會員，就先視為離店
CAMERA_ID = "camera_1"         # 對應 recognition_logs.camera_id


def now_text():
    """回傳目前時間文字，格式統一給 recognition_logs 使用。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def open_camera(camera_index=CAMERA_INDEX):
    """
    開啟攝影機。

    Windows 建議使用 cv2.CAP_DSHOW，外接 USB 攝影機會比較快開啟，
    也比較不容易出現 MSMF can\'t grab frame 的問題。

    0: 內建鏡頭
    1: 外接 Logi C270 HD WebCam
    """

    print(f"嘗試開啟攝影機，camera_index={camera_index}")

    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

    if not cap.isOpened():
        print(f"無法開啟攝影機，camera_index={camera_index}")
        cap.release()
        return None

    # 先讀一張測試影像，避免網頁已開啟但畫面是黑的或卡住
    success, _ = cap.read()
    if not success:
        print(f"攝影機已開啟，但讀不到畫面，camera_index={camera_index}")
        cap.release()
        return None

    print(f"已開啟攝影機，camera_index={camera_index}")
    return cap


def update_member_visit(result, current_time):
    member_id = result.get("member_id")
    subject_type = result.get("subject_type")
    visitor_id = result.get("visitor_id")

    subject_key = build_subject_key(
        subject_type=subject_type,
        member_id=member_id,
        visitor_id=visitor_id,
    )

    if subject_key is None:
        return

    current_time_text = now_text()

    with active_visits_lock:
        # 第一次看到這位會員
        if subject_key not in active_visits:
            visit_time = current_time_text

            log_id = log_recognition_result(
                result,
                visit_time=visit_time,
                leave_time=None,
                stay_minutes=0,
                visit_status="arrived",
                camera_id=CAMERA_ID,
            )

            if log_id is None:
                print(
                    f"會員到店紀錄新增失敗，"
                    f"member_id={member_id}"
                )
                return

            active_visits[subject_key] = {
                "log_id": log_id,
                "result": result,
                "visit_timestamp": current_time,
                "visit_time": visit_time,
                "last_seen_timestamp": current_time,
                "last_seen_at": current_time_text,
                "last_db_update_timestamp": current_time,
            }

            print("========== Member Visit Started ==========")
            print(f"member_id: {member_id}")
            print(f"log_id: {log_id}")
            print(f"visit_time: {visit_time}")
            print("==========================================")

            # 只有第一次建立到店紀錄時，執行 VIP 通知
            notification_status = send_line_notify(
               result,
               log_id=log_id
            )

            if notification_status is not None:
                print("========== VIP Notify Result ==========")
                print(f"log_id: {log_id}")
                print(f"notification_status: {notification_status}")
                print("=======================================")

        # 持續看到同一位會員
        else:
            visit_data = active_visits[subject_key]

            visit_data["result"] = result
            visit_data["last_seen_timestamp"] = current_time
            visit_data["last_seen_at"] = current_time_text

            last_db_update_timestamp = visit_data.get(
                "last_db_update_timestamp",
                0,
            )

            if (
                current_time - last_db_update_timestamp
                >= LAST_SEEN_UPDATE_INTERVAL
            ):
                log_id = visit_data.get("log_id")

                update_recognition_last_seen(
                    log_id=log_id,
                    last_seen_at=current_time_text,
                )

                visit_data["last_db_update_timestamp"] = current_time


def close_timeout_visits(current_time):
    """
    檢查超過 LEAVE_TIMEOUT 未再次辨識到的對象。

    離店時不新增另一筆紀錄，
    而是將第一次到店建立的同一筆 recognition_logs
    更新為 visit_status="left"。
    """

    leaving_subject_keys = []

    with active_visits_lock:
        for subject_key, visit_data in list(active_visits.items()):
            result = visit_data.get("result", {})
            member_id = result.get("member_id")

            last_seen_timestamp = visit_data.get("last_seen_timestamp")

            if last_seen_timestamp is None:
                continue

            elapsed_seconds = current_time - last_seen_timestamp

            if elapsed_seconds < LEAVE_TIMEOUT:
                continue

            log_id = visit_data.get("log_id")

            # 最後一次實際看到會員的時間
            last_seen_at = visit_data.get("last_seen_at")

            if not last_seen_at:
                last_seen_at = now_text()

            # 系統滿足離店逾時條件後，正式判定離店的時間
            leave_time = now_text()

            visit_timestamp = visit_data.get(
                "visit_timestamp",
                current_time,
            )

            stay_seconds = int(
                round(
                    current_time - visit_timestamp
                )
            )

            stay_seconds = max(stay_seconds, 0)
            stay_minutes = round(stay_seconds / 60, 2)

            closed = close_recognition_visit(
                log_id=log_id,
                last_seen_at=last_seen_at,
                leave_time=leave_time,
                stay_seconds=stay_seconds,
                stay_minutes=stay_minutes,
            )

            if closed:
                print("========== Member Visit Ended ==========")
                print(f"member_id: {member_id}")
                print(f"log_id: {log_id}")
                print(f"leave_time: {leave_time}")
                print(f"stay_seconds: {stay_seconds}")
                print(f"stay_minutes: {stay_minutes}")
                print("========================================")

                leaving_subject_keys.append(subject_key)

        # 成功更新資料庫後，才從記憶體移除
        for subject_key in leaving_subject_keys:
            active_visits.pop(subject_key, None)


def generate_frames():
    global last_recognition_time
    global last_result
    global last_guest_log_time

    cap = open_camera(CAMERA_INDEX)

    if cap is None:
        print("攝影機串流停止：無法取得攝影機")
        return

    try:
        while True:
            time.sleep(0.01)

            success, frame = cap.read()

            if not success or frame is None:
                print("讀取攝影機畫面失敗，結束本次串流")
                break

            faces = detect_face(frame)
            current_time = time.time()
            has_face = len(faces) > 0

            # 畫面沒有偵測到人臉
            # 清除上一筆會員或 guest 的顯示資料
            if not has_face:
                last_result = {
                    "subject_type": "none",
                    "member_id": None,
                    "visitor_id": None,
                    "visitor_code": None,
                    "member_id": None,
                    "name": "No Face",
                    "phone": None,
                    "vip": False,
                    "member_level": "guest",
                    "visit_count": 0,
                    "line_user_id": None,
                    "registration_source": None,
                    "total_amount": 0,
                    "favorite_product": None,
                    "face_image": None,
                    "confidence": 0,
                    "recognition_status": "no_face",
                    "member_level_text": "No Face"
                }

            # 畫面有偵測到人臉，而且超過辨識間隔
            # 才執行會員人臉比對
            elif (
                current_time - last_recognition_time
                >= RECOGNITION_INTERVAL
            ):
                last_result = recognize_face(frame, faces)
                last_recognition_time = current_time

            current_member_id = last_result.get("member_id")
            current_subject_type = last_result.get("subject_type")
            current_visitor_id = last_result.get("visitor_id")
            current_subject_key = build_subject_key(
                subject_type=current_subject_type,
                member_id=current_member_id,
                visitor_id=current_visitor_id,
            )

            current_confidence = last_result.get("confidence", 0)

            current_recognition_status = last_result.get(
                "recognition_status",
                "no_face"
            )

            # ----------------------------------------
            # 正式會員紀錄
            # ----------------------------------------
            # 條件：
            # 1. 畫面有偵測到人臉
            # 2. 有正式 member_id
            # 3. 信心值達到最低門檻
            # 4. 辨識狀態為 recognized
            if (
                has_face
                and current_member_id is not None
                and current_confidence >= MIN_CONFIDENCE
                and current_recognition_status == "recognized"
            ):
                # 第一次看到會員時建立 visit_start
                # 持續看到會員時更新最後出現時間
                update_member_visit(
                    last_result,
                    current_time
                )

        

            # ----------------------------------------
            # Guest 紀錄
            # ----------------------------------------
            # 必須是：
            # 1. 畫面確實有人臉
            # 2. 沒有辨識到正式會員
            # 3. recognize_face 已確認狀態為 guest
            elif (
                has_face
                and current_member_id is None
                and current_recognition_status == "guest"
            ):
                # 避免同一位 Guest 每一幀都重複寫入
                if (
                    current_time - last_guest_log_time
                    >= GUEST_LOG_INTERVAL
                ):
                    log_recognition_result(
                        last_result,
                        visit_time=now_text(),
                        leave_time=None,
                        stay_minutes=None,
                        visit_status="arrived",
                        camera_id=CAMERA_ID
                    )

                    last_guest_log_time = current_time

            # 檢查已經超過離店等待時間的對象
            # 並將原本紀錄更新為 visit_status="left"
            close_timeout_visits(current_time)

            # 只有畫面有人臉時才畫框與辨識文字
            if has_face:
                frame = draw_face_boxes(
                    frame,
                    faces,
                    last_result
                )

            # 將 OpenCV 畫面轉成 JPEG
            ret, buffer = cv2.imencode(
                ".jpg",
                frame
            )

            if not ret:
                continue

            frame_bytes = buffer.tobytes()

            # 傳送給 Flask 網頁串流
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame_bytes
                + b"\r\n"
            )

    except GeneratorExit:
        print("瀏覽器已關閉攝影機串流")

    except Exception as e:
        print(f"攝影機串流發生錯誤：{e}")

    finally:
        if cap is not None:
            cap.release()
            print("攝影機已釋放")


@camera_bp.route("/camera")
def camera():
    return """
    <h1>智慧會員辨識系統 - 攝影機畫面</h1>
    <p>即時攝影機串流</p>
    <p>本週測試重點：一般會員 / VIP / Guest 辨識、到店時間、離店時間、停留時間</p>
    <img src="/camera/video_feed" width="640">
    """


@camera_bp.route("/camera/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )
