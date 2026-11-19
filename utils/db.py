"""MySQL 数据库访问：用于测试数据校验。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor

from utils.config_loader import get_config

ORDER_POLICY_SCHEMA = "mth_insure_core"


@contextmanager
def connect() -> Iterator[pymysql.connections.Connection]:
    """按当前环境的 db 配置建立连接，退出时自动关闭。"""
    cfg = get_config().db
    if not cfg:
        raise RuntimeError("当前环境未配置数据库连接信息")
    conn = pymysql.connect(
        host=cfg.get("host", "127.0.0.1"),
        port=int(cfg.get("port", 3306)),
        user=cfg.get("user", "root"),
        password=cfg.get("password", ""),
        database=cfg.get("database", ""),
        charset=cfg.get("charset", "utf8mb4"),
        cursorclass=DictCursor,
    )
    try:
        yield conn
    finally:
        conn.close()


def query_all(sql: str, args: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    """查询多行，返回字典列表。"""
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(sql, args)
        return list(cursor.fetchall())


def query_one(sql: str, args: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    """查询单行，返回字典；无结果时返回 None。"""
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchone()


def execute(sql: str, args: tuple[Any, ...] | None = None) -> int:
    """执行写操作并提交，返回影响行数。"""
    with connect() as conn, conn.cursor() as cursor:
        rows = cursor.execute(sql, args)
        conn.commit()
        return rows


def order_policy_table(order_no: str) -> str:
    """订单投保数据分 10 张表（insure_order_policy_0 ~ 9），按订单号末位定位。"""
    order_no = (order_no or "").strip()
    if not order_no or not order_no[-1].isdigit():
        raise ValueError(f"订单号不合法：{order_no!r}")
    return f"{ORDER_POLICY_SCHEMA}.insure_order_policy_{order_no[-1]}"


def query_order_policy(order_no: str, columns: str = "*") -> dict[str, Any] | None:
    """按订单号在对应分表中查询一条投保数据。"""
    return query_one(
        f"SELECT {columns} FROM {order_policy_table(order_no)} WHERE order_no = %s LIMIT 1",
        (order_no,),
    )


def get_order_share_code(order_no: str) -> str:
    """查询订单的 share_code，无记录时返回空串。"""
    row = query_order_policy(order_no, columns="share_code")
    return (row or {}).get("share_code") or ""
