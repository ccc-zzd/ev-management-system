# -*- coding: utf-8 -*-
"""
新能源汽车综合管理系统 - Flask 后端 API
"""

import os
import csv
import uuid
import hashlib
import json
import urllib.request
import urllib.parse
from datetime import datetime, date

from flask import Flask, request, session, jsonify, render_template
from werkzeug.exceptions import HTTPException
import pymysql

from db_config import DB_CONFIG, DATA_DIR

app = Flask(__name__)
app.secret_key = "ev_management_secret_key_2024"


# ============================================================
# 静态资源缓存：图片设强缓存，避免同一张车图被多卡片重复下载导致加载慢/白块
# ============================================================
@app.after_request
def add_cache_headers(response):
    if request.path.startswith("/static/cars/"):
        # 车辆图片：缓存 7 天，浏览器只下载一次
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    elif request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=3600"
    return response


# ============================================================
# 数据库连接工具
# ============================================================

def get_db():
    """获取数据库连接"""
    config = DB_CONFIG.copy()
    config["cursorclass"] = pymysql.cursors.DictCursor
    return pymysql.connect(**config)


# ============================================================
# 密码工具
# ============================================================

def hash_password(password, username):
    """SHA256 + 随机盐，返回「盐$摘要」；新注册用户使用，避免固定盐被字典反推"""
    import secrets as _secrets
    salt = _secrets.token_hex(8)
    digest = hashlib.sha256((salt + password + username).encode("utf-8")).hexdigest()
    return "%s$%s" % (salt, digest)


def verify_password(password, username, stored):
    """校验密码：兼容新版「盐$摘要」与旧版「sha256(密码+用户名)」"""
    if not stored:
        return False
    if "$" in stored:
        salt, digest = stored.split("$", 1)
        return hashlib.sha256((salt + password + username).encode("utf-8")).hexdigest() == digest
    # 兼容历史数据（未加盐）
    return hashlib.sha256((password + username).encode("utf-8")).hexdigest() == stored


# ============================================================
# 权限检查
# ============================================================

def get_current_user():
    """获取当前登录用户"""
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id, username, role, phone FROM `user` WHERE user_id=%s", (user_id,))
            return cursor.fetchone()
    finally:
        conn.close()


def require_login():
    """检查是否登录，返回 (user, error_response)"""
    user = get_current_user()
    if not user:
        return None, {"code": 401, "msg": "请先登录", "data": None}
    return user, None


def require_admin():
    """检查是否管理员，返回 (user, error_response)"""
    user = get_current_user()
    if not user:
        return None, {"code": 401, "msg": "请先登录", "data": None}
    if user.get("role") != "admin":
        return None, {"code": 403, "msg": "需要管理员权限", "data": None}
    return user, None


def success(data=None, msg="成功", **extra):
    resp = {"code": 0, "msg": msg, "data": data}
    resp.update(extra)
    return resp


def error(msg="失败", code=400):
    return {"code": code, "msg": msg, "data": None}


# ============================================================
# 页面路由
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/car_list")
def car_list_page():
    return render_template("car_list.html")


@app.route("/car_detail")
@app.route("/car_detail/<path:car_name>")
def car_detail_page(car_name=None):
    if not car_name:
        car_name = request.args.get("car_name", "")
    return render_template("car_detail.html", car_name=car_name)


@app.route("/test_drive")
def test_drive_page():
    return render_template("test_drive.html")


@app.route("/my_drives")
def my_drives_page():
    return render_template("my_drives.html")


@app.route("/my_orders")
def my_orders_page():
    return render_template("my_orders.html")


@app.route("/repair")
def repair_page():
    return render_template("repair.html")


@app.route("/my_repairs")
def my_repairs_page():
    return render_template("my_repairs.html")


@app.route("/favorites")
def favorites_page():
    return render_template("favorites.html")


@app.route("/profile")
def profile_page():
    return render_template("profile.html")


@app.route("/admin")
def admin_page():
    return render_template("admin.html")


@app.route("/admin/test_drives")
def admin_drives_page():
    return render_template("admin.html")


@app.route("/admin/orders")
def admin_orders_page():
    return render_template("admin.html")


@app.route("/admin/repairs")
def admin_repairs_page():
    return render_template("admin.html")


@app.route("/admin/import")
def admin_import_page():
    return render_template("admin.html")


@app.route("/stats")
def stats_page():
    return render_template("stats.html")


# ============================================================
# 用户相关 API
# ============================================================

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    phone = data.get("phone", "").strip()

    if not username or not password:
        return error("用户名和密码不能为空")
    if phone and not (phone.isdigit() and len(phone) == 11):
        return error("手机号格式不正确（应为 11 位数字）")
    if len(username) < 2 or len(username) > 20:
        return error("用户名长度应为 2-20 个字符")
    if len(password) < 6:
        return error("密码长度不能少于 6 位")

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM `user` WHERE username=%s", (username,))
            if cursor.fetchone():
                return error("用户名已存在")

            pwd_hash = hash_password(password, username)
            cursor.execute(
                "INSERT INTO `user` (username, password, phone, role) VALUES (%s, %s, %s, 'user')",
                (username, pwd_hash, phone)
            )
        conn.commit()
        return success(msg="注册成功")
    finally:
        conn.close()


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return error("用户名和密码不能为空")

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, username, role, phone, password FROM `user` WHERE username=%s",
                (username,)
            )
            user = cursor.fetchone()
            if not user or not verify_password(password, username, user["password"]):
                return error("用户名或密码错误")

            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return success(data={
                "user_id": user["user_id"],
                "username": user["username"],
                "role": user["role"]
            }, msg="登录成功")
    finally:
        conn.close()


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return success(msg="已退出登录")


@app.route("/api/me")
def api_me():
    user = get_current_user()
    if not user:
        return error("未登录", 401)
    return success(data=user)


# ============================================================
# 个人中心 API
# ============================================================

@app.route("/api/profile")
def api_profile():
    """个人中心：账户信息 + 收藏/试驾/订单/报修数量概览"""
    user, err = require_login()
    if err:
        return jsonify(err), 401
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, username, role, phone, created_at FROM `user` WHERE user_id=%s",
                (user["user_id"],))
            info = cursor.fetchone()
            tables = {"favorite": "favorite", "test_drive": "test_drive",
                      "order": "`order`", "repair": "repair"}
            counts = {}
            for name, tbl in tables.items():
                cursor.execute("SELECT COUNT(*) AS c FROM %s WHERE user_id=%%s" % tbl,
                               (user["user_id"],))
                counts[name] = cursor.fetchone()["c"]
            return success(data={"user": info, "counts": counts})
    finally:
        conn.close()


@app.route("/api/profile", methods=["PUT"])
def api_profile_update():
    """修改个人资料（当前支持手机号）"""
    user, err = require_login()
    if err:
        return jsonify(err), 401
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "").strip()
    if phone and not (phone.isdigit() and len(phone) == 11):
        return error("手机号格式不正确（应为 11 位数字）")
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            if phone:
                cursor.execute("UPDATE `user` SET phone=%s WHERE user_id=%s",
                               (phone, user["user_id"]))
        conn.commit()
        return success(msg="资料已更新")
    finally:
        conn.close()


@app.route("/api/profile/password", methods=["POST"])
def api_profile_password():
    """修改密码：校验原密码后更新为随机盐新哈希"""
    user, err = require_login()
    if err:
        return jsonify(err), 401
    data = request.get_json(silent=True) or {}
    old_pwd = data.get("old_password", "")
    new_pwd = data.get("new_password", "").strip()
    if not old_pwd or not new_pwd:
        return error("请填写原密码和新密码")
    if len(new_pwd) < 6:
        return error("新密码长度不能少于 6 位")
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT password FROM `user` WHERE user_id=%s", (user["user_id"],))
            row = cursor.fetchone()
            if not row or not verify_password(old_pwd, user["username"], row["password"]):
                return error("原密码不正确")
            new_hash = hash_password(new_pwd, user["username"])
            cursor.execute("UPDATE `user` SET password=%s WHERE user_id=%s",
                           (new_hash, user["user_id"]))
        conn.commit()
        return success(msg="密码修改成功")
    finally:
        conn.close()


