import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional


def validate_sieve_data(sieve_data: List[Dict], total_weight: float) -> Tuple[bool, str]:
    total_retained = sum(d['retained_weight'] for d in sieve_data)
    
    for d in sieve_data:
        if d['retained_weight'] < 0:
            return False, f"粒级 {d['sieve_size']} mm 的留存重量不能为负数"
    
    if total_retained > total_weight + 0.001:
        return False, f"所有粒级重量合计 ({total_retained:.2f} g) 超过样本总重量 ({total_weight:.2f} g)"
    
    return True, ""


def calculate_analysis(sieve_data: List[Dict], total_weight: float) -> Dict:
    if not sieve_data:
        return {
            'df': pd.DataFrame(),
            'cum_df': pd.DataFrame(),
            'median_diameter': None,
            'sorting_coefficient': None,
            'sorting_grade': '无数据',
            'total_retained': 0,
            'missing_sieves': [],
            'mean_d10': None,
            'd25': None,
            'd75': None,
            'd90': None,
            'reliability_score': 0,
            'reliability_level': '无数据',
            'reliability_details': {},
        }
    
    df = pd.DataFrame(sieve_data)
    df = df.sort_values('sieve_size', ascending=True).reset_index(drop=True)
    
    df['weight_percent'] = (df['retained_weight'] / total_weight * 100).round(2)
    
    total_retained = df['retained_weight'].sum()
    
    if total_retained < total_weight:
        pan_weight = total_weight - total_retained
        pan_percent = pan_weight / total_weight * 100
    else:
        pan_weight = 0
        pan_percent = 0
    
    cum_rows = []
    cum_percent = pan_percent
    cum_weight = pan_weight
    
    for i, row in df.iterrows():
        cum_rows.append({
            'sieve_size': row['sieve_size'],
            'cumulative_percent': round(cum_percent, 2),
            'cumulative_weight': round(cum_weight, 4),
        })
        cum_percent += row['weight_percent']
        cum_weight += row['retained_weight']
    
    if len(df) > 0:
        max_size = df['sieve_size'].max() * 2
        cum_rows.append({
            'sieve_size': max_size,
            'cumulative_percent': 100.0,
            'cumulative_weight': total_weight,
        })
    
    cum_df = pd.DataFrame(cum_rows)
    
    median_diameter = _calculate_percentile_diameter(cum_df, 50)
    d10 = _calculate_percentile_diameter(cum_df, 10)
    d25 = _calculate_percentile_diameter(cum_df, 25)
    d75 = _calculate_percentile_diameter(cum_df, 75)
    d90 = _calculate_percentile_diameter(cum_df, 90)
    
    sorting_coefficient = None
    sorting_grade = '无法判断'
    
    if d25 is not None and d75 is not None and d25 > 0:
        sorting_coefficient = np.sqrt(d75 / d25)
        if sorting_coefficient < 1.3:
            sorting_grade = '分选良好'
        elif sorting_coefficient < 2.0:
            sorting_grade = '分选一般'
        else:
            sorting_grade = '分选差'
    
    reliability = calculate_reliability_score(sieve_data, total_weight, default_sieve_count=11)
    
    return {
        'df': df,
        'cum_df': cum_df,
        'median_diameter': median_diameter,
        'sorting_coefficient': sorting_coefficient,
        'sorting_grade': sorting_grade,
        'total_retained': total_retained,
        'pan_weight': pan_weight,
        'pan_percent': pan_percent,
        'd10': d10,
        'd25': d25,
        'd75': d75,
        'd90': d90,
        'reliability_score': reliability['score'],
        'reliability_level': reliability['level'],
        'reliability_details': reliability['details'],
    }


