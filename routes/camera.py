import os
import cv2
import time
import threading
from datetime import datetime
from flask import Blueprint, Response
from services.visit_service import (
    build_subject_key,
    handle_recognition,
    close_timeout_visits as close_timeout_visits_service,
)
from database.db import get_active_visit

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from services.face_service import (
    detect_face,
    recognize_face,
    register_new_visitor,
    draw_face_boxes,
    log_recognition_result,
    update_recognition_last_seen,
    close_recognition_visit,
    send_line_notify,
    reload_member_faces
)
camera_bp = Blueprint("camera", __name__)

# 同一時間只允許一個攝影機串流持有實體鏡頭。
# 瀏覽器重新整理時，會先釋放舊串流使用的鏡頭，
# 再交給新的 /camera/video_feed 使用。
camera_instance = None
camera_instance_lock = threading.Lock()
camera_stream_lock = threading.Lock()

# =============================
# 攝影機設定
# =============================

def get_int_env(name, default):
    """安全讀取整數環境變數，讀不到就使用預設值。"""
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# 攝影機編號由 Windows / DirectShow 的裝置順序決定
# 請透過 .env 的 CAMERA_INDEX 指定目前要使用的鏡頭
CAMERA_INDEX = get_int_env("CAMERA_INDEX", 0)
CAMERA_WIDTH = get_int_env("CAMERA_WIDTH", 640)
CAMERA_HEIGHT = get_int_env("CAMERA_HEIGHT", 480)
CAMERA_FPS = get_int_env("CAMERA_FPS", 30)

# 每 2 秒才重新做人臉辨識
last_recognition_time = 0

