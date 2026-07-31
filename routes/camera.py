import os
import cv2
import numpy as np
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from flask import Blueprint, Response, jsonify
from services.visit_service import (
    build_subject_key,
    handle_recognition,
    close_timeout_visits as close_timeout_visits_service,
)
from database.db import (
    get_active_visit,
    get_member_by_id,
    get_member_preferences,
    get_visitor_by_id,
)

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
    reload_all_faces,
)
from linebot_service.notify import notify_preference_promo
camera_bp = Blueprint("camera", __name__)

# 全域共用的攝影機物件
camera_instance = None

# 保護攝影機物件的建立與釋放，
# 避免多個執行緒同時修改 camera_instance。
camera_instance_lock = threading.Lock()

# 同一時間只允許一個 /camera/video_feed 串流執行，
# 避免重新整理或開啟多個分頁時同時搶用攝影機。
camera_stream_lock = threading.Lock()

# 雲端 I/O 不可阻塞 MJPEG 影格產生器。
face_cache_worker_lock = threading.Lock()
face_cache_worker_started = False
face_cache_refresh_wakeup = threading.Event()
visit_db_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="visit-db",
)
visit_update_pending = set()
visit_update_pending_lock = threading.Lock()
camera_ai_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="camera-ai",
)
visitor_conversion_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="visitor-conversion",
)

# =============================
# 攝影機連線狀態
# =============================

camera_status = {
    "connected": False,
    "status": "Disconnected",
    "message": "攝影機尚未開啟"
}

camera_status_lock = threading.Lock()

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
    "total_visit_count": 0,
    "last_visit_time": None,
    "total_visit_time": 0,
    "updated_by": None,
    "visitor_visit_count": 0,
    "converted_member_id": None,
    "best_face_image": None,
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


def clear_visitor_active_visit(visitor_id):
    """散客轉會員後清除舊狀態，讓下一幀立即重新辨識。"""
    global last_result
    global last_recognition_time

    visitor_key = build_subject_key(
        subject_type="visitor",
        visitor_id=visitor_id,
    )

    with active_visits_lock:
        removed_visit = active_visits.pop(visitor_key, None)

        if (
            last_result.get("subject_type") == "visitor"
            and last_result.get("visitor_id") == visitor_id
        ):
            last_result = {}

        last_recognition_time = 0

    return removed_visit is not None


def convert_visitor_active_visit(
    visitor_id,
    member_id,
    name,
    vip=False,
    member_level="normal",
    line_user_id=None,
    converted_active_log_id=None,
):
    """Keep the same active Log ID when a visitor registers in store."""
    global last_result
    global last_recognition_time

    visitor_key = build_subject_key(
        subject_type="visitor",
        visitor_id=visitor_id,
    )
    member_key = build_subject_key(
        subject_type="member",
        member_id=member_id,
    )

    with active_visits_lock:
        visit_data = active_visits.pop(visitor_key, None)

        converted_result = {}
        if visit_data:
            converted_result.update(visit_data.get("result") or {})
        if (
            last_result.get("subject_type") == "visitor"
            and last_result.get("visitor_id") == visitor_id
        ):
            converted_result.update(last_result)

        effective_log_id = converted_active_log_id

        converted_result.update({
            "subject_type": "member",
            "member_id": member_id,
            "visitor_id": visitor_id,
            "name": name,
            "vip": bool(vip),
            "line_user_id": line_user_id,
            "member_level": member_level,
            "member_level_text": (
                "VIP 會員" if bool(vip) or member_level == "vip"
                else "一般會員"
            ),
            "recognition_status": "recognized",
        })
        if effective_log_id is not None:
            converted_result["log_id"] = effective_log_id

        if visit_data is None or effective_log_id is None:
            last_result = converted_result
            last_recognition_time = 0
            return True

        visit_data["log_id"] = effective_log_id
        visit_data["result"] = converted_result
        active_visits[member_key] = visit_data
        last_result = converted_result
        last_recognition_time = 0
        return True
# 訪客上一次產生 recognition log 的時間
last_guest_log_time = 0

# Guest 必須連續辨識幾次才正式確認
guest_confirm_count = 0
guest_candidate_encoding = None

# 連續 2 次辨識為 Guest 才正式顯示與記錄
GUEST_CONFIRM_REQUIRED = max(
    get_int_env("GUEST_CONFIRM_REQUIRED", 3),
    2,
)
GUEST_STABILITY_TOLERANCE = float(
    os.getenv("GUEST_STABILITY_TOLERANCE", "0.45")
)