def _calculate_percentile_diameter(df: pd.DataFrame, percentile: float) -> Optional[float]:
    if df.empty or 'cumulative_percent' not in df.columns:
        return None
    
    cum_percents = df['cumulative_percent'].values
    sieve_sizes = df['sieve_size'].values
    
    if cum_percents[-1] < percentile:
        return None
    
    for i in range(len(cum_percents)):
        if cum_percents[i] >= percentile:
            if i == 0:
                return float(sieve_sizes[i])
            
            prev_cum = cum_percents[i-1]
            curr_cum = cum_percents[i]
            prev_size = sieve_sizes[i-1]
            curr_size = sieve_sizes[i]
            
            if curr_cum == prev_cum:
                return float(curr_size)
            
            ratio = (percentile - prev_cum) / (curr_cum - prev_cum)
            diameter = prev_size * (curr_size / prev_size) ** ratio
            
            return float(diameter)
    
    return None


def get_sieve_label(size_mm: float) -> str:
    if size_mm >= 2.0:
        return f"{size_mm} mm"
    elif size_mm >= 0.063:
        return f"{size_mm * 1000:.0f} μm"
    else:
        return f"{size_mm * 1000:.1f} μm"


def classify_grade(sorting_coefficient: float) -> str:
    if sorting_coefficient is None:
        return '无法判断'
    if sorting_coefficient < 1.3:
        return '分选良好'
    elif sorting_coefficient < 2.0:
        return '分选一般'
    else:
        return '分选差'


def calculate_reliability_score(sieve_data: List[Dict], total_weight: float, 
                                default_sieve_count: int = 11) -> Dict:
    """
    计算分选结果的可信度评分
    返回: {'score': 0-100, 'level': '高/中/低', 'details': {...}}
    """
    score = 100
    details = {}
    
    data_count = len(sieve_data)
    coverage_ratio = min(data_count / default_sieve_count, 1.0)
    coverage_score = coverage_ratio * 40
    details['data_coverage'] = {
        'score': round(coverage_score, 1),
        'max_score': 40,
        'description': f'数据粒级覆盖率: {coverage_ratio*100:.1f}% ({data_count}/{default_sieve_count})'
    }
    score -= (40 - coverage_score)
    
    if total_weight > 0:
        total_retained = sum(d['retained_weight'] for d in sieve_data)
        recovery_ratio = total_retained / total_weight
        if recovery_ratio >= 0.95:
            recovery_score = 30
        elif recovery_ratio >= 0.85:
            recovery_score = 30 - (0.95 - recovery_ratio) * 100
        elif recovery_ratio >= 0.7:
            recovery_score = 20 - (0.85 - recovery_ratio) * 100
        else:
            recovery_score = max(0, 5 - (0.7 - recovery_ratio) * 20)
        
        recovery_score = round(recovery_score, 1)
        details['recovery_rate'] = {
            'score': recovery_score,
            'max_score': 30,
            'description': f'筛分回收率: {recovery_ratio*100:.1f}%'
        }
        score -= (30 - recovery_score)
    else:
        details['recovery_rate'] = {
            'score': 0,
            'max_score': 30,
            'description': '总重量为0，无法计算回收率'
        }
        score -= 30
    
    if data_count >= 3:
        size_range_valid = True
        details['size_range'] = {
            'score': 15,
            'max_score': 15,
            'description': '粒级范围合理'
        }
    else:
        size_range_valid = False
        details['size_range'] = {
            'score': 5,
            'max_score': 15,
            'description': '粒级数据过少，统计意义有限'
        }
        score -= 10
    
    distribution_score = 15
    if data_count >= 2:
        weights = [d['retained_weight'] for d in sieve_data]
        max_weight = max(weights) if weights else 0
        if max_weight > 0:
            zero_count = sum(1 for w in weights if w == 0)
            if zero_count > 0:
                distribution_score = 15 - zero_count * 3
                distribution_score = max(distribution_score, 5)
    
    distribution_score = round(max(distribution_score, 5), 1)
    details['distribution'] = {
        'score': distribution_score,
        'max_score': 15,
        'description': '粒径分布连续性'
    }
    score -= (15 - distribution_score)
    
    score = max(0, min(100, round(score, 1)))
    
    if score >= 80:
        level = '高'
    elif score >= 50:
        level = '中'
    else:
        level = '低'
    
    return {
        'score': score,
        'level': level,
        'details': details,
    }