# ============================================================
# 车辆相关 API
# ============================================================

@app.route("/api/vehicles")
def api_vehicles():
    brand = request.args.get("brand", "").strip()
    min_price = request.args.get("min_price", "").strip()
    max_price = request.args.get("max_price", "").strip()
    min_range = request.args.get("min_range", "").strip()
    vtype = request.args.get("type", "").strip()
    keyword = request.args.get("keyword", "").strip()
    status = request.args.get("status", "").strip()
    limit = request.args.get("limit", "50").strip()
    page = request.args.get("page", "1").strip()
    page_size = request.args.get("page_size", "").strip()

    where_sql = " WHERE 1=1"
    params = []

    if brand:
        where_sql += " AND v.brand=%s"
        params.append(brand)
    if min_price:
        try:
            _v = float(min_price)
        except ValueError:
            _v = None
        if _v is not None:
            where_sql += " AND v.price>=%s"
            params.append(_v)
    if max_price:
        try:
            _v = float(max_price)
        except ValueError:
            _v = None
        if _v is not None:
            where_sql += " AND v.price<=%s"
            params.append(_v)
    if min_range:
        try:
            _v = int(min_range)
        except ValueError:
            _v = None
        if _v is not None:
            where_sql += " AND v.range_cltc>=%s"
            params.append(_v)
    if vtype:
        where_sql += " AND v.type=%s"
        params.append(vtype)
    if status:
        where_sql += " AND v.status=%s"
        params.append(status)
    if keyword:
        where_sql += " AND (v.brand LIKE %s OR v.series LIKE %s OR v.model LIKE %s)"
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 统计总数
            cursor.execute(f"SELECT COUNT(*) AS total FROM `vehicle` v{where_sql}", params)
            total = cursor.fetchone()["total"]

            # 排序（白名单，避免任意列注入）
            sort = request.args.get("sort", "").strip()
            order_map = {
                "price_asc": "price ASC",
                "price_desc": "price DESC",
                "range_desc": "range_cltc DESC",
                "range_asc": "range_cltc ASC",
                "rating_desc": "rating DESC",
            }
            order_clause = order_map.get(sort, "price DESC")
            # 附带头评分：LEFT JOIN 一次聚合 score 各维度分，供展示与按评分排序（比逐行子查询高效）
            sql = ("SELECT v.*, r.rating FROM `vehicle` v LEFT JOIN ("
                   "SELECT model, AVG((space_score+drive_score+range_score+"
                   "appearance_score+interior_score+value_score+smart_score)/7) AS rating "
                   "FROM `score` GROUP BY model) r ON r.model = v.model"
                   + where_sql + " ORDER BY " + order_clause)
            query_params = list(params)

            if page_size:
                try:
                    page_val = max(1, int(page))
                    size_val = max(1, int(page_size))
                    offset = (page_val - 1) * size_val
                    sql += " LIMIT %s OFFSET %s"
                    query_params.extend([size_val, offset])
                except ValueError:
                    sql += " LIMIT 50"
            else:
                try:
                    limit_val = int(limit)
                    if limit_val > 0:
                        sql += " LIMIT %s"
                        query_params.append(limit_val)
                except ValueError:
                    sql += " LIMIT 50"

            cursor.execute(sql, query_params)
            vehicles = cursor.fetchall()
            return success(data=vehicles, total=total)
    finally:
        conn.close()


@app.route("/api/car_detail")
def api_car_detail():
    car_name = request.args.get("car_name", "").strip()
    if not car_name:
        return error("缺少车辆名称")

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 查询车辆信息
            cursor.execute("SELECT * FROM `vehicle` WHERE vehicle_id=%s OR model=%s", (car_name, car_name))
            vehicle = cursor.fetchone()
            if not vehicle:
                # 尝试模糊匹配
                cursor.execute("SELECT * FROM `vehicle` WHERE model LIKE %s LIMIT 1", (f"%{car_name}%",))
                vehicle = cursor.fetchone()
            if not vehicle:
                return error("未找到该车辆")

            vehicle_id = vehicle["vehicle_id"]

            # 查询评分
            cursor.execute("""
                SELECT AVG(space_score) as avg_space, AVG(drive_score) as avg_drive,
                    AVG(range_score) as avg_range, AVG(appearance_score) as avg_appearance,
                    AVG(interior_score) as avg_interior, AVG(value_score) as avg_value,
                    AVG(smart_score) as avg_smart, COUNT(*) as score_count
                FROM `score` WHERE model=%s OR (brand=%s AND series=%s)
            """, (vehicle["model"], vehicle["brand"], vehicle["series"]))
            avg_scores = cursor.fetchone()

            # 查询评论（最多20条，带用户名）
            cursor.execute("""
                SELECT comment_id, comment_date, content, COALESCE(username,'') AS username FROM `comment`
                WHERE brand=%s AND series=%s
                ORDER BY comment_date DESC LIMIT 20
            """, (vehicle["brand"], vehicle["series"]))
            comments = cursor.fetchall()

            # 当前登录用户对该车型的已评记录（用于回填表单）
            my_review = None
            cu = get_current_user()
            if cu:
                cursor.execute(
                    "SELECT * FROM `score` WHERE user_id=%s AND model=%s LIMIT 1",
                    (cu["user_id"], vehicle["model"]))
                my_review = cursor.fetchone()

            # 查询同车系其他车型
            cursor.execute("""
                SELECT vehicle_id, model, price, range_cltc, type FROM `vehicle`
                WHERE brand=%s AND series=%s AND vehicle_id!=%s LIMIT 10
            """, (vehicle["brand"], vehicle["series"], vehicle_id))
            related = cursor.fetchall()

            return success(data={
                "vehicle": vehicle,
                "scores": avg_scores,
                "comments": comments,
                "my_review": my_review,
                "related": related
            })
    finally:
        conn.close()


@app.route("/api/car_detail/review", methods=["POST"])
def api_car_detail_review():
    """用户提交/更新车型评分与评论（登录后，一人一车一条）"""
    user, err = require_login()
    if err:
        return jsonify(err), 401
    data = request.get_json(silent=True) or {}
    model = str(data.get("model", "")).strip()
    brand = str(data.get("brand", "")).strip()
    series = str(data.get("series", "")).strip()
    if not model or not brand:
        return error("缺少车型信息")
    dims = {
        "space_score": 0, "drive_score": 0, "range_score": 0,
        "appearance_score": 0, "interior_score": 0, "value_score": 0, "smart_score": 0,
    }
    for key in dims:
        try:
            v = int(data.get(key, 0))
        except (TypeError, ValueError):
            return error("评分必须为 1-5 的整数")
        if v < 1 or v > 5:
            return error("评分必须在 1-5 之间")
        dims[key] = v
    content = str(data.get("content", "")).strip()
    if len(content) > 500:
        return error("评论内容不能超过 500 字")

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # comment_id 为 varchar(64) 主键，用「用户+车型」的确定性哈希生成，保证同用户同车型主键稳定可被更新
            cid = "C" + hashlib.sha256(("%s|%s" % (user["user_id"], model)).encode("utf-8")).hexdigest()[:32]
            # 1) 评分 upsert（同用户同车型主键/唯一键命中即更新）
            cursor.execute(
                "INSERT INTO `score` (comment_id, brand, series, model, space_score, drive_score,"
                " range_score, appearance_score, interior_score, value_score, smart_score, user_id)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON DUPLICATE KEY UPDATE space_score=VALUES(space_score), drive_score=VALUES(drive_score),"
                " range_score=VALUES(range_score), appearance_score=VALUES(appearance_score),"
                " interior_score=VALUES(interior_score), value_score=VALUES(value_score),"
                " smart_score=VALUES(smart_score)",
                (cid, brand, series, model, dims["space_score"], dims["drive_score"],
                 dims["range_score"], dims["appearance_score"], dims["interior_score"],
                 dims["value_score"], dims["smart_score"], user["user_id"]))
            # 2) 评论 upsert（同一用户同一车型仅保留一条）
            if content:
                cursor.execute(
                    "INSERT INTO `comment` (comment_id, comment_date, brand, series, model, content, user_id, username)"
                    " VALUES (%s,NOW(),%s,%s,%s,%s,%s,%s)"
                    " ON DUPLICATE KEY UPDATE content=VALUES(content), comment_date=NOW()",
                    (cid, brand, series, model, content, user["user_id"], user["username"]))
        conn.commit()
        return success(msg="评价已提交")
    finally:
        conn.close()