# 連續幾幀沒有偵測到人臉，
# 才正式切換成 no_face，避免眨眼或瞬間轉頭造成畫面閃爍。
no_face_frame_count = 0

# 建議先從 5 幀開始測試。
NO_FACE_CONFIRM_REQUIRED = 5

# 設定參數
RECOGNITION_INTERVAL = 2       # 每 2 秒做一次人臉比對
CAMERA_ANALYSIS_INTERVAL = max(
    float(os.getenv("CAMERA_ANALYSIS_INTERVAL", "0.15")),
    0.05,
)
LAST_SEEN_UPDATE_INTERVAL = 15 # 每 15 秒更新一次資料庫
VISIT_STATE_INTERVAL = 1.0     # 到店狀態最多每秒排入一次背景更新
VISITOR_CONVERSION_CHECK_INTERVAL = 2.0
GUEST_LOG_INTERVAL = 60        # Guest 每 60 秒最多記錄一次，避免太頻繁
MIN_CONFIDENCE = 0.5           # 信心值低於 0.5 的會員辨識結果先不記錄
LEAVE_TIMEOUT = 60             # 超過 60 秒沒再看到同一會員，就先視為離店
FACE_CACHE_REFRESH_INTERVAL = max(
    get_int_env("FACE_CACHE_REFRESH_INTERVAL", 60),
    10
)
CAMERA_ID = os.getenv("CAMERA_ID", "camera_1")
CAMERA_LOCATION = os.getenv("CAMERA_LOCATION", "入口")


def reset_guest_confirmation():
    global guest_confirm_count
    global guest_candidate_encoding

    guest_confirm_count = 0
    guest_candidate_encoding = None


def confirm_stable_guest(recognition_result):
    """只有連續數次 encoding 都像同一張臉，才允許建立散客。"""
    global guest_confirm_count
    global guest_candidate_encoding

    encoding = recognition_result.get("_face_encoding")
    if encoding is None:
        reset_guest_confirmation()
        return False

    try:
        encoding = np.asarray(encoding, dtype=float)
    except (TypeError, ValueError):
        reset_guest_confirmation()
        return False

    if encoding.shape != (128,):
        reset_guest_confirmation()
        return False

    if guest_candidate_encoding is None:
        guest_confirm_count = 1
    else:
        distance = float(
            np.linalg.norm(
                guest_candidate_encoding - encoding
            )
        )
        if distance <= GUEST_STABILITY_TOLERANCE:
            guest_confirm_count += 1
        else:
            guest_confirm_count = 1

    guest_candidate_encoding = np.array(
        encoding,
        dtype=float
    )
    return guest_confirm_count >= GUEST_CONFIRM_REQUIRED


def _face_cache_refresh_worker():
    while True:
        refresh_started = time.monotonic()
        try:
            members, visitors = reload_all_faces()
            elapsed = time.monotonic() - refresh_started
            print(
                "背景人臉快取更新完成："
                f"會員 {len(members)} 筆，"
                f"散客 {len(visitors)} 筆，"
                f"耗時 {elapsed:.2f} 秒"
            )
        except Exception as error:
            print(f"背景人臉快取更新失敗：{error}")

        elapsed = time.monotonic() - refresh_started
        wait_seconds = max(
            FACE_CACHE_REFRESH_INTERVAL - elapsed,
            1,
        )
        face_cache_refresh_wakeup.wait(wait_seconds)
        face_cache_refresh_wakeup.clear()


def start_face_cache_refresh_worker():
    global face_cache_worker_started

    with face_cache_worker_lock:
        if face_cache_worker_started:
            return False

        worker = threading.Thread(
            target=_face_cache_refresh_worker,
            name="face-cache-refresh",
            daemon=True,
        )
        face_cache_worker_started = True
        worker.start()
        return True


def queue_recognition_last_seen(log_id, last_seen_at):
    """將週期性 last_seen 寫入交給單一背景執行緒。"""
    visit_db_executor.submit(
        update_recognition_last_seen,
        log_id,
        last_seen_at,
    )
    return True


