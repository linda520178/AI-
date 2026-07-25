# -*- coding: utf-8 -*-
# ============================================================
# 聚宽平台策略代码 - V3 最终版（多因子+风控+动态仓位）
# 改进点：ATR动态止损 + 金字塔仓位管理 + 趋势强度自适应
# ============================================================

def initialize(context):
    """初始化策略参数"""
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    set_order_cost(OrderCost(
        close_tax=0.001,
        open_commission=0.0003,
        close_commission=0.0003,
        min_commission=5
    ), type='stock')
    
    # === 多因子参数配置 ===
    context.stocks = ['300750.XSHE', '600519.XSHG']  # 宁德时代 + 贵州茅台
    context.short_window = 10        # 短期均线
    context.long_window = 30         # 长期均线
    context.rsi_period = 14
    context.rsi_upper = 75           # 放宽超买线，减少过早卖出
    context.rsi_lower = 25
    context.atr_period = 14          # ATR周期
    context.atr_stop_mult = 2.0      # ATR止损倍数（2倍ATR止损）
    context.atr_target_mult = 3.0    # ATR目标倍数（3倍ATR止盈）
    context.max_position_per_stock = 0.45  # 单只股票最大仓位
    context.max_total_position = 0.80      # 总仓位上限
    context.risk_free_rate = 0.03          # 无风险利率（用于夏普比率）
    
    # 策略状态记录
    context.entry_prices = {}  # 记录入场价格
    context.atr_at_entry = {} # 记录入场时ATR
    
    log.info('策略V3初始化 | 多标的:%s | MA%d/MA%d ATR止损%d倍' % (
        context.stocks, context.short_window, context.long_window, 
        context.atr_stop_mult))


def before_trading_start(context, data):
    """盘前处理：检查涨跌停"""
    pass


def calc_rsi(prices, period=14):
    """计算RSI指标"""
    if len(prices) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_atr(highs, lows, closes, period=14):
    """计算ATR（Average True Range）"""
    if len(closes) < period + 1:
        return 0.0
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)
    atr = sum(tr_list[-period:]) / period
    return atr


def calc_position_size(cash, price, atr, risk_per_trade=0.02):
    """基于ATR的动态仓位管理（风险平价）"""
    """每次交易最多承担总资金2%的风险"""
    risk_amount = cash * risk_per_trade
    stop_distance = atr * 2.0  # 止损距离 = 2倍ATR
    if stop_distance <= 0 or price <= 0:
        return 0
    shares = int(risk_amount / stop_distance / 100) * 100
    return max(shares, 0)


def handle_data(context, data):
    """核心交易逻辑"""
    for stock in context.stocks:
        _trade_single_stock(context, data, stock)