@app.route("/api/brands")
def api_brands():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT brand FROM `vehicle` ORDER BY brand")
            brands = [row["brand"] for row in cursor.fetchall()]
            return success(data=brands)
    finally:
        conn.close()


@app.route("/api/car_image")
def api_car_image():
    """根据车型名动态搜索图片。优先数据库已配置的图，没有则联网搜。"""
    model = request.args.get("model", "").strip()
    brand = request.args.get("brand", "").strip()
    series = request.args.get("series", "").strip()
    if not model and not brand:
        return error("缺少车型名")

    # 1. 先查数据库：精确匹配 model
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            if model:
                cursor.execute("SELECT image_url FROM `vehicle` WHERE model=%s AND image_url IS NOT NULL AND image_url!='' LIMIT 1", (model,))
                row = cursor.fetchone()
                if row and row["image_url"]:
                    return success(data={"url": row["image_url"], "source": "db"})
            # 2. 模糊匹配：同品牌同车系任意一辆的图
            if brand:
                like = "%" + (series or model[:2] if model else "") + "%"
                cursor.execute("SELECT image_url FROM `vehicle` WHERE brand=%s AND image_url IS NOT NULL AND image_url!='' LIMIT 1", (brand,))
                row = cursor.fetchone()
                if row and row["image_url"]:
                    return success(data={"url": row["image_url"], "source": "db_brand"})
    finally:
        conn.close()

    # 3. 联网搜图：用必应图片搜索
    keyword = " ".join(filter(None, [brand, model, "外观"]))
    try:
        search_url = "https://www.bing.com/images/async?" + urllib.parse.urlencode({
            "q": keyword, "first": 0, "count": 5
        })
        req = urllib.request.Request(search_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # 从 HTML 里提取 m="..." 中的 murl（原始图片URL）
        import re
        urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+?\.(?:jpg|jpeg|png|webp))', html)
        if not urls:
            urls = re.findall(r'"murl":"(https?://[^"]+?\.(?:jpg|jpeg|png|webp))"', html)
        if urls:
            return success(data={"url": urls[0], "source": "search"})
    except Exception as e:
        pass

    return error("未找到图片")


@app.route("/api/recommend")
def api_recommend():
    num = request.args.get("num", "10")
    try:
        num = int(num)
    except ValueError:
        num = 10

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 只推荐有足够评论（>=3条）且综合分>=32的车型，保证评分可信
            cursor.execute("""
                SELECT v.vehicle_id, v.brand, v.series, v.model, v.type, v.range_cltc, v.price, v.status, v.image_url,
                    ROUND(AVG(s.space_score+s.drive_score+s.range_score+s.appearance_score
                        +s.interior_score+s.value_score+s.smart_score),1) AS avg_score,
                    COUNT(s.comment_id) AS score_count
                FROM vehicle v
                JOIN score s ON v.model = s.model
                WHERE v.status = '在售'
                GROUP BY v.vehicle_id, v.brand, v.series, v.model, v.type, v.range_cltc, v.price, v.status, v.image_url
                HAVING score_count >= 3 AND avg_score >= 32
                ORDER BY avg_score DESC
                LIMIT %s
            """, (num,))
            vehicles = cursor.fetchall()
            return success(data=vehicles)
    finally:
        conn.close()


# ============================================================
# 试驾预约 API
# ============================================================

@app.route("/api/test_drive", methods=["POST"])
def api_create_test_drive():
    user, err = require_login()
    if err:
        return jsonify(err), 401

    data = request.get_json(force=True)
    vehicle_id = data.get("vehicle_id", "").strip()
    drive_date = data.get("drive_date", "").strip()
    drive_time = data.get("drive_time", "").strip()
    contact_phone = data.get("contact_phone", "").strip()
    remark = data.get("remark", "").strip()

    if not vehicle_id or not drive_date or not drive_time:
        return error("请填写完整的预约信息")

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO `test_drive` (user_id, vehicle_id, drive_date, drive_time, contact_phone, remark) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (user["user_id"], vehicle_id, drive_date, drive_time, contact_phone, remark)
            )
        conn.commit()
        return success(msg="预约成功")
    finally:
        conn.close()


@app.route("/api/my_drives")
def api_my_drives():
    user, err = require_login()
    if err:
        return jsonify(err), 401

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT td.*, v.brand, v.series, v.model, v.image_url
                FROM `test_drive` td
                LEFT JOIN `vehicle` v ON td.vehicle_id = v.vehicle_id
                WHERE td.user_id = %s
                ORDER BY td.created_at DESC
            """, (user["user_id"],))
            drives = cursor.fetchall()
            return success(data=drives)
    finally:
        conn.close()


@app.route("/api/test_drive/<int:drive_id>/cancel", methods=["PUT"])
def api_cancel_test_drive(drive_id):
    user, err = require_login()
    if err:
        return jsonify(err), 401

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            if user["role"] != "admin":
                cursor.execute(
                    "UPDATE `test_drive` SET status='已取消' WHERE drive_id=%s AND user_id=%s AND status='待确认'",
                    (drive_id, user["user_id"])
                )
            else:
                cursor.execute(
                    "UPDATE `test_drive` SET status='已取消' WHERE drive_id=%s AND status IN ('待确认','已确认')",
                    (drive_id,)
                )
            if cursor.rowcount == 0:
                return error("无法取消该预约")
        conn.commit()
        return success(msg="预约已取消")
    finally:
        conn.close()


@app.route("/api/admin/drives")
def api_admin_drives():
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    status_filter = request.args.get("status", "").strip()

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT td.*, td.drive_id as id,
                    u.username, u.phone as user_phone, u.phone as phone,
                    v.brand, v.series, v.model,
                    CONCAT(v.brand, ' ', v.series, ' ', v.model) as car_name
                FROM `test_drive` td
                LEFT JOIN `user` u ON td.user_id = u.user_id
                LEFT JOIN `vehicle` v ON td.vehicle_id = v.vehicle_id
            """
            params = []
            if status_filter:
                sql += " WHERE td.status=%s"
                params.append(status_filter)
            sql += " ORDER BY td.created_at DESC"
            cursor.execute(sql, params)
            drives = cursor.fetchall()
            return success(data=drives)
    finally:
        conn.close()


@app.route("/api/admin/drives/<int:drive_id>/confirm", methods=["PUT"])
def api_admin_confirm_drive(drive_id):
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE `test_drive` SET status='已确认' WHERE drive_id=%s AND status='待确认'",
                (drive_id,)
            )
            if cursor.rowcount == 0:
                return error("无法确认该预约")
        conn.commit()
        return success(msg="已确认预约")
    finally:
        conn.close()


@app.route("/api/admin/drives/<int:drive_id>/complete", methods=["PUT"])
def api_admin_complete_drive(drive_id):
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE `test_drive` SET status='已完成' WHERE drive_id=%s AND status='已确认'",
                (drive_id,)
            )
            if cursor.rowcount == 0:
                return error("无法完成该预约")
        conn.commit()
        return success(msg="已完成预约")
    finally:
        conn.close()