def queue_member_visit_update(result, current_time):
    subject_key = build_subject_key(
        subject_type=result.get("subject_type"),
        member_id=result.get("member_id"),
        visitor_id=result.get("visitor_id"),
    )
    if subject_key is None:
        return False

    with visit_update_pending_lock:
        if subject_key in visit_update_pending:
            return False
        visit_update_pending.add(subject_key)

    def run_update():
        try:
            update_member_visit(
                dict(result),
                current_time,
            )
        finally:
            with visit_update_pending_lock:
                visit_update_pending.discard(subject_key)

    visit_db_executor.submit(run_update)
    return True


def check_visitor_conversion(visitor_id):
    """
    跨 Flask／Cloud Run 執行個體檢查散客是否已由 LINE 轉成會員。
    """
    visitor = get_visitor_by_id(visitor_id)
    if not visitor:
        return None

    member_id = visitor.get("converted_member_id")
    if member_id is None:
        return None

    member = get_member_by_id(member_id)
    if not member:
        return None

    active_visit = get_active_visit(
        subject_type="member",
        subject_id=member_id,
        camera_id=CAMERA_ID,
    )

    return {
        "visitor_id": visitor_id,
        "member": member,
        "converted_active_log_id": (
            active_visit.get("log_id")
            if active_visit
            else None
        ),
    }


def build_camera_display_result(
    recognition_status,
    name,
    member_level_text,
):
    return {
        "subject_type": "none",
        "member_id": None,
        "visitor_id": None,
        "visitor_code": None,
        "name": name,
        "phone": None,
        "vip": False,
        "member_level": "guest",
        "total_visit_count": 0,
        "last_visit_time": None,
        "total_visit_time": 0,
        "updated_by": None,
        "visitor_visit_count": 0,
        "converted_member_id": None,
        "best_face_image": None,
        "line_user_id": None,
        "registration_source": None,
        "total_amount": 0,
        "favorite_product": None,
        "face_image": None,
        "confidence": 0,
        "recognition_status": recognition_status,
        "member_level_text": member_level_text,
    }


def process_camera_recognition(frame, faces):
    """
    在 camera-ai 背景執行緒完成 encoding、比對與散客建檔。
    MJPEG 串流只讀取完成結果，不等待這些高成本工作。
    """
    recognition_result = recognize_face(frame, faces)
    recognition_status = recognition_result.get(
        "recognition_status"
    )

    if recognition_status == "recognized":
        reset_guest_confirmation()
        return recognition_result

    if recognition_status == "guest":
        if confirm_stable_guest(recognition_result):
            print("未知人臉連續確認完成，開始建立固定散客")
            visitor_result = register_new_visitor(
                frame,
                faces,
                encoding=recognition_result.get("_face_encoding"),
            )
            reset_guest_confirmation()
            return visitor_result

        return build_camera_display_result(
            recognition_status="detecting",
            name="Detecting",
            member_level_text="Detecting",
        )

    reset_guest_confirmation()
    return recognition_result


def analyze_camera_frame(frame, perform_recognition):
    """
    背景分析單張快照。偵測每輪執行，完整辨識依既有 2 秒間隔執行。
    """
    faces = detect_face(frame)
    result = None

    if perform_recognition and faces:
        result = process_camera_recognition(
            frame,
            faces,
        )

    return {
        "faces": faces,
        "result": result,
    }


def update_camera_status(
    connected,
    status,
    message
):
    """
    更新攝影機目前連線狀態。

    connected：
    True 代表攝影機可正常讀取；
    False 代表尚未開啟或已中斷。
    """

    with camera_status_lock:
        camera_status["connected"] = connected
        camera_status["status"] = status
        camera_status["message"] = message

def now_text():
    """回傳目前時間文字，格式統一給 recognition_logs 使用。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def open_camera(camera_index=CAMERA_INDEX):
    """
    開啟攝影機。
    """

    update_camera_status(
        connected=False,
        status="Connecting",
        message="正在嘗試開啟攝影機"
    )

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
        
        update_camera_status(
            connected=False,
            status="Disconnected",
            message="無法開啟攝影機"
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
            
            update_camera_status(
                connected=False,
                status="Disconnected",
                message="攝影機暖機失敗"
            )
            
            cap.release()
            return None

        time.sleep(0.03)

    print(
        f"已開啟攝影機，"
        f"camera_index={camera_index}"
    )
    
    update_camera_status(
        connected=True,
        status="Connected",
        message="攝影機已正常連線"
    )
    
    return cap

def acquire_camera():
    """
    取得攝影機。

    若全域攝影機物件已經成功開啟，
    直接沿用目前的攝影機，不主動 release()。

    這樣可以避免瀏覽器重新整理或第二個請求進入時，
    把另一個正在使用攝影機的執行緒強制中斷。
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
    
    update_camera_status(
        connected=False,
        status="Disconnected",
        message="攝影機串流已關閉"
    )

    print("攝影機已釋放")


