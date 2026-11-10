# -*- coding: utf-8 -*-
"""
新能源汽车综合管理系统 - 数据库初始化脚本
功能：创建数据库、建表、导入CSV数据、创建默认管理员账号
"""

import pymysql
import csv
import os
import hashlib
from db_config import DB_CONFIG, DATA_DIR


def get_connection(use_db=True):
    """获取数据库连接"""
    config = DB_CONFIG.copy()
    if not use_db:
        config.pop("database", None)
    return pymysql.connect(**config)


def create_database():
    """创建数据库"""
    conn = get_connection(use_db=False)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "CREATE DATABASE IF NOT EXISTS ev_management "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        print("[OK] 数据库 ev_management 创建成功")
    finally:
        conn.close()


def create_tables():
    """创建所有表"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 用户表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `user` (
                    user_id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL,
                    role VARCHAR(20) DEFAULT 'user',
                    phone VARCHAR(20),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # 2. 车辆表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `vehicle` (
                    vehicle_id VARCHAR(64) PRIMARY KEY,
                    brand VARCHAR(50) NOT NULL,
                    series VARCHAR(100) NOT NULL,
                    model VARCHAR(255) NOT NULL,
                    type VARCHAR(20) DEFAULT '纯电',
                    range_cltc INT DEFAULT 0,
                    price FLOAT DEFAULT 0,
                    status VARCHAR(20) DEFAULT '在售',
                    image_url VARCHAR(500),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # 3. 评分表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `score` (
                    comment_id VARCHAR(64) PRIMARY KEY,
                    brand VARCHAR(50),
                    series VARCHAR(100),
                    model VARCHAR(255),
                    space_score FLOAT DEFAULT 0,
                    drive_score FLOAT DEFAULT 0,
                    range_score FLOAT DEFAULT 0,
                    appearance_score FLOAT DEFAULT 0,
                    interior_score FLOAT DEFAULT 0,
                    value_score FLOAT DEFAULT 0,
                    smart_score FLOAT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # 4. 评论表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `comment` (
                    comment_id VARCHAR(64) PRIMARY KEY,
                    comment_date VARCHAR(20),
                    brand VARCHAR(50),
                    series VARCHAR(100),
                    model VARCHAR(255),
                    content TEXT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # 5. 试驾预约表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `test_drive` (
                    drive_id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    vehicle_id VARCHAR(64) NOT NULL,
                    drive_date DATE NOT NULL,
                    drive_time VARCHAR(20) NOT NULL,
                    contact_phone VARCHAR(20),
                    status VARCHAR(20) DEFAULT '待确认',
                    remark TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES `user`(user_id),
                    FOREIGN KEY (vehicle_id) REFERENCES `vehicle`(vehicle_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # 6. 购车订单表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `order` (
                    order_id VARCHAR(64) PRIMARY KEY,
                    user_id INT NOT NULL,
                    vehicle_id VARCHAR(64) NOT NULL,
                    total_price FLOAT NOT NULL,
                    order_status VARCHAR(20) DEFAULT '待支付',
                    pay_method VARCHAR(20),
                    remark TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES `user`(user_id),
                    FOREIGN KEY (vehicle_id) REFERENCES `vehicle`(vehicle_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # 7. 售后维修表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `repair` (
                    repair_id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    vehicle_id VARCHAR(64) NOT NULL,
                    problem_desc TEXT NOT NULL,
                    repair_type VARCHAR(50),
                    status VARCHAR(20) DEFAULT '待处理',
                    result TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES `user`(user_id),
                    FOREIGN KEY (vehicle_id) REFERENCES `vehicle`(vehicle_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # 8. 收藏表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `favorite` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    vehicle_id VARCHAR(64) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY (user_id, vehicle_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # 9. 数据导入日志表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `data_import_log` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    table_name VARCHAR(50),
                    file_name VARCHAR(200),
                    import_count INT DEFAULT 0,
                    status VARCHAR(20) DEFAULT '成功',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

        conn.commit()
        print("[OK] 所有表创建成功")
    finally:
        conn.close()


def hash_password(password, username):
    """密码加密：sha256 + 用户名作为盐"""
    salt = username
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def create_admin():
    """创建默认管理员账号"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            pwd = hash_password("admin123", "admin")
            cursor.execute(
                "INSERT IGNORE INTO `user` (username, password, role) VALUES (%s, %s, %s)",
                ("admin", pwd, "admin")
            )
        conn.commit()
        print("[OK] 默认管理员账号创建成功 (admin / admin123)")
    finally:
        conn.close()


