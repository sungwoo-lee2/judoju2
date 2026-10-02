from __future__ import annotations


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(v)))


def score_stock(x: dict) -> dict:
    """100-point leadership score.

    Flow is 20 points: foreign 8 + institution 8 + simultaneous-buying 4.
    When upstream investor data is unavailable only the flow component is neutral.
    """
    amount = 25 * clamp((x.get('amount_ratio', 1.0) - 0.9) / 2.6)

    flow_available = x.get('flow_available', False)
    if flow_available:
        foreign = 8 * clamp(x.get('foreign_score', 0.5))
        institution = 8 * clamp(x.get('institution_score', 0.5))
        foreign_net = x.get('foreign_net_5d', 0)
        institution_net = x.get('institution_net_5d', 0)
        simultaneous = 4.0 if foreign_net > 0 and institution_net > 0 else (1.5 if foreign_net > 0 or institution_net > 0 else 0.0)
        # Daily streak/surge signals can add a small bonus, but the flow component remains capped at 20.
        signal_bonus = 0.0
        if x.get('foreign_streak', 0) >= 3:
            signal_bonus += 0.8
        if x.get('institution_streak', 0) >= 3:
            signal_bonus += 0.8
        if x.get('flow_surge', False):
            signal_bonus += 0.9
        flow = min(20.0, foreign + institution + simultaneous + signal_bonus)
    else:
        foreign = institution = 4.0
        simultaneous = 2.0
        flow = 10.0

    rs20 = x.get('rs20', 1.0)
    trend = 20 * clamp((rs20 - 0.96) / 0.24)
    sector = 15 * clamp(x.get('sector_strength', 0.5))
    high52 = x.get('high52', 0.90)
    breakout = 10 * clamp((high52 - 0.88) / 0.12)
    change = x.get('change', 0.0)
    momentum = 10 * clamp((change + 1.5) / 7.5)

    total = round(amount + flow + trend + sector + breakout + momentum, 1)

    if total >= 84:
        stage = '본격주도'
    elif total >= 72:
        stage = '초기상승'
    elif total >= 60:
        stage = '발굴'
    elif total >= 48:
        stage = '관찰'
    else:
        stage = '이탈주의'

    reasons = []
    if x.get('amount_ratio', 1) >= 1.8:
        reasons.append(f"거래대금이 20일 평균의 {x['amount_ratio']:.1f}배")
    if flow_available:
        fn = x.get('foreign_net_5d', 0)
        inn = x.get('institution_net_5d', 0)
        if fn > 0 and inn > 0:
            reasons.append('최근 외국인·기관 동반 순매수')
        if x.get('foreign_streak',0) >= 3 or x.get('institution_streak',0) >= 3:
            fs=x.get('foreign_streak',0); ins=x.get('institution_streak',0)
            reasons.append(f'연속 순매수: 외국인 {fs}일 · 기관 {ins}일')
        if x.get('flow_surge',False):
            reasons.append('최근 3거래일 수급 급증 감지')
        elif fn > 0:
            reasons.append('최근 외국인 순매수 우위')
        elif inn > 0:
            reasons.append('최근 기관 순매수 우위')
    if rs20 >= 1.08:
        reasons.append(f"20일 상대강도 {rs20:.2f}")
    if high52 >= 0.97:
        reasons.append('52주 신고가권 접근')
    if change >= 3:
        reasons.append(f"당일 {change:+.1f}% 강세")
    if x.get('sector_strength', 0) >= 0.7:
        reasons.append('섹터 동반 강세')
    if not reasons:
        reasons.append('거래대금·수급·추세·섹터 점수 종합 상위')

    return {
        **x,
        'score': total,
        'stage': stage,
        'reasons': reasons[:4],
        'parts': {
            '거래대금': round(amount, 1),
            '수급': round(flow, 1),
            '추세': round(trend, 1),
            '섹터': round(sector, 1),
            '돌파': round(breakout, 1),
            '모멘텀': round(momentum, 1),
        },
        'flow_parts': {
            '외국인': round(foreign, 1),
            '기관': round(institution, 1),
            '동반수급': round(simultaneous, 1),
            '연속/급증': round(signal_bonus if flow_available else 0.0, 1),
        }
    }