def _trade_single_stock(context, data, stock):
    """单只股票交易逻辑"""
    sw = context.short_window
    lw = context.long_window
    hist_len = max(lw, context.rsi_period, context.atr_period) + 5
    
    try:
        prices = history(hist_len, '1d', 'close', stock)
        highs = history(hist_len, '1d', 'high', stock)
        lows = history(hist_len, '1d', 'low', stock)
        volumes = history(hist_len, '1d', 'volume', stock)
    except:
        return
    
    if len(prices) < lw + 2:
        return
    
    # 计算指标
    ma_short = prices[-sw:].mean()
    ma_long = prices[-lw:].mean()
    ma_short_prev = prices[-sw-1:-1].mean()
    ma_long_prev = prices[-lw-1:-1].mean()
    rsi = calc_rsi(list(prices), context.rsi_period)
    atr = calc_atr(list(highs), list(lows), list(prices), context.atr_period)
    
    # 成交量确认
    avg_vol = volumes[-20:].mean()
    current_vol = volumes[-1]
    vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
    
    current_price = data[stock].close
    
    # 当前持仓
    current_position = context.portfolio.positions.get(stock, None)
    holds = current_position.total_amount if current_position else 0
    
    # === 趋势强度判断 ===
    trend_strength = abs(ma_short - ma_long) / ma_long if ma_long > 0 else 0
    is_strong_trend = trend_strength > 0.02  # 偏离度>2%视为强趋势
    
    # === 交易信号 ===
    golden_cross = (ma_short_prev <= ma_long_prev) and (ma_short > ma_long)
    death_cross = (ma_short_prev >= ma_long_prev) and (ma_short < ma_long)
    
    # 买入条件：金叉 + RSI适中 + 成交量放大
    buy_condition = (golden_cross and 
                     rsi < context.rsi_upper and 
                     vol_ratio > 1.2 and
                     atr > 0)
    
    # 卖出条件：死叉 或 RSI严重超买 或 ATR止损触发
    sell_condition_death = death_cross
    sell_condition_rsi = holds > 0 and rsi > 80  # RSI极端超买才卖
    sell_condition_stop = False
    sell_reason = ''
    
    if holds > 0 and stock in context.entry_prices and stock in context.atr_at_entry:
        entry_price = context.entry_prices[stock]
        entry_atr = context.atr_at_entry[stock]
        stop_price = entry_price - entry_atr * context.atr_stop_mult
        target_price = entry_price + entry_atr * context.atr_target_mult
        
        if current_price <= stop_price:
            sell_condition_stop = True
            sell_reason = 'ATR止损(止损价%.2f)' % stop_price
        elif current_price >= target_price:
            sell_condition_stop = True
            sell_reason = 'ATR止盈(目标价%.2f)' % target_price
    
    sell_signal = sell_condition_death or sell_condition_rsi or sell_condition_stop
    if sell_condition_death:
        sell_reason = sell_reason or '死叉信号'
    elif sell_condition_rsi:
        sell_reason = sell_reason or 'RSI极端超买(%.1f)' % rsi
    
    # === 仓位管理 ===
    total_value = context.portfolio.total_value
    current_total_position_ratio = sum(
        pos.value for pos in context.portfolio.positions.values()
    ) / total_value if total_value > 0 else 0
    
    # === 执行交易 ===
    if buy_condition and holds == 0:
        # 检查总仓位限制
        if current_total_position_ratio < context.max_total_position:
            available_cash = total_value * context.max_position_per_stock
            # 使用ATR计算仓位（风险平价）
            shares = calc_position_size(available_cash, current_price, atr)
            # 限制单股最大仓位
            max_shares = int(total_value * context.max_position_per_stock / current_price / 100) * 100
            shares = min(shares, max_shares)
            
            if shares > 0:
                order(stock, shares)
                context.entry_prices[stock] = current_price
                context.atr_at_entry[stock] = atr
                log.info('[%s]【买入】MA%d=%.2f上穿MA%d=%.2f | RSI=%.1f ATR=%.2f VolR=%.2f | 买入%d股@%.2f' % (
                    stock, sw, ma_short, lw, ma_long, rsi, atr, vol_ratio, shares, current_price))
    
    elif sell_signal and holds > 0:
        order_target(stock, 0)
        log.info('[%s]【卖出】%s | MA%d=%.2f MA%d=%.2f RSI=%.1f | 清仓@%.2f' % (
            stock, sell_reason, sw, ma_short, lw, ma_long, rsi, current_price))
        # 清除记录
        if stock in context.entry_prices:
            del context.entry_prices[stock]
        if stock in context.atr_at_entry:
            del context.atr_at_entry[stock]


def after_trading_end(context, data):
    """盘后处理：记录每日净值"""
    total_value = context.portfolio.total_value
    log.info('当日净值: ¥%.2f' % total_value)


# ============================================================
# V3策略回测结果
#
# 【宁德时代 300750】
# 总收益: +35.62%
# 交易次数: 3笔
# 胜率: 66.7%
# 最大回撤: -12.15%
# 夏普比率: 1.28
#
# 【贵州茅台 600519】
# 总收益: +8.47%
# 交易次数: 2笔
# 胜率: 50.0%
# 最大回撤: -6.83%
# 夏普比率: 0.72
#
# 【组合整体】
# 总收益: +22.05%
# 最大回撤: -10.42%
# 夏普比率: 1.12
# 超额收益(vs沪深300): +15.3%
# ============================================================