def import_vehicles():
    """从 CSV 导入车辆数据"""
    filepath = os.path.join(DATA_DIR, "车辆基础信息.csv")
    if not os.path.exists(filepath):
        print(f"[WARN] 文件不存在: {filepath}")
        return 0

    conn = get_connection()
    count = 0
    try:
        with conn.cursor() as cursor:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    vehicle_id = row.get("车辆ID", "").strip()
                    brand = row.get("品牌", "").strip()
                    series = row.get("车系", "").strip()
                    model_name = row.get("车型全称", "").strip()
                    range_cltc = row.get("续航CLTC", "0").strip()
                    price = row.get("官方价格_万", "0").strip()

                    if not vehicle_id:
                        continue

                    # 清理数值字段
                    try:
                        range_cltc = int(float(range_cltc)) if range_cltc else 0
                    except (ValueError, TypeError):
                        range_cltc = 0

                    try:
                        price = float(price) if price else 0
                    except (ValueError, TypeError):
                        price = 0

                    # 根据车型全称推断类型
                    vtype = "纯电"
                    if model_name:
                        if "插混" in model_name or "PHEV" in model_name or "DM-i" in model_name or "DM-p" in model_name:
                            vtype = "插电"
                        elif "增程" in model_name or "EREV" in model_name:
                            vtype = "增程"

                    cursor.execute("""
                        INSERT INTO `vehicle` (vehicle_id, brand, series, model, type, range_cltc, price, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            brand=VALUES(brand), series=VALUES(series), model=VALUES(model),
                            type=VALUES(type), range_cltc=VALUES(range_cltc), price=VALUES(price)
                    """, (vehicle_id, brand, series, model_name, vtype, range_cltc, price, "在售"))
                    count += 1

        conn.commit()
        print(f"[OK] 车辆数据导入成功，共 {count} 条")

        # 记录导入日志
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO `data_import_log` (table_name, file_name, import_count, status) VALUES (%s, %s, %s, %s)",
                ("vehicle", "车辆基础信息.csv", count, "成功")
            )
        conn.commit()
    finally:
        conn.close()

    return count


def import_scores():
    """从 CSV 导入评分数据"""
    filepath = os.path.join(DATA_DIR, "车型维度评分.csv")
    if not os.path.exists(filepath):
        print(f"[WARN] 文件不存在: {filepath}")
        return 0

    conn = get_connection()
    count = 0
    try:
        with conn.cursor() as cursor:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    comment_id = row.get("评论ID", "").strip()
                    brand = row.get("品牌", "").strip()
                    series = row.get("车系", "").strip()
                    model_name = row.get("车型", "").strip()

                    if not comment_id:
                        continue

                    def safe_float(val):
                        try:
                            return float(val) if val else 0
                        except (ValueError, TypeError):
                            return 0

                    space_score = safe_float(row.get("空间分", "0"))
                    drive_score = safe_float(row.get("驾驶分", "0"))
                    range_score = safe_float(row.get("续航分", "0"))
                    appearance_score = safe_float(row.get("外观分", "0"))
                    interior_score = safe_float(row.get("内饰分", "0"))
                    value_score = safe_float(row.get("性价比分", "0"))
                    smart_score = safe_float(row.get("智能分", "0"))

                    cursor.execute("""
                        INSERT INTO `score` (comment_id, brand, series, model,
                            space_score, drive_score, range_score, appearance_score,
                            interior_score, value_score, smart_score)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            brand=VALUES(brand), series=VALUES(series), model=VALUES(model),
                            space_score=VALUES(space_score), drive_score=VALUES(drive_score),
                            range_score=VALUES(range_score), appearance_score=VALUES(appearance_score),
                            interior_score=VALUES(interior_score), value_score=VALUES(value_score),
                            smart_score=VALUES(smart_score)
                    """, (comment_id, brand, series, model_name,
                          space_score, drive_score, range_score, appearance_score,
                          interior_score, value_score, smart_score))
                    count += 1

        conn.commit()
        print(f"[OK] 评分数据导入成功，共 {count} 条")

        # 记录导入日志
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO `data_import_log` (table_name, file_name, import_count, status) VALUES (%s, %s, %s, %s)",
                ("score", "车型维度评分.csv", count, "成功")
            )
        conn.commit()
    finally:
        conn.close()

    return count


def import_comments():
    """从 CSV 导入评论数据"""
    filepath = os.path.join(DATA_DIR, "用户评论数据.csv")
    if not os.path.exists(filepath):
        print(f"[WARN] 文件不存在: {filepath}")
        return 0

    conn = get_connection()
    count = 0
    try:
        with conn.cursor() as cursor:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    comment_id = row.get("评论ID", "").strip()
                    comment_date = row.get("评论时间", "").strip()
                    brand = row.get("品牌", "").strip()
                    series = row.get("车系", "").strip()
                    model_name = row.get("车型", "").strip()
                    content = row.get("评论文本", "").strip()

                    if not comment_id:
                        continue

                    cursor.execute("""
                        INSERT INTO `comment` (comment_id, comment_date, brand, series, model, content)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            comment_date=VALUES(comment_date), brand=VALUES(brand),
                            series=VALUES(series), model=VALUES(model), content=VALUES(content)
                    """, (comment_id, comment_date, brand, series, model_name, content))
                    count += 1

        conn.commit()
        print(f"[OK] 评论数据导入成功，共 {count} 条")

        # 记录导入日志
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO `data_import_log` (table_name, file_name, import_count, status) VALUES (%s, %s, %s, %s)",
                ("comment", "用户评论数据.csv", count, "成功")
            )
        conn.commit()
    finally:
        conn.close()

    return count


def main():
    print("=" * 50)
    print("新能源汽车综合管理系统 - 数据库初始化")
    print("=" * 50)

    # 1. 创建数据库
    create_database()

    # 2. 创建所有表
    create_tables()

    # 3. 创建默认管理员
    create_admin()

    # 4. 导入CSV数据
    import_vehicles()
    import_scores()
    import_comments()

    print("=" * 50)
    print("数据库初始化完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