# ============================================================
# 评价管理 API（管理员查看/删除用户评价）
# ============================================================

@app.route("/api/admin/reviews")
def api_admin_reviews():
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    kw = request.args.get("kw", "").strip()
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT s.comment_id, s.brand, s.series, s.model,
                    COALESCE(u.username, '') AS username,
                    s.space_score, s.drive_score, s.range_score, s.appearance_score,
                    s.interior_score, s.value_score, s.smart_score,
                    ROUND((s.space_score + s.drive_score + s.range_score + s.appearance_score +
                           s.interior_score + s.value_score + s.smart_score) / 7.0, 1) AS total_score,
                    COALESCE(c.content, '') AS content, c.comment_date
                FROM `score` s
                LEFT JOIN `user` u ON s.user_id = u.user_id
                LEFT JOIN `comment` c ON c.comment_id = s.comment_id
                WHERE s.user_id IS NOT NULL
            """
            params = []
            if kw:
                sql += " AND (s.model LIKE %s OR s.brand LIKE %s OR COALESCE(u.username, '') LIKE %s)"
                params += ["%" + kw + "%", "%" + kw + "%", "%" + kw + "%"]
            sql += " ORDER BY c.comment_date DESC"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return success(data=rows)
    finally:
        conn.close()


@app.route("/api/admin/reviews/<comment_id>", methods=["DELETE"])
def api_admin_delete_review(comment_id):
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM `score` WHERE comment_id=%s", (comment_id,))
            cursor.execute("DELETE FROM `comment` WHERE comment_id=%s", (comment_id,))
        conn.commit()
        return success(msg="已删除该评价")
    finally:
        conn.close()


# ============================================================
# 购车订单 API
# ============================================================

@app.route("/api/order", methods=["POST"])
def api_create_order():
    user, err = require_login()
    if err:
        return jsonify(err), 401

    data = request.get_json(force=True)
    vehicle_id = data.get("vehicle_id", "").strip()
    pay_method = data.get("pay_method", "全款").strip()
    remark = data.get("remark", "").strip()

    if not vehicle_id:
        return error("请选择车辆")

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 查询车辆价格
            cursor.execute("SELECT price FROM `vehicle` WHERE vehicle_id=%s", (vehicle_id,))
            vehicle = cursor.fetchone()
            if not vehicle:
                return error("车辆不存在")

            total_price = vehicle["price"]
            order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4())[:6].upper()}"

            cursor.execute(
                "INSERT INTO `order` (order_id, user_id, vehicle_id, total_price, pay_method, remark) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (order_id, user["user_id"], vehicle_id, total_price, pay_method, remark)
            )
        conn.commit()
        return success(data={"order_id": order_id, "total_price": total_price}, msg="下单成功")
    finally:
        conn.close()


@app.route("/api/my_orders")
def api_my_orders():
    user, err = require_login()
    if err:
        return jsonify(err), 401

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT o.*, v.brand, v.series, v.model, v.image_url, v.price
                FROM `order` o
                LEFT JOIN `vehicle` v ON o.vehicle_id = v.vehicle_id
                WHERE o.user_id = %s
                ORDER BY o.created_at DESC
            """, (user["user_id"],))
            orders = cursor.fetchall()
            return success(data=orders)
    finally:
        conn.close()


@app.route("/api/order/<order_id>/cancel", methods=["PUT"])
def api_cancel_order(order_id):
    user, err = require_login()
    if err:
        return jsonify(err), 401

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            if user["role"] != "admin":
                cursor.execute(
                    "UPDATE `order` SET order_status='已取消' WHERE order_id=%s AND user_id=%s AND order_status='待支付'",
                    (order_id, user["user_id"])
                )
            else:
                cursor.execute(
                    "UPDATE `order` SET order_status='已取消' WHERE order_id=%s AND order_status IN ('待支付','已支付')",
                    (order_id,)
                )
            if cursor.rowcount == 0:
                return error("无法取消该订单")
        conn.commit()
        return success(msg="订单已取消")
    finally:
        conn.close()


@app.route("/api/order/<order_id>/pay", methods=["PUT"])
def api_pay_order(order_id):
    user, err = require_login()
    if err:
        return jsonify(err), 401

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE `order` SET order_status='已支付' WHERE order_id=%s AND user_id=%s AND order_status='待支付'",
                (order_id, user["user_id"])
            )
            if cursor.rowcount == 0:
                return error("无法支付该订单")
        conn.commit()
        return success(msg="支付成功")
    finally:
        conn.close()


@app.route("/api/admin/orders")
def api_admin_orders():
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    status_filter = request.args.get("status", "").strip()

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT o.*, o.order_id as order_no, o.order_status as status,
                    o.pay_method as payment_method, o.total_price * 10000 as price,
                    u.username, u.phone as user_phone,
                    v.brand, v.series, v.model,
                    CONCAT(v.brand, ' ', v.series, ' ', v.model) as car_name
                FROM `order` o
                LEFT JOIN `user` u ON o.user_id = u.user_id
                LEFT JOIN `vehicle` v ON o.vehicle_id = v.vehicle_id
            """
            params = []
            if status_filter:
                sql += " WHERE o.order_status=%s"
                params.append(status_filter)
            sql += " ORDER BY o.created_at DESC"
            cursor.execute(sql, params)
            orders = cursor.fetchall()
            return success(data=orders)
    finally:
        conn.close()


@app.route("/api/admin/orders/<order_id>/deliver", methods=["PUT"])
def api_admin_deliver_order(order_id):
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE `order` SET order_status='已交付' WHERE order_id=%s AND order_status='已支付'",
                (order_id,)
            )
            if cursor.rowcount == 0:
                return error("无法交付该订单")
        conn.commit()
        return success(msg="已确认交付")
    finally:
        conn.close()


# ============================================================
# 售后维修 API
# ============================================================

@app.route("/api/repair", methods=["POST"])
def api_create_repair():
    user, err = require_login()
    if err:
        return jsonify(err), 401

    data = request.get_json(force=True)
    vehicle_id = data.get("vehicle_id", "").strip()
    problem_desc = data.get("problem_desc", "").strip()
    repair_type = data.get("repair_type", "其他").strip()

    if not vehicle_id or not problem_desc:
        return error("请填写完整的报修信息")

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO `repair` (user_id, vehicle_id, problem_desc, repair_type) VALUES (%s, %s, %s, %s)",
                (user["user_id"], vehicle_id, problem_desc, repair_type)
            )
        conn.commit()
        return success(msg="报修提交成功")
    finally:
        conn.close()


@app.route("/api/my_repairs")
def api_my_repairs():
    user, err = require_login()
    if err:
        return jsonify(err), 401

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.*, v.brand, v.series, v.model, v.image_url
                FROM `repair` r
                LEFT JOIN `vehicle` v ON r.vehicle_id = v.vehicle_id
                WHERE r.user_id = %s
                ORDER BY r.created_at DESC
            """, (user["user_id"],))
            repairs = cursor.fetchall()
            return success(data=repairs)
    finally:
        conn.close()


