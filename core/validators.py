from typing import Any, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime
import re


@dataclass
class ValidationResult:
    valid: bool
    message: str = ""
    
    def __bool__(self):
        return self.valid


def validate_required(value: Any, field_name: str = "该字段") -> ValidationResult:
    if value is None or (isinstance(value, str) and not value.strip()):
        return ValidationResult(False, f"{field_name}不能为空")
    return ValidationResult(True)


def validate_positive_number(value: Any, field_name: str = "该数值", 
                             min_value: float = 0, max_value: Optional[float] = None,
                             allow_zero: bool = True) -> ValidationResult:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return ValidationResult(False, f"{field_name}必须是有效的数值")
    
    if not allow_zero and num == 0:
        return ValidationResult(False, f"{field_name}不能为0")
    
    if num < min_value:
        return ValidationResult(False, f"{field_name}不能小于{min_value}")
    
    if max_value is not None and num > max_value:
        return ValidationResult(False, f"{field_name}不能大于{max_value}")
    
    return ValidationResult(True)


def validate_date_format(date_str: str, formats: Optional[List[str]] = None,
                         field_name: str = "日期") -> ValidationResult:
    if not date_str or not date_str.strip():
        return ValidationResult(True)
    
    if formats is None:
        formats = ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S']
    
    date_str = date_str.strip()
    for fmt in formats:
        try:
            datetime.strptime(date_str, fmt)
            return ValidationResult(True)
        except ValueError:
            continue
    
    return ValidationResult(False, f"{field_name}格式不正确，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS 格式")


def validate_email(email: str) -> ValidationResult:
    if not email or not email.strip():
        return ValidationResult(True)
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(pattern, email.strip()):
        return ValidationResult(True)
    return ValidationResult(False, "邮箱格式不正确")


def validate_min_length(value: str, min_len: int, field_name: str = "该字段") -> ValidationResult:
    if not value:
        return ValidationResult(True)
    if len(value.strip()) < min_len:
        return ValidationResult(False, f"{field_name}长度不能少于{min_len}个字符")
    return ValidationResult(True)


def validate_max_length(value: str, max_len: int, field_name: str = "该字段") -> ValidationResult:
    if not value:
        return ValidationResult(True)
    if len(value.strip()) > max_len:
        return ValidationResult(False, f"{field_name}长度不能超过{max_len}个字符")
    return ValidationResult(True)


def validate_numeric_range(value: float, min_val: Optional[float], max_val: Optional[float],
                           field_name: str = "数值") -> ValidationResult:
    if min_val is not None and value < min_val:
        return ValidationResult(False, f"{field_name}不能小于{min_val}")
    if max_val is not None and value > max_val:
        return ValidationResult(False, f"{field_name}不能大于{max_val}")
    return ValidationResult(True)


class FormValidator:
    def __init__(self):
        self._errors: List[str] = []
    
    def add_error(self, message: str) -> None:
        self._errors.append(message)
    
    def validate(self, result: ValidationResult) -> bool:
        if not result.valid:
            self._errors.append(result.message)
            return False
        return True
    
    @property
    def is_valid(self) -> bool:
        return len(self._errors) == 0
    
    @property
    def errors(self) -> List[str]:
        return self._errors.copy()
    
    def get_first_error(self) -> Optional[str]:
        return self._errors[0] if self._errors else None
    
    def show_errors(self) -> None:
        import streamlit as st
        for error in self._errors:
            st.error(error)