def update_member_visit(result, current_time):
    """將會員或固定散客 active visit 流程交由 visit_service 統一處理。"""
    result["camera_id"] = CAMERA_ID
    result["camera_location"] = CAMERA_LOCATION

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
        update_last_seen_fn=queue_recognition_last_seen,
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
        print("========== Subject Visit Started ==========")
        print(f"subject_type: {outcome.get('subject_type')}")
        print(f"member_id: {outcome.get('member_id')}")
        print(f"visitor_id: {outcome.get('visitor_id')}")
        print(f"member_id: {member_id}")
        print(f"log_id: {log_id}")
        print("==========================================")

        notification_status = outcome.get("notification_status")
        if notification_status is not None:
            print("========== VIP Notify Result ==========")
            print(f"log_id: {log_id}")
            print(f"notification_status: {notification_status}")
            print("=======================================")

        if outcome.get("subject_type") == "member":
            try:
                preferences = get_member_preferences(member_id)
                promo_status = notify_preference_promo(
                    {
                        "name": result.get("name"),
                        "line_user_id": result.get("line_user_id"),
                    },
                    preferences=preferences,
                )
                print("========== Preference Promo Result ==========")
                print(f"log_id: {log_id}")
                print(f"preferences: {preferences}")
                print(f"promo_status: {promo_status}")
                print("===============================================")
            except Exception as e:
                print(f"喜好推播失敗（member_id={member_id}）：", e)

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

def close_all_active_visits():
    """關閉攝影機時，把所有尚未結束的 visit 全部結束。"""

    current_time = time.time()
    current_time_text = now_text()

    with active_visits_lock:
        visit_list = list(active_visits.items())

    for subject_key, visit_data in visit_list:

        log_id = visit_data.get("log_id")
        if log_id is None:
            continue

        visit_timestamp = visit_data.get(
            "visit_timestamp",
            current_time
        )

        last_seen_at = (
            visit_data.get("last_seen_at")
            or current_time_text
        )

        stay_seconds = max(
            int(current_time - visit_timestamp),
            0
        )

        stay_minutes = round(stay_seconds / 60, 2)

        closed = close_recognition_visit(
            log_id=log_id,
            last_seen_at=last_seen_at,
            leave_time=current_time_text,
            stay_seconds=stay_seconds,
            stay_minutes=stay_minutes
        )

        if closed:
            with active_visits_lock:
                active_visits.pop(subject_key, None)