@app.route("/api/admin/repairs")
def api_admin_repairs():
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    status_filter = request.args.get("status", "").strip()

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT r.*, r.repair_id as id,
                    r.repair_type as fault_type, r.problem_desc as description,
                    u.username, u.phone as user_phone,
                    v.brand, v.series, v.model,
                    CONCAT(v.brand, ' ', v.series, ' ', v.model) as car_name
                FROM `repair` r
                LEFT JOIN `user` u ON r.user_id = u.user_id
                LEFT JOIN `vehicle` v ON r.vehicle_id = v.vehicle_id
            """
            params = []
            if status_filter:
                sql += " WHERE r.status=%s"
                params.append(status_filter)
            sql += " ORDER BY r.created_at DESC"
            cursor.execute(sql, params)
            repairs = cursor.fetchall()
            return success(data=repairs)
    finally:
        conn.close()


@app.route("/api/admin/repairs/<int:repair_id>/process", methods=["PUT"])
def api_admin_process_repair(repair_id):
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    data = request.get_json(force=True)
    result = data.get("result", "").strip()

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE `repair` SET status='处理中', result=%s WHERE repair_id=%s AND status='待处理'",
                (result, repair_id)
            )
            if cursor.rowcount == 0:
                return error("无法处理该报修")
        conn.commit()
        return success(msg="已开始处理")
    finally:
        conn.close()


@app.route("/api/admin/repairs/<int:repair_id>/complete", methods=["PUT"])
def api_admin_complete_repair(repair_id):
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    data = request.get_json(force=True)
    result = data.get("result", "").strip()

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            update_sql = "UPDATE `repair` SET status='已完成'"
            params = []
            if result:
                update_sql += ", result=%s"
                params.append(result)
            update_sql += " WHERE repair_id=%s AND status='处理中'"
            params.append(repair_id)
            cursor.execute(update_sql, params)
            if cursor.rowcount == 0:
                return error("无法完成该维修")
        conn.commit()
        return success(msg="维修已完成")
    finally:
        conn.close()


# ============================================================
# 收藏 API
# ============================================================

@app.route("/api/favorite", methods=["POST"])
def api_add_favorite():
    user, err = require_login()
    if err:
        return jsonify(err), 401

    data = request.get_json(force=True)
    vehicle_id = data.get("vehicle_id", "").strip()
    if not vehicle_id:
        return error("请选择车辆")

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "INSERT INTO `favorite` (user_id, vehicle_id) VALUES (%s, %s)",
                    (user["user_id"], vehicle_id)
                )
                conn.commit()
                return success(msg="收藏成功")
            except pymysql.err.IntegrityError:
                return error("已经收藏过了")
    finally:
        conn.close()


@app.route("/api/favorite/<vehicle_id>", methods=["DELETE"])
def api_remove_favorite(vehicle_id):
    user, err = require_login()
    if err:
        return jsonify(err), 401

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM `favorite` WHERE user_id=%s AND vehicle_id=%s",
                (user["user_id"], vehicle_id)
            )
            if cursor.rowcount == 0:
                return error("未收藏该车辆")
        conn.commit()
        return success(msg="已取消收藏")
    finally:
        conn.close()


@app.route("/api/my_favorites")
def api_my_favorites():
    user, err = require_login()
    if err:
        return jsonify(err), 401

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT f.id, f.vehicle_id, f.created_at,
                    v.brand, v.series, v.model, v.type, v.range_cltc, v.price, v.status, v.image_url
                FROM `favorite` f
                LEFT JOIN `vehicle` v ON f.vehicle_id = v.vehicle_id
                WHERE f.user_id = %s
                ORDER BY f.created_at DESC
            """, (user["user_id"],))
            favorites = cursor.fetchall()
            return success(data=favorites)
    finally:
        conn.close()


# ============================================================
# 管理员 - 车辆管理 API
# ============================================================

@app.route("/api/vehicles", methods=["POST"])
def api_add_vehicle():
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    data = request.get_json(force=True)
    vehicle_id = data.get("vehicle_id", "").strip() or data.get("id", "")
    brand = data.get("brand", "").strip()
    series = data.get("series", "").strip()
    model_name = data.get("model", "").strip() or data.get("car_name", "").strip()
    vtype = data.get("type", "纯电").strip()
    range_cltc = data.get("range_cltc", data.get("range", 0))
    price = data.get("price", 0)
    status = data.get("status", "在售").strip()
    image_url = data.get("image_url", "").strip()

    if not brand or not model_name:
        return error("品牌和车型不能为空")

    # 自动补全缺失字段
    if not vehicle_id:
        vehicle_id = "V" + uuid.uuid4().hex[:12].upper()
    if not series:
        series = brand

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO `vehicle` (vehicle_id, brand, series, model, type, range_cltc, price, status, image_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (vehicle_id, brand, series, model_name, vtype, int(float(range_cltc or 0)), float(price or 0), status, image_url))
        conn.commit()
        return success(msg="车辆添加成功", data={"vehicle_id": vehicle_id})
    finally:
        conn.close()


@app.route("/api/vehicles/<vehicle_id>", methods=["PUT"])
def api_update_vehicle(vehicle_id):
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    data = request.get_json(force=True)

    # 前端兼容字段映射
    if "car_name" in data and "model" not in data:
        data["model"] = data["car_name"]
    if "range" in data and "range_cltc" not in data:
        data["range_cltc"] = data["range"]

    fields = []
    params = []
    for key in ["brand", "series", "type", "status", "image_url"]:
        if key in data and data[key] is not None:
            fields.append(f"{key}=%s")
            params.append(data[key])
    if "model" in data and data["model"] is not None:
        fields.append("model=%s")
        params.append(data["model"])
    if "range_cltc" in data and data["range_cltc"] is not None:
        try:
            _rv = int(float(data["range_cltc"]))
        except (ValueError, TypeError):
            return error("续航参数格式不正确")
        fields.append("range_cltc=%s")
        params.append(_rv)
    if "price" in data and data["price"] is not None:
        try:
            _pv = float(data["price"])
        except (ValueError, TypeError):
            return error("价格参数格式不正确")
        fields.append("price=%s")
        params.append(_pv)

    if not fields:
        return error("没有要更新的字段")

    params.append(vehicle_id)
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE `vehicle` SET {', '.join(fields)} WHERE vehicle_id=%s",
                params
            )
            if cursor.rowcount == 0:
                return error("车辆不存在")
        conn.commit()
        return success(msg="车辆信息已更新")
    finally:
        conn.close()


@app.route("/api/vehicles/<vehicle_id>", methods=["DELETE"])
def api_delete_vehicle(vehicle_id):
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM `vehicle` WHERE vehicle_id=%s", (vehicle_id,))
            if cursor.rowcount == 0:
                return error("车辆不存在")
        conn.commit()
        return success(msg="车辆已删除")
    finally:
        conn.close()


# ============================================================
# 管理员 - 数据导入 API
# ============================================================

@app.route("/api/import_data", methods=["POST"])
def api_import_data():
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    data = request.get_json(force=True, silent=True) or {}
    import_type = data.get("type", "").strip()  # vehicle / score / comment

    if import_type == "vehicle":
        return _import_vehicles_api()
    elif import_type == "score":
        return _import_scores_api()
    elif import_type == "comment":
        return _import_comments_api()
    else:
        return error("不支持的导入类型，可选: vehicle, score, comment")


def _import_vehicles_api():
    filepath = os.path.join(DATA_DIR, "车辆基础信息.csv")
    if not os.path.exists(filepath):
        return error("数据文件不存在")

    conn = get_db()
    count = 0
    try:
        with conn.cursor() as cursor:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    vehicle_id = row.get("车辆ID", "").strip()
                    if not vehicle_id:
                        continue
                    brand = row.get("品牌", "").strip()
                    series = row.get("车系", "").strip()
                    model_name = row.get("车型全称", "").strip()
                    range_cltc = row.get("续航CLTC", "0").strip()
                    price = row.get("官方价格_万", "0").strip()
                    try:
                        range_cltc = int(float(range_cltc)) if range_cltc else 0
                    except (ValueError, TypeError):
                        range_cltc = 0
                    try:
                        price = float(price) if price else 0
                    except (ValueError, TypeError):
                        price = 0
                    vtype = "纯电"
                    if model_name:
                        if "插混" in model_name or "PHEV" in model_name or "DM-i" in model_name:
                            vtype = "插电"
                        elif "增程" in model_name or "EREV" in model_name:
                            vtype = "增程"
                    cursor.execute("""
                        INSERT INTO `vehicle` (vehicle_id, brand, series, model, type, range_cltc, price, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE brand=VALUES(brand), series=VALUES(series),
                            model=VALUES(model), type=VALUES(type), range_cltc=VALUES(range_cltc), price=VALUES(price)
                    """, (vehicle_id, brand, series, model_name, vtype, range_cltc, price, "在售"))
                    count += 1
        conn.commit()
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO `data_import_log` (table_name, file_name, import_count, status) VALUES (%s, %s, %s, %s)",
                ("vehicle", "车辆基础信息.csv", count, "成功")
            )
        conn.commit()
        return success(data={"import_count": count}, msg=f"车辆数据导入成功，共 {count} 条")
    finally:
        conn.close()