def get_reliability_color(level: str) -> str:
    return {'高': 'green', '中': 'orange', '低': 'red'}.get(level, 'gray')


def suggest_missing_sieve_fill(sieve_data: List[Dict], default_sizes: List[float]) -> List[Dict]:
    """
    基于相邻粒级数据，对缺失粒级进行智能插值建议
    返回建议列表: [{'sieve_size': float, 'suggested_weight': float, 'confidence': 'high/medium/low'}, ...]
    """
    if not sieve_data or len(sieve_data) < 2:
        return []
    
    existing_sizes = {d['sieve_size']: d['retained_weight'] for d in sieve_data}
    sorted_sizes = sorted(default_sizes)
    
    suggestions = []
    
    for i, size in enumerate(sorted_sizes):
        if size in existing_sizes:
            continue
        
        prev_size = None
        next_size = None
        prev_weight = None
        next_weight = None
        
        for j in range(i - 1, -1, -1):
            if sorted_sizes[j] in existing_sizes:
                prev_size = sorted_sizes[j]
                prev_weight = existing_sizes[prev_size]
                break
        
        for j in range(i + 1, len(sorted_sizes)):
            if sorted_sizes[j] in existing_sizes:
                next_size = sorted_sizes[j]
                next_weight = existing_sizes[next_size]
                break
        
        if prev_size is not None and next_size is not None:
            log_prev = np.log10(prev_size)
            log_next = np.log10(next_size)
            log_curr = np.log10(size)
            
            ratio = (log_curr - log_prev) / (log_next - log_prev)
            
            log_prev_w = np.log10(max(prev_weight, 0.001))
            log_next_w = np.log10(max(next_weight, 0.001))
            suggested_weight = 10 ** (log_prev_w + ratio * (log_next_w - log_prev_w))
            
            gap = next_size / prev_size if prev_size > 0 else 0
            if gap <= 2:
                confidence = 'high'
            elif gap <= 4:
                confidence = 'medium'
            else:
                confidence = 'low'
        elif prev_size is not None:
            suggested_weight = prev_weight * 0.5
            confidence = 'low'
        elif next_size is not None:
            suggested_weight = next_weight * 0.5
            confidence = 'low'
        else:
            continue
        
        suggestions.append({
            'sieve_size': size,
            'sieve_label': get_sieve_label(size),
            'suggested_weight': round(suggested_weight, 4),
            'confidence': confidence,
        })
    
    return suggestions


def generate_export_data(samples_data: List[Dict]) -> pd.DataFrame:
    export_rows = []
    
    for sample in samples_data:
        analysis = sample['analysis']
        df = analysis['df']
        cum_df = analysis['cum_df']
        
        cum_map = dict(zip(cum_df['sieve_size'], cum_df['cumulative_percent']))
        
        for _, row in df.iterrows():
            cum_pct = cum_map.get(row['sieve_size'], '')
            export_rows.append({
                '样本编号': sample['sample_no'],
                '采样点': sample['sampling_site'],
                '喷发层位': sample.get('eruption_layer', ''),
                '样本总重量(g)': sample['total_weight'],
                '筛孔粒级(mm)': row['sieve_size'],
                '留存重量(g)': row['retained_weight'],
                '粒级占比(%)': row['weight_percent'],
                '小于该筛孔累计(%)': cum_pct,
            })
        
        export_rows.append({
            '样本编号': sample['sample_no'],
            '采样点': sample['sampling_site'],
            '喷发层位': sample.get('eruption_layer', ''),
            '样本总重量(g)': sample['total_weight'],
            '筛孔粒级(mm)': '底盘（小于最小粒级）',
            '留存重量(g)': analysis.get('pan_weight', 0),
            '粒级占比(%)': analysis.get('pan_percent', 0),
            '小于该筛孔累计(%)': analysis.get('pan_percent', 0),
        })
    
    return pd.DataFrame(export_rows)