def score_early_leader(x: dict) -> dict:
    """Score candidates that may be entering leadership before full trend maturity.

    100 points before overheat penalty:
    turnover acceleration 30, flow turn/acceleration 25, breakout proximity 20,
    sector breadth 15, momentum quality 10. Up to 18 points are deducted for
    already-overextended price moves so the list does not simply chase late spikes.
    """
    amount_ratio = float(x.get('amount_ratio', 1.0) or 1.0)
    turnover = 30 * clamp((amount_ratio - 1.05) / 2.0)

    if x.get('flow_available', False):
        fs = float(x.get('foreign_score', 0.5) or 0.5)
        ins = float(x.get('institution_score', 0.5) or 0.5)
        base_flow = 15 * clamp((fs + ins) / 2)
        accel = float(x.get('flow_acceleration_ratio', 0) or 0)
        acceleration = 6 * clamp((accel + 0.01) / 0.09)
        streak = 0.0
        if x.get('foreign_streak', 0) >= 2:
            streak += 2.0
        if x.get('institution_streak', 0) >= 2:
            streak += 2.0
        flow = min(25.0, base_flow + acceleration + streak)
    else:
        flow = 12.5

    high52 = float(x.get('high52', 0.90) or 0.90)
    # Highest score just below/around breakout; still allow fresh breakouts.
    if high52 < 0.88:
        breakout = 4 * clamp((high52 - 0.75) / 0.13)
    elif high52 <= 1.02:
        breakout = 20 * clamp((high52 - 0.88) / 0.14)
    else:
        breakout = max(8.0, 20.0 - (high52 - 1.02) * 180)

    sector = 15 * clamp(float(x.get('sector_strength', 0.45) or 0.45))
    change = float(x.get('change', 0.0) or 0.0)
    rs20 = float(x.get('rs20', 1.0) or 1.0)
    # Prefer positive but not exhausted moves and an improving medium trend.
    day_quality = 6 * clamp((change + 0.5) / 5.5)
    rs_quality = 4 * clamp((rs20 - 0.98) / 0.12)
    momentum = day_quality + rs_quality

    overheat_penalty = 0.0
    if change >= 10:
        overheat_penalty += min(8.0, (change - 9) * 1.2)
    if rs20 >= 1.25:
        overheat_penalty += min(6.0, (rs20 - 1.24) * 35)
    if amount_ratio >= 4.0:
        overheat_penalty += min(4.0, (amount_ratio - 4.0) * 1.2)

    total = round(max(0.0, min(100.0, turnover + flow + breakout + sector + momentum - overheat_penalty)), 1)

    signals = []
    if amount_ratio >= 1.6:
        signals.append(f'거래대금 {amount_ratio:.1f}배 급증')
    if x.get('flow_surge'):
        signals.append('최근 3일 수급 가속')
    elif x.get('foreign_streak', 0) >= 2 or x.get('institution_streak', 0) >= 2:
        signals.append(f"연속수급 외국인 {x.get('foreign_streak',0)}일·기관 {x.get('institution_streak',0)}일")
    elif x.get('flow_available') and (x.get('foreign_net_5d', 0) > 0 or x.get('institution_net_5d', 0) > 0):
        signals.append('외국인/기관 순매수 우위')
    if 0.95 <= high52 <= 1.02:
        signals.append(f'52주 고점의 {high52*100:.0f}%')
    if x.get('sector_strength', 0) >= 0.65:
        signals.append('섹터 확산 동반')
    if 0.5 <= change <= 7:
        signals.append(f'당일 {change:+.1f}% 초기 모멘텀')
    if overheat_penalty >= 4:
        signals.append('과열 감점 적용')
    if not signals:
        signals.append('거래대금·수급·돌파 전 단계 종합 상위')

    if total >= 78:
        label = '초기주도 강'
    elif total >= 66:
        label = '초기주도 후보'
    elif total >= 55:
        label = '관찰 후보'
    else:
        label = '대기'

    return {
        **x,
        'early_score': total,
        'early_label': label,
        'early_signals': signals[:4],
        'early_parts': {
            '거래대금급증': round(turnover, 1),
            '수급전환': round(flow, 1),
            '돌파근접': round(breakout, 1),
            '섹터확산': round(sector, 1),
            '초기모멘텀': round(momentum, 1),
            '과열감점': round(overheat_penalty, 1),
        }
    }