def _import_scores_api():
    filepath = os.path.join(DATA_DIR, "车型维度评分.csv")
    if not os.path.exists(filepath):
        return error("数据文件不存在")

    conn = get_db()
    count = 0
    try:
        with conn.cursor() as cursor:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    comment_id = row.get("评论ID", "").strip()
                    if not comment_id:
                        continue
                    brand = row.get("品牌", "").strip()
                    series = row.get("车系", "").strip()
                    model_name = row.get("车型", "").strip()

                    def safe_float(val):
                        try:
                            return float(val) if val else 0
                        except (ValueError, TypeError):
                            return 0

                    cursor.execute("""
                        INSERT INTO `score` (comment_id, brand, series, model,
                            space_score, drive_score, range_score, appearance_score,
                            interior_score, value_score, smart_score)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE brand=VALUES(brand), series=VALUES(series), model=VALUES(model),
                            space_score=VALUES(space_score), drive_score=VALUES(drive_score),
                            range_score=VALUES(range_score), appearance_score=VALUES(appearance_score),
                            interior_score=VALUES(interior_score), value_score=VALUES(value_score),
                            smart_score=VALUES(smart_score)
                    """, (comment_id, brand, series, model_name,
                          safe_float(row.get("空间分", "0")),
                          safe_float(row.get("驾驶分", "0")),
                          safe_float(row.get("续航分", "0")),
                          safe_float(row.get("外观分", "0")),
                          safe_float(row.get("内饰分", "0")),
                          safe_float(row.get("性价比分", "0")),
                          safe_float(row.get("智能分", "0"))))
                    count += 1
        conn.commit()
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO `data_import_log` (table_name, file_name, import_count, status) VALUES (%s, %s, %s, %s)",
                ("score", "车型维度评分.csv", count, "成功")
            )
        conn.commit()
        return success(data={"import_count": count}, msg=f"评分数据导入成功，共 {count} 条")
    finally:
        conn.close()


def _import_comments_api():
    filepath = os.path.join(DATA_DIR, "用户评论数据.csv")
    if not os.path.exists(filepath):
        return error("数据文件不存在")

    conn = get_db()
    count = 0
    try:
        with conn.cursor() as cursor:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    comment_id = row.get("评论ID", "").strip()
                    if not comment_id:
                        continue
                    comment_date = row.get("评论时间", "").strip()
                    brand = row.get("品牌", "").strip()
                    series = row.get("车系", "").strip()
                    model_name = row.get("车型", "").strip()
                    content = row.get("评论文本", "").strip()
                    cursor.execute("""
                        INSERT INTO `comment` (comment_id, comment_date, brand, series, model, content)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE comment_date=VALUES(comment_date), brand=VALUES(brand),
                            series=VALUES(series), model=VALUES(model), content=VALUES(content)
                    """, (comment_id, comment_date, brand, series, model_name, content))
                    count += 1
        conn.commit()
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO `data_import_log` (table_name, file_name, import_count, status) VALUES (%s, %s, %s, %s)",
                ("comment", "用户评论数据.csv", count, "成功")
            )
        conn.commit()
        return success(data={"import_count": count}, msg=f"评论数据导入成功，共 {count} 条")
    finally:
        conn.close()


# ============================================================
# 智能推荐 API（参考同源推荐系统项目）
# ============================================================

# 三级兜底评分子查询：车型均分 -> 品牌均分 -> 全局均分
_AVG_SCORE_JOIN = """
    LEFT JOIN (
        SELECT v2.brand,
            ROUND(AVG(s2.space_score+s2.drive_score+s2.range_score+s2.appearance_score
                +s2.interior_score+s2.value_score+s2.smart_score),1) AS brand_avg
        FROM vehicle v2 JOIN score s2 ON v2.model=s2.model GROUP BY v2.brand
    ) b ON v.brand=b.brand
    CROSS JOIN (
        SELECT ROUND(AVG(s3.space_score+s3.drive_score+s3.range_score+s3.appearance_score
            +s3.interior_score+s3.value_score+s3.smart_score),1) AS global_avg
        FROM score s3
    ) g
"""


@app.route("/api/smart_recommend")
def api_smart_recommend():
    """按预算/续航/品牌/偏好排序推荐"""
    max_price = request.args.get("max_price", "").strip()
    min_range = request.args.get("min_range", "").strip()
    brand = request.args.get("brand", "").strip()
    priority = request.args.get("priority", "score").strip()  # score/price/range/space/smart

    conds, args = [], []
    if max_price:
        try:
            _v = float(max_price)
        except ValueError:
            _v = None
        if _v is not None:
            conds.append("v.price<=%s"); args.append(_v)
    if min_range:
        try:
            _v = int(min_range)
        except ValueError:
            _v = None
        if _v is not None:
            conds.append("v.range_cltc>=%s"); args.append(_v)
    if brand:
        conds.append("v.brand=%s"); args.append(brand)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    order_map = {
        "score": "avg_score DESC",
        "price": "v.price ASC",
        "range": "v.range_cltc DESC",
        "space": "space_avg DESC",
        "smart": "smart_avg DESC",
    }
    order_by = order_map.get(priority, "avg_score DESC")

    sql = f"""
        SELECT v.vehicle_id, v.brand, v.series, v.model, v.type, v.range_cltc, v.price, v.status, v.image_url,
            ROUND(COALESCE(AVG(s.space_score+s.drive_score+s.range_score+s.appearance_score
                +s.interior_score+s.value_score+s.smart_score), b.brand_avg, g.global_avg),1) AS avg_score,
            ROUND(AVG(s.space_score),1) AS space_avg,
            ROUND(AVG(s.smart_score),1) AS smart_avg
        FROM vehicle v
        LEFT JOIN score s ON v.model=s.model
        {_AVG_SCORE_JOIN}
        {where}
        GROUP BY v.vehicle_id, v.brand, v.series, v.model, v.type, v.range_cltc, v.price, v.status, v.image_url,
            b.brand_avg, g.global_avg
        ORDER BY {order_by}
        LIMIT 10
    """
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(args))
            rows = cursor.fetchall()
            return success(data=rows, total=len(rows))
    finally:
        conn.close()


