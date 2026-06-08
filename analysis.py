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
            'median_diameter': None,
            'sorting_coefficient': None,
            'sorting_grade': '无数据',
            'total_retained': 0,
            'missing_sieves': [],
            'mean_d10': None,
            'd25': None,
            'd75': None,
            'd90': None,
        }
    
    df = pd.DataFrame(sieve_data)
    df = df.sort_values('sieve_size', ascending=True).reset_index(drop=True)
    
    df['weight_percent'] = (df['retained_weight'] / total_weight * 100).round(2)
    df['cumulative_percent'] = df['weight_percent'].cumsum().round(2)
    
    total_retained = df['retained_weight'].sum()
    
    if total_retained < total_weight:
        pan_weight = total_weight - total_retained
        pan_percent = pan_weight / total_weight * 100
    else:
        pan_weight = 0
        pan_percent = 0
    
    median_diameter = _calculate_percentile_diameter(df, 50)
    d10 = _calculate_percentile_diameter(df, 10)
    d25 = _calculate_percentile_diameter(df, 25)
    d75 = _calculate_percentile_diameter(df, 75)
    d90 = _calculate_percentile_diameter(df, 90)
    
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
    
    return {
        'df': df,
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


def generate_export_data(samples_data: List[Dict]) -> pd.DataFrame:
    export_rows = []
    
    for sample in samples_data:
        analysis = sample['analysis']
        df = analysis['df']
        
        for _, row in df.iterrows():
            export_rows.append({
                '样本编号': sample['sample_no'],
                '采样点': sample['sampling_site'],
                '喷发层位': sample.get('eruption_layer', ''),
                '样本总重量(g)': sample['total_weight'],
                '筛孔粒级(mm)': row['sieve_size'],
                '留存重量(g)': row['retained_weight'],
                '粒级占比(%)': row['weight_percent'],
                '累计百分比(%)': row['cumulative_percent'],
            })
        
        export_rows.append({
            '样本编号': sample['sample_no'],
            '采样点': sample['sampling_site'],
            '喷发层位': sample.get('eruption_layer', ''),
            '样本总重量(g)': sample['total_weight'],
            '筛孔粒级(mm)': '底盘',
            '留存重量(g)': analysis.get('pan_weight', 0),
            '粒级占比(%)': analysis.get('pan_percent', 0),
            '累计百分比(%)': 100.0,
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
        })
    
    return pd.DataFrame(summary_rows)
