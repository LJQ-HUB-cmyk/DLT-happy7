# -*- coding: utf-8 -*-
"""
数据新鲜度校验 — 按北京时间判断开奖数据是否已经更新。

大乐透每周一/三/六 21:25 开奖，数据源通常在 21:40 前更新。
GitHub Actions 的定时任务可能延迟数小时，因此不能只依赖 cron 时间，
必须在发送邮件 / 生成预测前用真实时间校验数据是否已跟上开奖节奏。
"""

from datetime import datetime, timezone, timedelta

BJ_TZ = timezone(timedelta(hours=8))
DRAW_WEEKDAYS = {0, 2, 5}          # 周一 / 周三 / 周六
DRAW_READY_AT = (21, 40)           # 开奖 21:25，留 15 分钟给数据源
LAST_UPDATED_WARN_HOURS = 48


def now_bj():
    """当前北京时间（不依赖运行机器的时区设置）。"""
    return datetime.now(BJ_TZ)


def parse_date(value):
    """把 'YYYY-MM-DD' 解析为 date，失败返回 None。"""
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def expected_latest_draw_date(now=None):
    """返回当前时刻（北京时间）理应已经开奖并可查到数据的最新开奖日。"""
    now = now or now_bj()
    candidate = now.date()
    if not (candidate.weekday() in DRAW_WEEKDAYS and (now.hour, now.minute) >= DRAW_READY_AT):
        candidate -= timedelta(days=1)
        while candidate.weekday() not in DRAW_WEEKDAYS:
            candidate -= timedelta(days=1)
    return candidate


def check_freshness(lottery_history, now=None):
    """校验 lottery_history 相对北京时间是否新鲜。

    返回 (errors, warnings)：
      - errors 表示数据已过期/未更新，调用方应拒绝发送邮件或生成预测；
      - warnings 仅提示。
    """
    now = now or now_bj()
    errors, warnings = [], []

    if not lottery_history or not lottery_history.get("data"):
        return errors, warnings

    latest = lottery_history["data"][0]
    latest_date = parse_date(latest.get("date"))
    if latest_date is None:
        errors.append(
            f"最新开奖日期格式异常（{latest.get('date')!r}），无法判断数据新鲜度"
        )
    else:
        expected = expected_latest_draw_date(now)
        if latest_date < expected:
            errors.append(
                f"开奖数据未更新：北京时间 {now:%Y-%m-%d %H:%M} 应已有 {expected} 的开奖数据，"
                f"实际最新为第 {latest.get('period')} 期（{latest.get('date')}）"
            )

    next_draw = lottery_history.get("next_draw") or {}
    next_date = parse_date(next_draw.get("next_date"))
    if next_date is not None and next_date < now.date():
        errors.append(
            f"数据已过期：下期开奖日 {next_date} 已过（今天 {now.date()}），"
            f"第 {next_draw.get('next_period', '')} 期的预测已失效"
        )

    last_updated = lottery_history.get("last_updated")
    if last_updated:
        try:
            ts = datetime.strptime(
                str(last_updated), "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            age_hours = (now - ts).total_seconds() / 3600
            if age_hours > LAST_UPDATED_WARN_HOURS:
                warnings.append(
                    f"数据已 {age_hours:.0f} 小时未更新（last_updated={last_updated}）"
                )
        except Exception:
            pass

    return errors, warnings