@app.route("/api/nl_recommend")
def api_nl_recommend():
    """自然语言推荐：解析用户输入中的预算/续航/品牌/偏好"""
    import re
    text = request.args.get("text", "").strip()
    if not text:
        return error("请输入选车需求")

    max_price, min_range, brand, priority = None, None, None, "score"
    analysis = []

    m = re.search(r"(\d+)\s*万", text)
    if m:
        max_price = float(m.group(1))
        analysis.append(f"预算约{max_price:g}万")

    m = re.search(r"(\d+)\s*(?:km|公里|千米)", text)
    if m:
        min_range = int(m.group(1))
        analysis.append(f"续航≥{min_range}km")

    known_brands = ["比亚迪","蔚来","极氪","小鹏","问界","小米","理想","特斯拉",
                    "宝马","奔驰","奥迪","大众","广汽埃安","零跑","阿维塔","深蓝",
                    "沃尔沃","smart","吉利银河","AITO 问界","AITO"]
    for b in known_brands:
        if b in text:
            brand = b.replace("AITO ", "").strip() or b
            analysis.append(f"偏好品牌：{b}")
            break

    if any(k in text for k in ["性价比","便宜","划算","省钱"]):
        priority = "price"; analysis.append("看重性价比")
    elif any(k in text for k in ["续航","跑长途","长途"]):
        priority = "range"; analysis.append("看重续航")
    elif any(k in text for k in ["空间","家用","大"]):
        priority = "space"; analysis.append("看重空间")
    elif any(k in text for k in ["智能","智驾","科技","辅助驾驶"]):
        priority = "smart"; analysis.append("看重智能")

    conds, args = [], []
    if max_price:
        conds.append("v.price<=%s"); args.append(max_price * 1.1)  # 上浮10%容错
    if min_range:
        conds.append("v.range_cltc>=%s"); args.append(min_range)
    if brand:
        conds.append("v.brand=%s"); args.append(brand)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    order_map = {"score":"avg_score DESC","price":"v.price ASC","range":"v.range_cltc DESC",
                 "space":"space_avg DESC","smart":"smart_avg DESC"}
    sql = f"""
        SELECT v.vehicle_id, v.brand, v.series, v.model, v.type, v.range_cltc, v.price, v.image_url,
            ROUND(COALESCE(AVG(s.space_score+s.drive_score+s.range_score+s.appearance_score
                +s.interior_score+s.value_score+s.smart_score), b.brand_avg, g.global_avg),1) AS avg_score,
            ROUND(AVG(s.space_score),1) AS space_avg,
            ROUND(AVG(s.smart_score),1) AS smart_avg
        FROM vehicle v
        LEFT JOIN score s ON v.model=s.model
        {_AVG_SCORE_JOIN}
        {where}
        GROUP BY v.vehicle_id, v.brand, v.series, v.model, v.type, v.range_cltc, v.price, v.image_url,
            b.brand_avg, g.global_avg
        ORDER BY {order_map.get(priority,'avg_score DESC')}
        LIMIT 8
    """
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(args))
            rows = cursor.fetchall()
            if not rows and max_price:
                # 没结果就放宽价格
                conds2 = [c for c in conds if "price" not in c]
                args2 = [a for c, a in zip(conds, args) if "price" not in c]
                where2 = ("WHERE " + " AND ".join(conds2)) if conds2 else ""
                sql2 = sql.replace(where, where2)
                cursor.execute(sql2, tuple(args2))
                rows = cursor.fetchall()
                analysis.append("（已放宽价格条件）")
            return success(data=rows, analysis="，".join(analysis) if analysis else "综合评分排序")
    finally:
        conn.close()


@app.route("/api/rank")
def api_rank():
    """评分排行榜：评论数>=3 且综合分>=32"""
    sql = """
        SELECT v.brand, v.series, v.model, v.range_cltc, v.price,
            ROUND(AVG(s.space_score+s.drive_score+s.range_score+s.appearance_score
                +s.interior_score+s.value_score+s.smart_score),1) AS avg_score,
            COUNT(s.comment_id) AS cnt
        FROM vehicle v JOIN score s ON v.model=s.model
        GROUP BY v.vehicle_id, v.brand, v.series, v.model, v.range_cltc, v.price
        HAVING cnt>=3 AND avg_score>=32
        ORDER BY avg_score DESC LIMIT 15
    """
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return success(data=cursor.fetchall())
    finally:
        conn.close()


# ============================================================
# 统计 API
# ============================================================

@app.route("/api/stats/brand")
@app.route("/api/stats/brands")
def api_stats_brand():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT brand, COUNT(*) as count FROM `vehicle` GROUP BY brand ORDER BY count DESC")
            data = cursor.fetchall()
            return success(data=data)
    finally:
        conn.close()


@app.route("/api/stats/price")
@app.route("/api/stats/price_distribution")
def api_stats_price():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    CASE
                        WHEN price < 10 THEN '10万以下'
                        WHEN price < 15 THEN '10-15万'
                        WHEN price < 20 THEN '15-20万'
                        WHEN price < 30 THEN '20-30万'
                        WHEN price < 50 THEN '30-50万'
                        ELSE '50万以上'
                    END as price_range,
                    COUNT(*) as count
                FROM `vehicle`
                GROUP BY price_range
                ORDER BY MIN(price)
            """)
            data = cursor.fetchall()
            return success(data=data)
    finally:
        conn.close()


@app.route("/api/stats/range")
@app.route("/api/stats/range_distribution")
def api_stats_range():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    CASE
                        WHEN range_cltc < 300 THEN '300km以下'
                        WHEN range_cltc < 400 THEN '300-400km'
                        WHEN range_cltc < 500 THEN '400-500km'
                        WHEN range_cltc < 600 THEN '500-600km'
                        WHEN range_cltc < 700 THEN '600-700km'
                        ELSE '700km以上'
                    END as range_range,
                    COUNT(*) as count
                FROM `vehicle`
                GROUP BY range_range
                ORDER BY MIN(range_cltc)
            """)
            data = cursor.fetchall()
            return success(data=data)
    finally:
        conn.close()


@app.route("/api/stats/type")
@app.route("/api/stats/types")
def api_stats_type():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT type, COUNT(*) as count FROM `vehicle` GROUP BY type ORDER BY count DESC")
            data = cursor.fetchall()
            return success(data=data)
    finally:
        conn.close()


@app.route("/api/stats/score")
@app.route("/api/stats/radar")
def api_stats_score():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    ROUND(AVG(space_score), 2) as avg_space,
                    ROUND(AVG(drive_score), 2) as avg_drive,
                    ROUND(AVG(range_score), 2) as avg_range,
                    ROUND(AVG(appearance_score), 2) as avg_appearance,
                    ROUND(AVG(interior_score), 2) as avg_interior,
                    ROUND(AVG(value_score), 2) as avg_value,
                    ROUND(AVG(smart_score), 2) as avg_smart
                FROM `score`
            """)
            data = cursor.fetchone()
            return success(data=data)
    finally:
        conn.close()


@app.route("/api/stats/brand_score")
@app.route("/api/stats/ranking")
def api_stats_brand_score():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT brand,
                    ROUND(AVG((space_score + drive_score + range_score + appearance_score + interior_score + value_score + smart_score) / 7), 2) as avg_score,
                    COUNT(*) as score_count
                FROM `score`
                GROUP BY brand
                ORDER BY avg_score DESC
                LIMIT 20
            """)
            data = cursor.fetchall()
            return success(data=data)
    finally:
        conn.close()