def generate_frames():
    global last_recognition_time
    global last_result
    global last_guest_log_time
    global guest_confirm_count
    global guest_candidate_encoding
    global no_face_frame_count

    # 嘗試取得攝影機串流鎖。
    # blocking=False 表示若已有串流正在執行，
    # 不等待，直接結束這次新的串流請求。
    lock_acquired = camera_stream_lock.acquire(
        blocking=False
    )

    if not lock_acquired:
        print("已有攝影機串流正在執行")
        return

    # 先設為 None，確保 finally 可以安全判斷與釋放。
    cap = None

    try:
        cap = acquire_camera()

        if cap is None:
            print("攝影機串流停止：無法取得攝影機")
            return

        # =============================
        # FPS 計算初始值
        # =============================
        # 使用 monotonic() 計時，不受電腦系統時間調整影響。
        fps_start_time = time.monotonic()

        # 記錄這一秒內成功處理的畫面數量。
        fps_frame_count = 0

        # 實際顯示在攝影機畫面上的 FPS。
        current_fps = 0.0

        # AI 分析在背景執行；串流沿用最近一次完成的結果。
        analysis_future = None
        last_analysis_submit_time = 0.0
        last_visit_dispatch_time = 0.0
        conversion_future = None
        conversion_visitor_id = None
        last_conversion_check_time = 0.0
        converted_visitor_ids = set()
        last_detected_faces = []

        # 快取由背景執行緒同步，攝影串流不等待雲端 DB。
        start_face_cache_refresh_worker()

        while True:
            time.sleep(0.01)
            current_time = time.time()
            
            success, frame = cap.read()
            
            if not success or frame is None:
                print("讀取攝影機畫面失敗，結束本次串流")
                update_camera_status(
                    connected=False,
                    status="Disconnected",
                    message="攝影機畫面讀取失敗"
                )
                
                break

            # 每成功取得一張畫面，就累積一幀。
            fps_frame_count += 1
            
            # 計算距離上次更新 FPS 經過多少秒。
            fps_elapsed_time = (
                time.monotonic()
                - fps_start_time
            )
            
            # 每隔至少 1 秒更新一次 FPS，
            # 避免數字每一幀快速跳動。
            if fps_elapsed_time >= 1.0:
                current_fps = round(
                    fps_frame_count / fps_elapsed_time,
                    1
                )
                
                # 重設下一輪 FPS 計算。
                fps_frame_count = 0
                fps_start_time = time.monotonic()

            # 先接收背景 AI 已完成的分析，不等待尚未完成的 future。
            if (
                analysis_future is not None
                and analysis_future.done()
            ):
                try:
                    analysis_result = analysis_future.result()
                    last_detected_faces = analysis_result.get(
                        "faces",
                        [],
                    )
                    completed_result = analysis_result.get("result")

                    if last_detected_faces:
                        no_face_frame_count = 0
                        completed_visitor_id = (
                            completed_result.get("visitor_id")
                            if completed_result
                            else None
                        )
                        is_stale_visitor_result = (
                            completed_result is not None
                            and completed_result.get("subject_type")
                            == "visitor"
                            and completed_visitor_id
                            in converted_visitor_ids
                        )
                        if (
                            completed_result is not None
                            and not is_stale_visitor_result
                        ):
                            last_result = completed_result
                    else:
                        no_face_frame_count += 1
                        reset_guest_confirmation()

                        if (
                            no_face_frame_count
                            >= NO_FACE_CONFIRM_REQUIRED
                        ):
                            last_result = build_camera_display_result(
                                recognition_status="no_face",
                                name="No Face",
                                member_level_text="No Face",
                            )

                except Exception as analysis_error:
                    print(f"背景攝影辨識失敗：{analysis_error}")
                finally:
                    analysis_future = None

            monotonic_now = time.monotonic()
            if (
                analysis_future is None
                and monotonic_now - last_analysis_submit_time
                >= CAMERA_ANALYSIS_INTERVAL
            ):
                perform_recognition = (
                    current_time - last_recognition_time
                    >= RECOGNITION_INTERVAL
                )

                if perform_recognition:
                    last_recognition_time = current_time

                analysis_future = camera_ai_executor.submit(
                    analyze_camera_frame,
                    frame.copy(),
                    perform_recognition,
                )
                last_analysis_submit_time = monotonic_now

            # 串流不等待背景工作，沿用最近一次人臉框與辨識結果。
            faces = last_detected_faces
            has_face = len(faces) > 0

            if (
                conversion_future is not None
                and conversion_future.done()
            ):
                try:
                    conversion_result = conversion_future.result()
                    if conversion_result:
                        converted_visitor_id = (
                            conversion_result["visitor_id"]
                        )
                        converted_member = conversion_result["member"]
                        converted_visitor_ids.add(
                            converted_visitor_id
                        )
                        convert_visitor_active_visit(
                            visitor_id=converted_visitor_id,
                            member_id=converted_member["member_id"],
                            name=converted_member.get("name"),
                            vip=converted_member.get("vip", False),
                            member_level=converted_member.get(
                                "member_level",
                                "normal",
                            ),
                            line_user_id=converted_member.get(
                                "line_user_id"
                            ),
                            converted_active_log_id=(
                                conversion_result.get(
                                    "converted_active_log_id"
                                )
                            ),
                        )
                        face_cache_refresh_wakeup.set()
                        print(
                            "攝影頁已同步散客轉會員："
                            f"visitor_id={converted_visitor_id}，"
                            f"member_id="
                            f"{converted_member['member_id']}"
                        )
                except Exception as conversion_error:
                    print(
                        "檢查散客轉會員失敗："
                        f"{conversion_error}"
                    )
                finally:
                    conversion_future = None
                    conversion_visitor_id = None

            current_visitor_for_conversion = (
                last_result.get("visitor_id")
                if last_result.get("subject_type") == "visitor"
                else None
            )
            if (
                current_visitor_for_conversion is not None
                and current_visitor_for_conversion
                not in converted_visitor_ids
                and conversion_future is None
                and (
                    current_time - last_conversion_check_time
                    >= VISITOR_CONVERSION_CHECK_INTERVAL
                )
            ):
                conversion_visitor_id = (
                    current_visitor_for_conversion
                )
                conversion_future = (
                    visitor_conversion_executor.submit(
                        check_visitor_conversion,
                        conversion_visitor_id,
                    )
                )
                last_conversion_check_time = current_time


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
                and (
                    current_time - last_visit_dispatch_time
                    >= VISIT_STATE_INTERVAL
                )
            ):
                queued = queue_member_visit_update(
                    last_result,
                    current_time
                )
                if queued:
                    last_visit_dispatch_time = current_time
            
            
            # ----------------------------------------
            # 固定散客到店紀錄
            # ----------------------------------------
            elif (
                has_face
                and current_subject_type == "visitor"
                and current_visitor_id is not None
                and current_recognition_status == "recognized"
                and (
                    current_time - last_visit_dispatch_time
                    >= VISIT_STATE_INTERVAL
                )
            ):
                queued = queue_member_visit_update(
                    last_result,
                    current_time
                )
                if queued:
                    last_visit_dispatch_time = current_time

            # 檢查已經超過離店等待時間的對象
            # 並將原本紀錄更新為 visit_status="left"
            close_timeout_visits(current_time)

            # 無論有沒有人臉，都顯示目前辨識狀態與 FPS。
            # faces 為空時不會畫人臉框，只會顯示左上角資訊。
            frame = draw_face_boxes(
                frame,
                faces,
                last_result,
                current_fps=current_fps
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
        
        update_camera_status(
            connected=False,
            status="Disconnected",
            message="攝影機串流發生錯誤"
        )

    finally:
        close_all_active_visits()
        release_camera(cap)
        
        if camera_stream_lock.locked():
            camera_stream_lock.release()


@camera_bp.route("/camera")
def camera():
    return """
    <h1>智慧會員辨識系統 - 攝影機畫面</h1>

    <p>即時攝影機串流</p>

    <p>
        Camera Status：
        <strong id="camera-status">
            Connecting
        </strong>
    </p>

    <p id="camera-message">
        正在確認攝影機狀態
    </p>

    <p>
        本週測試重點：
        攝影機 FPS、連線／中斷狀態、
        VIP／一般會員／散客標籤、
        no_face／failed 防呆
    </p>

    <img
        id="camera-stream"
        src="/camera/video_feed"
        width="640"
        alt="攝影機串流"
    >

    <script>
        async function refreshCameraStatus() {
            const statusElement =
                document.getElementById(
                    "camera-status"
                );

            const messageElement =
                document.getElementById(
                    "camera-message"
                );

            try {
                const response = await fetch(
                    "/camera/status",
                    {
                        cache: "no-store"
                    }
                );

                const data = await response.json();

                statusElement.textContent =
                    data.status;

                messageElement.textContent =
                    data.message;

                if (data.connected) {
                    statusElement.style.color =
                        "green";

                } else if (
                    data.status === "Connecting"
                ) {
                    statusElement.style.color =
                        "orange";

                } else {
                    statusElement.style.color =
                        "red";
                }

            } catch (error) {
                statusElement.textContent =
                    "Disconnected";

                statusElement.style.color =
                    "red";

                messageElement.textContent =
                    "無法取得攝影機狀態";
            }
        }

        refreshCameraStatus();

        setInterval(
            refreshCameraStatus,
            2000
        );
    </script>
    """


@camera_bp.route("/camera/status")
def get_camera_status():
    """
    提供前端查詢目前攝影機連線狀態。
    """

    with camera_status_lock:
        return jsonify({
            "connected": camera_status["connected"],
            "status": camera_status["status"],
            "message": camera_status["message"]
        })



@camera_bp.route("/camera/reload-faces", methods=["POST"])
def reload_faces():
    """
    重新載入正式資料庫的人臉資料
    """
    try:
        members, visitors = reload_all_faces()

        print("========== Face Reload API ==========")
        print(f"Member Faces : {len(members)}")
        print(f"Visitor Faces: {len(visitors)}")
        print("=====================================")

        return {
            "success": True,
            "message": "Face data reloaded successfully.",
            "member_count": len(members),
            "visitor_count": len(visitors),
        }, 200

    except Exception as e:
        print(f"Face Reload API 失敗：{e}")

        return {
            "success": False,
            "message": "Face data reload failed.",
        }, 500


@camera_bp.route("/camera/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )
