from report import generate_pdf_report, generate_word_report
from analysis import generate_export_data, generate_summary_export


def generate_sample_report(samples_data, title="火山灰样本分析报告"):
    result = {
        'pdf': None,
        'word': None,
        'csv_detail': None,
        'csv_summary': None,
    }
    
    try:
        result['pdf'] = generate_pdf_report(samples_data, title=title)
    except ImportError:
        pass
    
    try:
        result['word'] = generate_word_report(samples_data, title=title)
    except ImportError:
        pass
    
    if samples_data and samples_data[0].get('analysis'):
        result['csv_detail'] = generate_export_data(samples_data)
        result['csv_summary'] = generate_summary_export(samples_data)
    
    return result


def generate_comparison_report(samples_data):
    return generate_sample_report(samples_data, title="火山灰多样本对比分析报告")