# 上一次辨識結果，給畫框顯示用
last_result = {
    "subject_type": "none",
    "member_id": None,
    "visitor_id": None,
    "visitor_code": None,
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

# Guest 必須連續辨識幾次才正式確認
guest_confirm_count = 0

# 連續 2 次辨識為 Guest 才正式顯示與記錄
GUEST_CONFIRM_REQUIRED = 2

# 設定參數
RECOGNITION_INTERVAL = 2       # 每 2 秒做一次人臉比對
LAST_SEEN_UPDATE_INTERVAL = 15 # 每 15 秒更新一次資料庫
GUEST_LOG_INTERVAL = 60        # Guest 每 60 秒最多記錄一次，避免太頻繁
MIN_CONFIDENCE = 0.5           # 信心值低於 0.5 的會員辨識結果先不記錄
LEAVE_TIMEOUT = 60             # 超過 60 秒沒再看到同一會員，就先視為離店
CAMERA_ID = "camera_1"         # 對應 recognition_logs.camera_id




def now_text():
    """回傳目前時間文字，格式統一給 recognition_logs 使用。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def open_camera(camera_index=CAMERA_INDEX):
    """
    開啟攝影機。

    Windows 建議使用 cv2.CAP_DSHOW，
    外接 USB 攝影機通常能更快開啟，
    也較不容易出現 MSMF 無法讀取畫面的問題。
    """

    print(
        f"嘗試開啟攝影機，"
        f"camera_index={camera_index}"
    )

    # 必須先建立 cap，後面才能使用 cap.set()
    cap = cv2.VideoCapture(
        camera_index,
        cv2.CAP_DSHOW
    )

    # 設定攝影機畫面大小與 FPS
    cap.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        CAMERA_WIDTH
    )
    cap.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        CAMERA_HEIGHT
    )
    cap.set(
        cv2.CAP_PROP_FPS,
        CAMERA_FPS
    )

    # 盡量只保留最新畫面，降低畫面延遲
    cap.set(
        cv2.CAP_PROP_BUFFERSIZE,
        1
    )

    # 確認攝影機是否成功開啟
    if not cap.isOpened():
        print(
            f"無法開啟攝影機，"
            f"camera_index={camera_index}"
        )
        cap.release()
        return None

    # 讓攝影機完成自動曝光與白平衡
    for _ in range(10):
        success, frame = cap.read()

        if not success or frame is None:
            print(
                f"攝影機暖機失敗，"
                f"camera_index={camera_index}"
            )
            cap.release()
            return None

        time.sleep(0.03)

    print(
        f"已開啟攝影機，"
        f"camera_index={camera_index}"
    )

    return cap

def acquire_camera():
    """
    取得攝影機。

    不可從另一個執行緒強制 release，
    否則 Windows DirectShow 可能直接造成 Python 崩潰。
    """

    global camera_instance

    with camera_instance_lock:
        if (
            camera_instance is not None
            and camera_instance.isOpened()
        ):
            return camera_instance

        camera_instance = open_camera(CAMERA_INDEX)

        return camera_instance


def release_camera(cap):
    """
    安全釋放指定攝影機。

    只有目前使用中的 cap 才會清除全域 camera_instance，
    避免舊串流結束時誤清除新串流。
    """

    global camera_instance

    if cap is None:
        return

    with camera_instance_lock:
        try:
            cap.release()
        except Exception as e:
            print(f"攝影機釋放失敗：{e}")

        if camera_instance is cap:
            camera_instance = None

    print("攝影機已釋放")


def update_member_visit(result, current_time):
    """將會員 active visit 流程交由 visit_service 統一處理。"""
    outcome = handle_recognition(
        result=result,
        current_time=current_time,
        current_time_text=now_text(),
        active_visits=active_visits,
        active_visits_lock=active_visits_lock,
        camera_id=CAMERA_ID,
        leave_timeout=LEAVE_TIMEOUT,
        last_seen_update_interval=LAST_SEEN_UPDATE_INTERVAL,
        get_active_visit_fn=get_active_visit,
        create_log_fn=log_recognition_result,
        update_last_seen_fn=update_recognition_last_seen,
        close_visit_fn=close_recognition_visit,
        notify_fn=send_line_notify,
    )

    action = outcome.get("action")
    log_id = outcome.get("log_id")
    member_id = outcome.get("member_id")

    if action == "restored":
        print("========== Active Visit Restored ==========")
        print(f"member_id: {member_id}")
        print(f"log_id: {log_id}")
        print("未新增新的 recognition log")
        print("===========================================")

    elif action == "created":
        print("========== Member Visit Started ==========")
        print(f"member_id: {member_id}")
        print(f"log_id: {log_id}")
        print("==========================================")

        notification_status = outcome.get("notification_status")
        if notification_status is not None:
            print("========== VIP Notify Result ==========")
            print(f"log_id: {log_id}")
            print(f"notification_status: {notification_status}")
            print("=======================================")

    elif action == "failed":
        print(
            f"會員到店紀錄新增失敗，"
            f"member_id={member_id}"
        )

def close_timeout_visits(current_time):
    """將離店逾時處理交由 visit_service 統一處理。"""
    closed_visits = close_timeout_visits_service(
        current_time=current_time,
        active_visits=active_visits,
        active_visits_lock=active_visits_lock,
        leave_timeout=LEAVE_TIMEOUT,
        close_visit_fn=close_recognition_visit,
        current_time_text_fn=now_text,
    )

    for visit in closed_visits:
        print("========== Member Visit Ended ==========")
        print(f"member_id: {visit.get('member_id')}")
        print(f"log_id: {visit.get('log_id')}")
        print(f"leave_time: {visit.get('leave_time')}")
        print(f"stay_seconds: {visit.get('stay_seconds')}")
        print(f"stay_minutes: {visit.get('stay_minutes')}")
        print("========================================")

def generate_frames():
    global last_recognition_time
    global last_result
    global last_guest_log_time
    global guest_confirm_count

    last_member_reload_time = 0
    member_reload_interval = 5

    # 同一時間只允許一個網頁串流讀取攝影機
    lock_acquired = camera_stream_lock.acquire(
        blocking=False
    )

    if not lock_acquired:
        print("已有攝影機串流正在執行，略過重複請求")
        return

    cap = acquire_camera()

    if cap is None:
        print("攝影機串流停止：無法取得攝影機")
        return

    try:
        while True:

            time.sleep(0.01)

            current_time = time.time()

            # 每 5 秒重新載入會員人臉快取
            if (
                current_time - last_member_reload_time
                >= member_reload_interval
            ):
                try:
                    loaded_members = reload_member_faces()

                    print(
                        f"會員人臉快取已自動更新，共 {len(loaded_members)} 筆"
                    )

                    last_member_reload_time = current_time

                except Exception as e:
                    print(f"會員快取更新失敗：{e}")

            success, frame = cap.read()

            if not success or frame is None:
                print("讀取攝影機畫面失敗，結束本次串流")
                break

            faces = detect_face(frame)
            has_face = len(faces) > 0

            # -----------------------------
            # 沒有人臉
            # -----------------------------
            if not has_face:

                guest_confirm_count = 0

                last_result = {
                    "subject_type": "none",
                    "member_id": None,
                    "visitor_id": None,
                    "visitor_code": None,
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

            # -----------------------------
            # 到達辨識間隔才做人臉辨識
            # -----------------------------
            elif (
                current_time - last_recognition_time
                >= RECOGNITION_INTERVAL
            ):

                recognition_result = recognize_face(
                    frame,
                    faces
                )

                last_recognition_time = current_time

                recognition_status = recognition_result.get(
                    "recognition_status"
                )

                print("recognition_status =", recognition_status)

                # ----------------------------------------
                # 正式會員
                # ----------------------------------------
                if recognition_status == "recognized":

                    guest_confirm_count = 0
                    last_result = recognition_result

                # ----------------------------------------
                # Guest
                # ----------------------------------------
                elif recognition_status == "guest":

                    guest_confirm_count += 1

                    print(
                        f"Guest Confirm: "
                        f"{guest_confirm_count}/"
                        f"{GUEST_CONFIRM_REQUIRED}"
                    )

                    # 連續辨識成功才建立固定散客
                    if guest_confirm_count >= GUEST_CONFIRM_REQUIRED:

                        print(
                            "未知人臉連續確認完成，開始建立固定散客"
                        )

                        visitor_result = register_new_visitor(
                            frame,
                            faces
                        )

                        if (
                            visitor_result.get("subject_type")
                            == "visitor"
                            and visitor_result.get("visitor_id")
                            is not None
                        ):

                            last_result = visitor_result

                            print(
                                "固定散客建立成功："
                                f"visitor_id="
                                f"{visitor_result.get('visitor_id')}"
                            )

                        else:

                            last_result = visitor_result

                            print(
                                "固定散客建立失敗，"
                                "本次不寫入到店紀錄"
                            )

                        # 重置計數
                        guest_confirm_count = 0

                    else:

                        # 第一次 Guest 僅顯示 Detecting
                        last_result = {
                            "subject_type": "unknown",
                            "member_id": None,
                            "visitor_id": None,
                            "visitor_code": None,
                            "name": "Detecting",
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
                            "recognition_status": "detecting",
                            "member_level_text": "Detecting"
                        }

                # ----------------------------------------
                # 其它狀態
                # ----------------------------------------
                else:

                    guest_confirm_count = 0
                    last_result = recognition_result

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
                and current_subject_type == "member"
                and current_member_id is not None
                and current_confidence >= MIN_CONFIDENCE
                and current_recognition_status == "recognized"
            ):
                update_member_visit(
                    last_result,
                    current_time
                )

            # ----------------------------------------
            # 固定散客到店紀錄
            # ----------------------------------------
            elif (
                has_face
                and current_subject_type == "visitor"
                and current_visitor_id is not None
                and current_recognition_status == "recognized"
            ):
                update_member_visit(
                    last_result,
                    current_time
                )

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
        print("攝影機串流結束，釋放資源")
        release_camera(cap)
        if camera_stream_lock.locked():
            camera_stream_lock.release()


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