def generate_summary_export(samples_data: List[Dict]) -> pd.DataFrame:
    summary_rows = []
    
    for sample in samples_data:
        analysis = sample['analysis']
        summary_rows.append({
            '样本编号': sample['sample_no'],
            '采样点': sample['sampling_site'],
            '喷发层位': sample.get('eruption_layer', ''),
            '样本总重量(g)': sample['total_weight'],
            '筛分总重量(g)': analysis['total_retained'],
            '底盘重量(g)': analysis.get('pan_weight', 0),
            '中值粒径D50(mm)': analysis['median_diameter'],
            'D10(mm)': analysis['d10'],
            'D25(mm)': analysis['d25'],
            'D75(mm)': analysis['d75'],
            'D90(mm)': analysis['d90'],
            '分选系数': analysis['sorting_coefficient'],
            '沉积分选评价': analysis['sorting_grade'],
            '可信度评分': analysis.get('reliability_score', ''),
            '可信度等级': analysis.get('reliability_level', ''),
        })
    
    return pd.DataFrame(summary_rows)


def prepare_profile_analysis(samples_data: List[Dict], sort_by: str = 'depth') -> pd.DataFrame:
    """
    准备剖面/时间序列分析数据
    sort_by: 'depth' 或 'time'
    """
    rows = []
    for sample in samples_data:
        analysis = sample.get('analysis', {})
        row = {
            'sample_no': sample.get('sample_no', ''),
            'sampling_site': sample.get('sampling_site', ''),
            'depth': sample.get('depth'),
            'sampling_time': sample.get('sampling_time', ''),
            'group_name': sample.get('group_name', ''),
            'D10': analysis.get('d10'),
            'D25': analysis.get('d25'),
            'D50': analysis.get('median_diameter'),
            'D75': analysis.get('d75'),
            'D90': analysis.get('d90'),
            'sorting_coefficient': analysis.get('sorting_coefficient'),
            'sorting_grade': analysis.get('sorting_grade', ''),
            'reliability_score': analysis.get('reliability_score'),
        }
        rows.append(row)
    
    df = pd.DataFrame(rows)
    
    if sort_by == 'depth' and 'depth' in df.columns:
        df = df.dropna(subset=['depth']).sort_values('depth', ascending=True).reset_index(drop=True)
    elif sort_by == 'time' and 'sampling_time' in df.columns:
        df = df[df['sampling_time'] != ''].sort_values('sampling_time').reset_index(drop=True)
    
    return df


def generate_trend_analysis(profile_df: pd.DataFrame, param: str = 'D50') -> Dict:
    """
    生成趋势分析结果
    """
    if profile_df.empty or param not in profile_df.columns:
        return {'has_trend': False, 'message': '数据不足，无法分析趋势'}
    
    values = profile_df[param].dropna().values
    if len(values) < 2:
        return {'has_trend': False, 'message': '有效数据点不足，无法分析趋势'}
    
    indices = np.arange(len(values))
    
    try:
        slope, intercept = np.polyfit(indices, values, 1)
        
        if len(values) >= 3:
            y_pred = slope * indices + intercept
            ss_res = np.sum((values - y_pred) ** 2)
            ss_tot = np.sum((values - np.mean(values)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        else:
            r_squared = None
        
        if abs(slope) < 1e-6:
            trend = '基本稳定'
        elif slope > 0:
            trend = '递增趋势'
        else:
            trend = '递减趋势'
        
        change_pct = ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else None
        
        return {
            'has_trend': True,
            'trend': trend,
            'slope': slope,
            'intercept': intercept,
            'r_squared': r_squared,
            'start_value': values[0],
            'end_value': values[-1],
            'change_percent': change_pct,
            'data_points': len(values),
        }
    except Exception:
        return {'has_trend': False, 'message': '趋势计算出错'}
