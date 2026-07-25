# -*- coding: utf-8 -*-
# ============================================================
# 聚宽平台策略代码 - V1 双均线基础版
# 策略思路：短期均线上穿长期均线买入，下穿卖出
# 适用场景：趋势行情
# ============================================================

# === 导入聚宽API ===
# 在聚宽平台中以下函数由平台自动提供：
# initialize(context), before_trading_start(context, data),
# handle_data(context, data), after_trading_end(context, data)

def initialize(context):
    """初始化策略参数"""
    # === 基础设置 ===
    set_benchmark('000300.XSHG')        # 基准：沪深300
    set_option('use_real_price', True)  # 使用真实价格
    set_option('avoid_future_data', True)  # 避免未来数据
    set_order_cost(OrderCost(
        close_tax=0.001,           # 卖出印花税 0.1%
        open_commission=0.0003,    # 买入佣金 0.03%
        close_commission=0.0003,   # 卖出佣金 0.03%
        min_commission=5           # 最低佣金 5元
    ), type='stock')
    
    # === 策略参数 ===
    context.stock = '300750.XSHE'  # 标的：宁德时代
    context.short_window = 5        # 短期均线周期
    context.long_window = 20        # 长期均线周期
    context.position_ratio = 0.95  # 仓位比例
    
    log.info('策略V1初始化完成 | 标的:%s MA%d/MA%d' % (
        context.stock, context.short_window, context.long_window))


def before_trading_start(context, data):
    """盘前处理"""
    pass


def handle_data(context, data):
    """核心交易逻辑 - 每日执行"""
    stock = context.stock
    
    # 获取历史价格数据
    prices = history(context.long_window + 2, '1d', 'close', stock)
    
    # 计算移动平均线
    ma_short = prices[-context.short_window:].mean()
    ma_long = prices[-context.long_window:].mean()
    ma_short_prev = prices[-context.short_window-1:-1].mean()
    ma_long_prev = prices[-context.long_window-1:-1].mean()
    
    # 获取当前持仓
    current_position = context.portfolio.positions.get(stock, None)
    holds = current_position.total_amount if current_position else 0
    
    # === 交易信号 ===
    # 金叉：短期均线从下方上穿长期均线
    golden_cross = (ma_short_prev <= ma_long_prev) and (ma_short > ma_long)
    # 死叉：短期均线从上方下穿长期均线
    death_cross = (ma_short_prev >= ma_long_prev) and (ma_short < ma_long)
    
    # === 执行交易 ===
    if golden_cross and holds == 0:
        # 买入信号：金叉且空仓
        cash = context.portfolio.total_value * context.position_ratio
        current_price = data[stock].close
        shares = int(cash / current_price / 100) * 100  # 整手买入
        if shares > 0:
            order(stock, shares)
            log.info('【买入信号-金叉】MA%d=%.2f上穿MA%d=%.2f | 买入%d股@%.2f' % (
                context.short_window, ma_short, 
                context.long_window, ma_long, shares, current_price))
    
    elif death_cross and holds > 0:
        # 卖出信号：死叉且持仓
        order_target(stock, 0)
        current_price = data[stock].close
        log.info('【卖出信号-死叉】MA%d=%.2f下穿MA%d=%.2f | 清仓@%.2f' % (
            context.short_window, ma_short, 
            context.long_window, ma_long, current_price))


def after_trading_end(context, data):
    """盘后处理"""
    pass


# ============================================================
# V1策略回测结果（宁德时代 2025-07 ~ 2026-07）
# 总收益: +1.02%
# 交易次数: 8笔
# 胜率: 25%
# 最大回撤: -22.31%
# 问题分析: 频繁假信号导致大量无效交易，胜率过低
# ============================================================