@app.route("/api/stats/overview")
def api_stats_overview():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            stats = {}

            cursor.execute("SELECT COUNT(*) as cnt FROM `vehicle`")
            stats["vehicle_count"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(DISTINCT brand) as cnt FROM `vehicle`")
            stats["brand_count"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM `test_drive`")
            stats["drive_count"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM `order`")
            stats["order_count"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM `repair`")
            stats["repair_count"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM `user`")
            stats["user_count"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM `comment`")
            stats["comment_count"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM `score`")
            stats["score_count"] = cursor.fetchone()["cnt"]

            return success(data=stats)
    finally:
        conn.close()


# ============================================================
# 前端模板兼容路由（与 admin.html / stats.html 调用对齐）
# ============================================================

@app.route("/api/test_drive/<int:drive_id>/confirm", methods=["PUT"])
def api_confirm_drive_alias(drive_id):
    """兼容 admin.html 调用路径，转发到管理员确认逻辑"""
    return api_admin_confirm_drive(drive_id)


@app.route("/api/repair/<int:repair_id>/resolve", methods=["PUT"])
def api_resolve_repair_alias(repair_id):
    """兼容 admin.html 调用路径：标记维修为处理中"""
    user, err = require_admin()
    if err:
        return jsonify(err), 403
    data = request.get_json(silent=True) or {}
    result = data.get("result", "已受理处理中").strip()
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE `repair` SET status='处理中', result=%s WHERE repair_id=%s AND status='待处理'",
                (result, repair_id)
            )
            if cursor.rowcount == 0:
                return error("无法处理该报修")
        conn.commit()
        return success(msg="已标记处理")
    finally:
        conn.close()


def _parse_upload_file(filename, raw):
    """把上传的 CSV / JSON / Excel 文件解析为「行字典」列表，供后续识别与写库"""
    import io
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".csv", ""):
        text = raw.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        return [dict(r) for r in reader
                if any(v is not None and str(v).strip() for v in r.values())]
    if ext == ".json":
        data = json.loads(raw.decode("utf-8", errors="replace"))
        if isinstance(data, dict):
            data = data.get("data") or data.get("list") or data.get("items") or data
        if not isinstance(data, list):
            raise ValueError("JSON 内容应为数组")
        return [dict(r) for r in data]
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header = next(it, None)
        if not header:
            wb.close()
            raise ValueError("Excel 表格为空")
        header = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(header)]
        out = []
        for vals in it:
            out.append({header[i]: (vals[i] if i < len(vals) else None)
                        for i in range(len(header))})
        wb.close()
        return out
    raise ValueError("仅支持 CSV / JSON / Excel 格式的文件")


def _field(r, *keys, default=""):
    for k in keys:
        v = r.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _field_num(r, *keys):
    try:
        return float(_field(r, *keys, default="0"))
    except (ValueError, TypeError):
        return 0


def _write_import(kind, rows, filename):
    """按识别出的类型把行数据写入对应数据表，返回成功写入条数"""
    conn = get_db()
    count = 0
    imp_err = None
    try:
        with conn.cursor() as cursor:
            for r in rows:
                if kind == "vehicle":
                    vid = _field(r, "车辆ID", "id")
                    if not vid:
                        continue
                    model = _field(r, "车型全称", "车型", "model")
                    vtype = "纯电"
                    upper = model.upper()
                    if "PHEV" in upper or "DM" in upper or "插混" in model:
                        vtype = "插电"
                    elif "增程" in model or "EREV" in upper:
                        vtype = "增程"
                    cursor.execute(
                        "INSERT INTO `vehicle` (vehicle_id, brand, series, model, type, "
                        "range_cltc, price, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE brand=VALUES(brand), series=VALUES(series), "
                        "model=VALUES(model), type=VALUES(type), range_cltc=VALUES(range_cltc), "
                        "price=VALUES(price)",
                        (vid, _field(r, "品牌"), _field(r, "车系"), model, vtype,
                         int(_field_num(r, "续航CLTC", "续航", "range_cltc")),
                         float(_field_num(r, "官方价格_万", "价格")), "在售"))
                elif kind == "score":
                    cid = _field(r, "评论ID")
                    if not cid:
                        continue
                    cursor.execute(
                        "INSERT INTO `score` (comment_id, brand, series, model, space_score, "
                        "drive_score, range_score, appearance_score, interior_score, "
                        "value_score, smart_score) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE brand=VALUES(brand), series=VALUES(series), "
                        "model=VALUES(model), space_score=VALUES(space_score), "
                        "drive_score=VALUES(drive_score), range_score=VALUES(range_score), "
                        "appearance_score=VALUES(appearance_score), "
                        "interior_score=VALUES(interior_score), value_score=VALUES(value_score), "
                        "smart_score=VALUES(smart_score)",
                        (cid, _field(r, "品牌"), _field(r, "车系"), _field(r, "车型", "model"),
                         _field_num(r, "空间分"), _field_num(r, "驾驶分"), _field_num(r, "续航分"),
                         _field_num(r, "外观分"), _field_num(r, "内饰分"),
                         _field_num(r, "性价比分"), _field_num(r, "智能分")))
                elif kind == "comment":
                    cid = _field(r, "评论ID")
                    if not cid:
                        continue
                    cursor.execute(
                        "INSERT INTO `comment` (comment_id, comment_date, brand, series, "
                        "model, content) VALUES (%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE comment_date=VALUES(comment_date), "
                        "brand=VALUES(brand), series=VALUES(series), model=VALUES(model), "
                        "content=VALUES(content)",
                        (cid, _field(r, "评论时间", "日期"), _field(r, "品牌"), _field(r, "车系"),
                         _field(r, "车型", "model"), _field(r, "评论文本", "内容")))
                count += 1
        conn.commit()
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO `data_import_log` (table_name, file_name, import_count, status) "
                "VALUES (%s,%s,%s,%s)", (kind, filename, count, "成功"))
        conn.commit()
    except Exception as e:
        imp_err = str(e)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()
    if imp_err:
        raise Exception(imp_err)
    return count


@app.route("/api/import", methods=["POST"])
def api_import_upload():
    """统一数据导入：支持粘贴 JSON，或上传 CSV / Excel 文件，真正解析入库（替换原占位实现）"""
    user, err = require_admin()
    if err:
        return jsonify(err), 403

    # JSON 形式（粘贴）转发原类型化导入
    if request.content_type and "application/json" in request.content_type:
        return api_import_data()

    file = request.files.get("file")
    if not file or not file.filename:
        return error("请选择要导入的文件")
    if not file.filename.lower().endswith((".csv", ".json", ".xlsx", ".xlsm")):
        return error("仅支持 .csv / .json / .xlsx 文件")

    raw = file.read()
    if not raw:
        return error("文件内容为空")

    try:
        rows = _parse_upload_file(file.filename, raw)
    except Exception as e:
        return error("文件解析失败：" + str(e))
    if not rows:
        return error("文件中没有可导出的数据")

    coltext = " ".join(str(k) for k in rows[0].keys())
    if "车辆" in coltext and ("车型" in coltext or "车系" in coltext):
        kind = "vehicle"
    elif "评论" in coltext and ("空间分" in coltext or "驾驶分" in coltext):
        kind = "score"
    elif "评论" in coltext and ("评论文本" in coltext or "文本" in coltext):
        kind = "comment"
    else:
        return error("无法识别数据类型，请使用标准的 车辆 / 评分 / 评论 格式")

    try:
        count = _write_import(kind, rows, file.filename)
    except Exception as e:
        return error("写入数据库失败：" + str(e))
    return success(data={"import_count": count}, msg="%s 数据导入成功，共 %d 条" % (kind, count))


# ============================================================
# 全局统一异常处理：任何未捕获异常都返回友好 JSON/页面，避免裸 500
# ============================================================
@app.errorhandler(Exception)
def handle_unexpected_error(e):
    # HTTP 异常（如 400 请求格式错误、405 方法不允许）按其自身状态码返回，避免误报 500
    if isinstance(e, HTTPException):
        code = e.code or 500
        if code < 500:
            msg = {400: "请求格式不正确", 405: "请求方法不被允许"}.get(code, e.description)
            if request.path.startswith("/api/"):
                return jsonify({"code": code, "success": False, "msg": msg}), code
            return _render_error_page(msg), code
    app.logger.error("Unhandled error: %s", e)
    if request.path.startswith("/api/"):
        return jsonify({"code": 500, "success": False, "msg": "服务内部错误，请稍后重试"}), 500
    return _render_error_page("服务内部错误，请稍后重试"), 500


@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"code": 404, "success": False, "msg": "接口不存在"}), 404
    return _render_error_page("您访问的页面不存在"), 404


def _render_error_page(msg):
    return (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>出错了</title>"
        "<body style='font-family:system-ui;text-align:center;padding-top:12vh;color:#333'>"
        "<h1 style='color:#e14e2b'>系统提示</h1><p style='font-size:18px'>%s</p>"
        "<a href='/'>返回首页</a></body></html>" % msg
    )


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
